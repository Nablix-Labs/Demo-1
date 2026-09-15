from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.ai_engine.openai_client import OpenAIAIEngineClient
from app.ai_engine.schemas import StrictSchema
from app.core.config import Settings, get_settings
from app.core.exceptions import AdapterError
from app.core.logger import logger
from app.models.phase4_review import (
    BraceBoardElement,
    BoxedBoardElement,
    ExampleBoardElement,
    ExpressionBoardElement,
    LabelBoardElement,
    Phase4ReviewRequest,
    Phase4ReviewResponse,
    StudentInsights,
    StruckBoardElement,
    TutorReplay,
    TutorReplayBoard,
    ValueRowBoardElement,
)


PHASE4_REVIEW_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "phase4_review.yaml"


class Phase4ReviewValidationError(ValueError):
    pass


class Phase4ReviewConfig(StrictSchema):
    generation_instructions: str
    stricter_guardrail_instruction: str
    forbidden_student_text_patterns: list[str]
    confirmed_pattern_minimum_count: int
    possible_pattern_minimum_count: int


@lru_cache(maxsize=1)
def load_phase4_review_config() -> Phase4ReviewConfig:
    raw_config: object = yaml.safe_load(PHASE4_REVIEW_CONFIG_PATH.read_text(encoding="utf-8"))
    return Phase4ReviewConfig.model_validate(raw_config)


def build_openai_phase4_review_context(
    request: Phase4ReviewRequest,
    config: Phase4ReviewConfig,
) -> dict[str, object]:
    """Build the compact prompt context without PDF URLs or database-only fields."""
    return {
        "generation_instructions": config.generation_instructions,
        "topic_info": request.topic_info.model_dump(),
        "topic_outcome": request.topic_outcome.model_dump(),
        "replay_items": [
            {
                "review_item_id": item.review_item_id,
                "question_id": item.question_id,
                "attempt_id": item.attempt_id,
                "artifact_id": item.artifact_id,
                "question_text": item.question_text,
                "student_answer": item.student_answer,
                "ocr_text": item.ocr_text,
                "page_count": item.page_count,
                "detected_errors": [error.model_dump() for error in item.detected_errors],
                "linked_misconceptions": item.linked_misconceptions,
                "canonical_answer": item.canonical_answer,
                "answer_steps": item.answer_steps,
            }
            for item in request.replay_items
        ],
        "whole_topic_evidence": request.whole_topic_evidence.model_dump(),
        "journey_questions": [
            question.model_dump() for question in request.journey_questions
        ],
    }


def build_openai_phase4_review_client(settings: Settings) -> OpenAIAIEngineClient:
    if settings.use_openai_ai_engine is False or settings.openai_api_key == "":
        raise AdapterError(
            "phase4_review",
            "Phase 4 review generation requires NABLIX_USE_OPENAI_AI_ENGINE=true and an OpenAI API key.",
        )
    from app.ai_engine.classifier_config import load_classifier_rules

    rules = load_classifier_rules()
    return OpenAIAIEngineClient(
        api_key=settings.openai_api_key,
        model=settings.openai_ai_engine_model,
        timeout_seconds=settings.openai_request_timeout_seconds,
        prompt_cache_key_enabled=settings.openai_prompt_cache_key_enabled,
        store_responses=settings.openai_store_responses,
        retry_count=settings.adapter_request_retry_count,
        guided_reasoning_effort=rules.guided_learning.reasoning_effort,
        guided_model_supports_reasoning_effort=(
            rules.guided_learning.model_supports_reasoning_effort
        ),
        guided_verbosity=rules.guided_learning.verbosity,
    )


def board_element_text(board: TutorReplayBoard | None) -> list[str]:
    """Return every learner-visible label from one structured replay board."""

    if board is None:
        return []
    text: list[str] = []
    for element in board.elements:
        if isinstance(
            element,
            (
                ExpressionBoardElement,
                LabelBoardElement,
                StruckBoardElement,
                BoxedBoardElement,
                ExampleBoardElement,
            ),
        ):
            text.append(element.text)
        elif isinstance(element, ValueRowBoardElement):
            text.extend(element.values)
            text.append(element.arrow_label)
        elif isinstance(element, BraceBoardElement):
            text.extend(element.labels)
    return text


def _student_facing_text(response: Phase4ReviewResponse) -> list[str]:
    insights: StudentInsights = response.student_insights
    outcome = response.topic_outcome
    return [
        (outcome.next_action_message or "") if outcome is not None else "",
        *[label.skill_label for label in (response.skill_labels or [])],
        insights.strength_summary,
        insights.development_summary,
        insights.learning_pattern_summary or "",
        insights.recent_improvement_summary or "",
        insights.next_practice_focus,
        *insights.personalised_notes,
        *[
            text
            for replay in response.tutor_replays
            for step in replay.replay_steps
            for text in (
                replay.first_error.summary,
                replay.first_error.why_it_matters or "",
                step.narration,
                step.tutor_write,
                step.stage_label or "",
                *board_element_text(step.board),
            )
        ],
    ]


def _validate_replay_identity(request: Phase4ReviewRequest, response: Phase4ReviewResponse) -> None:
    expected = [
        (item.review_item_id, item.question_id, item.attempt_id, item.artifact_id)
        for item in request.replay_items
    ]
    actual = [
        (replay.review_item_id, replay.question_id, replay.attempt_id, replay.artifact_id)
        for replay in response.tutor_replays
    ]
    if actual != expected:
        raise Phase4ReviewValidationError(
            "tutor_replays must exactly match supplied replay_items in their original order"
        )


def _validate_first_error_pages(request: Phase4ReviewRequest, response: Phase4ReviewResponse) -> None:
    page_counts = {item.review_item_id: item.page_count for item in request.replay_items}
    for replay in response.tutor_replays:
        page_no = replay.first_error.student_page_no
        page_count = page_counts[replay.review_item_id]
        if page_no is not None and (page_count is None or page_no > page_count):
            raise Phase4ReviewValidationError(
                f"student_page_no exceeds stored work pages for review_item_id={replay.review_item_id}"
            )


def _validate_pattern_and_improvement(
    request: Phase4ReviewRequest,
    insights: StudentInsights,
    config: Phase4ReviewConfig,
) -> None:
    recurrence_count = max(
        request.whole_topic_evidence.misconception_recurrence_counts.values(),
        default=0,
    )
    if recurrence_count < config.possible_pattern_minimum_count and insights.learning_pattern_summary is not None:
        raise Phase4ReviewValidationError(
            "learning_pattern_summary requires repeated misconception evidence"
        )
    has_later_independent_success = any(
        result.independent and result.evaluation == "CORRECT"
        for result in request.whole_topic_evidence.final_independent_results
    )
    if insights.recent_improvement_summary is not None and not has_later_independent_success:
        raise Phase4ReviewValidationError(
            "recent_improvement_summary requires later correct independent evidence"
        )


def _validate_skill_labels(
    request: Phase4ReviewRequest,
    response: Phase4ReviewResponse,
) -> None:
    """A label must name a real attempt, and each attempt at most once.

    The pair, never attempt_id alone: sequences restart per question, so two
    attempts on two questions legitimately share one.
    """

    known = {
        (question.question_usage_id, question.attempt_id)
        for question in request.journey_questions
    }
    seen: set[tuple[str | None, str]] = set()
    for label in response.skill_labels or []:
        key = (label.question_usage_id, label.attempt_id)
        if key not in known:
            raise Phase4ReviewValidationError(
                f"skill_label names an attempt that is not in the journey: {key}"
            )
        if key in seen:
            raise Phase4ReviewValidationError(
                f"skill_labels contains more than one label for attempt {key}"
            )
        seen.add(key)


def _validate_student_language(
    request: Phase4ReviewRequest,
    response: Phase4ReviewResponse,
    config: Phase4ReviewConfig,
) -> None:
    internal_identifiers = [
        item.question_id for item in request.replay_items
    ] + [
        item.question_usage_id for item in request.replay_items
    ] + [
        item.attempt_id for item in request.replay_items
    ] + [
        artifact_id
        for item in request.replay_items
        if (artifact_id := item.artifact_id) is not None
    ]
    prohibited = [*config.forbidden_student_text_patterns, *internal_identifiers]
    text = " ".join(_student_facing_text(response)).lower()
    leaked = next((value for value in prohibited if value.lower() in text), None)
    if leaked is not None:
        raise Phase4ReviewValidationError(
            f"student-facing Phase 4 text contains prohibited internal reference: {leaked}"
        )


def _normalise_math_text(text: str) -> str:
    return re.sub(r"[^a-z0-9+*/=.-]", "", text.lower().replace("×", "*").replace("−", "-"))


def _numeric_row_values(element: ValueRowBoardElement) -> tuple[str, ...]:
    return tuple(re.findall(r"\d+(?:\.\d+)?", " ".join(element.values)))


def _validate_board_progression(
    request: Phase4ReviewRequest,
    response: Phase4ReviewResponse,
) -> None:
    """Keep each replay board tied to its own question as it develops."""
    item_by_id = {item.review_item_id: item for item in request.replay_items}
    for replay in response.tutor_replays:
        item = item_by_id[replay.review_item_id]
        previous_rows: set[tuple[str, ...]] = set()
        previous_values: set[str] = set()
        canonical_answer = _normalise_math_text(item.canonical_answer)
        submitted_work = {
            _normalise_math_text(value)
            for value in (item.student_answer, item.ocr_text)
            if value is not None and value.strip()
        }
        for step in replay.replay_steps:
            if step.board is None:
                continue
            for element in step.board.elements:
                if isinstance(element, ValueRowBoardElement):
                    values = _numeric_row_values(element)
                    if not values or values in previous_rows:
                        previous_rows.add(values)
                        previous_values.update(values)
                        continue
                    if set(values).intersection(previous_values):
                        raise Phase4ReviewValidationError(
                            "a replay board value row mixes new values with values from an earlier row "
                            f"for review_item_id={replay.review_item_id}"
                        )
                    previous_rows.add(values)
                    previous_values.update(values)
                elif isinstance(element, BoxedBoardElement):
                    if canonical_answer not in _normalise_math_text(element.text):
                        raise Phase4ReviewValidationError(
                            "a replay board boxed rule differs from the supplied canonical answer "
                            f"for review_item_id={replay.review_item_id}"
                        )
                elif isinstance(element, StruckBoardElement):
                    struck_expression = _normalise_math_text(element.text)
                    if not any(struck_expression in work for work in submitted_work):
                        raise Phase4ReviewValidationError(
                            "a replay board crossed-out expression is not supported by submitted work "
                            f"for review_item_id={replay.review_item_id}"
                        )


def validate_phase4_review_response(
    request: Phase4ReviewRequest,
    response: Phase4ReviewResponse,
    config: Phase4ReviewConfig,
) -> None:
    _validate_replay_identity(request, response)
    _validate_first_error_pages(request, response)
    _validate_pattern_and_improvement(request, response.student_insights, config)
    _validate_skill_labels(request, response)
    _validate_student_language(request, response, config)
    _validate_board_progression(request, response)


def generate_phase4_review(request: Phase4ReviewRequest) -> Phase4ReviewResponse:
    config = load_phase4_review_config()
    context = build_openai_phase4_review_context(request, config)
    client = build_openai_phase4_review_client(get_settings())
    schema = Phase4ReviewResponse.model_json_schema()
    try:
        generated = Phase4ReviewResponse.model_validate(
            client.generate_phase4_review(context=context, schema=schema)
        )
        validate_phase4_review_response(request, generated, config)
    except AdapterError:
        raise
    except (ValidationError, ValueError) as first_error:
        stricter_context = {
            **context,
            "generation_instructions": (
                f"{config.generation_instructions}\n\n{config.stricter_guardrail_instruction}"
            ),
        }
        try:
            generated = Phase4ReviewResponse.model_validate(
                client.generate_phase4_review(context=stricter_context, schema=schema)
            )
            validate_phase4_review_response(request, generated, config)
        except AdapterError:
            raise
        except (ValidationError, ValueError) as retry_error:
            raise Phase4ReviewValidationError(
                f"Phase 4 review generation failed after a grounded retry: {retry_error}"
            ) from retry_error
        logger.warning("phase4_review_grounded_retry", extra={"validation_error": str(first_error)})
    logger.info(
        "phase4_review_generated",
        extra={
            "replay_count": len(generated.tutor_replays),
            "pattern_included": generated.student_insights.learning_pattern_summary is not None,
            "improvement_included": generated.student_insights.recent_improvement_summary is not None,
        },
    )
    return generated
