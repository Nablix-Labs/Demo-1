from __future__ import annotations

import hashlib
import json
from collections.abc import Collection
from dataclasses import dataclass
from time import perf_counter

import httpx
from pydantic import Field, StrictBool, ValidationError

from app.ai_engine.prompt_registry import (
    OpenAITutorPromptMetadata,
    Trigger,
    build_openai_tutor_messages,
    build_openai_tutor_prompt_metadata,
    sha256_text,
)
from app.ai_engine.schemas import (
    ErrorType,
    EvaluationCategory,
    HintLevel,
    InputSource,
    IntentType,
    LearningPhase,
    ResponseStrategy,
    StrictSchema,
)
from app.core.exceptions import AdapterError
from app.core.logger import logger
from app.models.adapters import ConversationMessage, ConversationState, Phase2PromptContext
from app.models.guided_learning import (
    ActiveTeachingObjective,
    GeneratedQuestionRubric,
    GuidedEvaluation,
    HybridSemanticEvaluation,
    HybridTutorRequest,
    HybridTutorWording,
    HybridTutorWordingRequest,
    HybridTutorTurn,
    HybridTutorTurnContext,
    ScaffoldEvaluationContext,
    ScaffoldStepEvaluation,
)
from app.models.student_model_session import AnswerSpec, QuestionType


_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def _hybrid_current_step_payload(request: HybridTutorRequest) -> dict[str, object] | None:
    current_index = request.pedagogical_state.current_answer_step_index
    if current_index is None:
        return None
    return {
        "step_id": f"{request.answer_spec.answer_spec_id}:STEP:{current_index + 1}",
        "step_index": current_index,
        "text": request.answer_spec.answer_steps[current_index],
        "component_id": f"{request.answer_spec.answer_spec_id}:COMPONENT:{current_index + 1}",
    }


class OpenAITutorTurn(StrictSchema):
    intent: IntentType
    evaluation: EvaluationCategory | None
    error_type: ErrorType | None
    response_strategy: ResponseStrategy
    hint_level: HintLevel | None
    tutor_message: str
    tutor_message_voice_optimised: str
    reasoning_complete: StrictBool
    confidence: float = Field(ge=0.0, le=1.0)


class OpenAITutorMessage(StrictSchema):
    tutor_message: str
    tutor_message_voice_optimised: str
    confidence: float = Field(ge=0.0, le=1.0)


@dataclass(frozen=True)
class OpenAIUsageMetrics:
    cached_tokens: int
    cache_write_tokens: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class OpenAIAIEngineClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: int,
        prompt_cache_key_enabled: bool,
        store_responses: bool,
        retry_count: int,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._prompt_cache_key_enabled = prompt_cache_key_enabled
        self._store_responses = store_responses
        self._retry_count = retry_count

    def generate_tutor_turn(
        self,
        question: str,
        correct_answer: str,
        answer_spec: AnswerSpec | None,
        phase_2_prompt_context: Phase2PromptContext | None,
        active_triggers: list[Trigger],
        student_input: str,
        phase: LearningPhase,
        input_source: InputSource,
        transcript_confidence: float | None,
        attempt_count: int,
        current_hint_level: HintLevel | None,
        question_completed: bool,
        answer_value_confirmed: bool,
        reasoning_required: bool,
        grounded_intent: IntentType,
        grounded_evaluation: EvaluationCategory | None,
        grounded_error_type: ErrorType | None,
        conversation_history: list[ConversationMessage],
        conversation_state: ConversationState | None,
    ) -> OpenAITutorTurn:
        schema = OpenAITutorTurn.model_json_schema()
        content = self._request_json(
            name="tutor_turn",
            schema=schema,
            phase=phase,
            active_triggers=active_triggers,
            conversation_history=conversation_history,
            user_payload={
                "question": question,
                "correct_answer": correct_answer,
                "answer_spec": (
                    answer_spec.model_dump()
                    if answer_spec is not None
                    else None
                ),
                "phase_2_context": (
                    phase_2_prompt_context.model_dump()
                    if phase_2_prompt_context is not None
                    else None
                ),
                "student_input": student_input,
                "input_source": input_source,
                "transcript_confidence": transcript_confidence,
                "attempt_count": attempt_count,
                "current_hint_level": current_hint_level,
                "question_completed": question_completed,
                "answer_value_confirmed": answer_value_confirmed,
                "reasoning_required": reasoning_required,
                "grounded_intent": grounded_intent,
                "grounded_evaluation": grounded_evaluation,
                "grounded_error_type": grounded_error_type,
                "conversation_state": (
                    conversation_state.model_dump()
                    if conversation_state is not None
                    else None
                ),
                "answer_reveal_allowed": False,
            },
        )
        return OpenAITutorTurn.model_validate(content)

    def generate_guided_rubric(
        self,
        question_id: str,
        question_type: QuestionType | None,
        question: str,
        answer_spec: AnswerSpec,
        potential_errors: list[dict[str, object]],
        target_micro_skill_ids: list[str],
        prompt_version: str,
        system_prompt: str,
    ) -> GeneratedQuestionRubric:
        answer_payload = answer_spec.model_dump()
        cache_source = json.dumps(
            {
                "question_id": question_id,
                "question_type": question_type,
                "answer_spec": answer_payload,
                "prompt_version": prompt_version,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        cache_key = hashlib.sha256(cache_source.encode("utf-8")).hexdigest()
        schema = GeneratedQuestionRubric.model_json_schema()
        content = self._request_guided_json(
            name="guided_question_rubric",
            schema=schema,
            system_prompt=system_prompt,
            user_payload={
                "question_id": question_id,
                "question_type": question_type,
                "question": question,
                "answer_spec": answer_payload,
                "allowed_potential_errors": potential_errors,
                "target_micro_skill_ids": target_micro_skill_ids,
                "cache_key": cache_key,
                "prompt_version": prompt_version,
            },
        )
        try:
            rubric = GeneratedQuestionRubric.model_validate(content)
        except ValidationError as error:
            raise AdapterError(
                "openai_ai_engine",
                f"invalid guided rubric: {error}",
            ) from error
        return rubric.model_copy(
            update={
                "question_id": question_id,
                "cache_key": cache_key,
                "prompt_version": prompt_version,
            }
        )

    def evaluate_guided_turn(
        self,
        question_type: QuestionType | None,
        question: str,
        answer_spec: AnswerSpec,
        deterministic_evaluation: EvaluationCategory | None,
        generated_rubric: GeneratedQuestionRubric,
        active_objective: ActiveTeachingObjective,
        student_response: str,
        input_source: InputSource,
        allowed_error_codes: list[dict[str, object]],
        recent_conversation: list[ConversationMessage],
        validation_feedback: str | None,
        evaluator_prompt_version: str,
        system_prompt: str,
    ) -> GuidedEvaluation:
        content = self._request_guided_json(
            name="guided_turn_evaluation",
            schema=GuidedEvaluation.model_json_schema(),
            system_prompt=system_prompt,
            user_payload={
                "question_type": question_type,
                "question": question,
                "answer_spec": answer_spec.model_dump(),
                "deterministic_evaluation": deterministic_evaluation,
                "generated_rubric": generated_rubric.model_dump(),
                "active_objective": active_objective.model_dump(),
                "student_response": student_response,
                "input_source": input_source,
                "allowed_error_codes": allowed_error_codes,
                "recent_conversation": [
                    message.model_dump()
                    for message in recent_conversation
                ],
                "validation_feedback": validation_feedback,
                "evaluator_prompt_version": evaluator_prompt_version,
                "answer_reveal_allowed": False,
            },
        )
        try:
            return GuidedEvaluation.model_validate(content)
        except ValidationError as error:
            raise AdapterError(
                "openai_ai_engine",
                f"invalid guided evaluation: {error}",
            ) from error

    def evaluate_scaffold_step(
        self,
        context: ScaffoldEvaluationContext,
        student_response: str,
        input_source: InputSource,
        system_prompt: str,
    ) -> ScaffoldStepEvaluation:
        content = self._request_guided_json(
            name="scaffold_step_evaluation",
            schema=ScaffoldStepEvaluation.model_json_schema(),
            system_prompt=system_prompt,
            user_payload={
                "scaffold": context.model_dump(),
                "student_response": student_response,
                "input_source": input_source,
            },
        )
        try:
            return ScaffoldStepEvaluation.model_validate(content)
        except ValidationError as error:
            raise AdapterError(
                "openai_ai_engine",
                f"invalid scaffold evaluation: {error}",
            ) from error

    def evaluate_hybrid_semantics(
        self,
        request: HybridTutorRequest,
        system_prompt: str,
    ) -> HybridSemanticEvaluation:
        current_step = _hybrid_current_step_payload(request)
        content = self._request_guided_json(
            name="hybrid_semantic_evaluation",
            schema=HybridSemanticEvaluation.model_json_schema(),
            system_prompt=system_prompt,
            user_payload={
                "question_id": request.question_id,
                "question": request.question,
                "current_authored_step": current_step,
                "completed_component_ids": request.pedagogical_state.completed_component_ids,
                "student_evidence": request.student_evidence.model_dump(),
                "ordered_canvas_memory": [
                    item.model_dump() for item in request.ordered_canvas_memory
                ],
                "support_state": request.support_state.model_dump(),
            },
        )
        try:
            return HybridSemanticEvaluation.model_validate(content)
        except ValidationError as error:
            raise AdapterError(
                "openai_ai_engine",
                f"invalid hybrid semantic evaluation: {error}",
            ) from error

    def generate_hybrid_tutor_wording(
        self,
        request: HybridTutorWordingRequest,
        system_prompt: str,
    ) -> HybridTutorWording:
        content = self._request_guided_json(
            name="hybrid_tutor_wording",
            schema=HybridTutorWording.model_json_schema(),
            system_prompt=system_prompt,
            user_payload=request.model_dump(),
        )
        try:
            return HybridTutorWording.model_validate(content)
        except ValidationError as error:
            raise AdapterError(
                "openai_ai_engine",
                f"invalid hybrid tutor wording: {error}",
            ) from error

    def generate_hybrid_tutor_turn(
        self,
        context: HybridTutorTurnContext,
        system_prompt: str,
    ) -> HybridTutorTurn:
        request = context.request
        authored_steps = [
            {
                "step_id": f"{request.answer_spec.answer_spec_id}:STEP:{index + 1}",
                "component_id": f"{request.answer_spec.answer_spec_id}:COMPONENT:{index + 1}",
                "text": text,
            }
            for index, text in enumerate(request.answer_spec.answer_steps)
        ]
        completed = request.pedagogical_state.completed_component_ids
        content = self._request_guided_json(
            name="hybrid_tutor_turn",
            schema=HybridTutorTurn.model_json_schema(),
            system_prompt=system_prompt,
            user_payload={
                "question_id": request.question_id,
                "question_type": request.question_type,
                "question": request.question,
                "answer_spec": request.answer_spec.model_dump(),
                "authored_steps": authored_steps,
                "completed_step_ids": [step["step_id"] for step in authored_steps[:len(completed)]],
                "unresolved_step_ids": [step["step_id"] for step in authored_steps[len(completed):]],
                "selected_option": {
                    "option_id": request.student_evidence.selected_option_id,
                    "option_text": request.student_evidence.selected_option_text,
                },
                "resolved_student_meaning": context.resolved_student_meaning,
                "student_evidence": request.student_evidence.model_dump(),
                "relevant_history": [item.model_dump() for item in request.session_history],
                "support_state": request.support_state.model_dump(),
                "active_support_content": (
                    context.active_support_content.model_dump()
                    if context.active_support_content is not None else None
                ),
                "ordered_canvas_memory": [item.model_dump() for item in request.ordered_canvas_memory],
                "decision": context.decision.model_dump(),
                "canvas_actions": [item.model_dump() for item in context.canvas_actions],
                "approved_answer_reveal": context.approved_answer_reveal,
            },
        )
        try:
            return HybridTutorTurn.model_validate(content)
        except ValidationError as error:
            raise AdapterError("openai_ai_engine", f"invalid hybrid tutor turn: {error}") from error

    def _request_guided_json(
        self,
        name: str,
        schema: dict[str, object],
        system_prompt: str,
        user_payload: dict[str, object],
    ) -> dict[str, object]:
        request_content = json.dumps(
            {"component": name, **user_payload},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        request_body: dict[str, object] = {
            "model": self._model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request_content},
            ],
            "store": self._store_responses,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": name,
                    "schema": schema,
                    "strict": True,
                }
            },
        }
        if self._prompt_cache_key_enabled:
            request_body["prompt_cache_key"] = sha256_text(system_prompt)
        response, latency_ms = self._post_with_retries(request_body)
        if response.status_code != 200:
            raise AdapterError(
                "openai_ai_engine",
                f"status={response.status_code} body={response.text}",
            )
        try:
            response_payload = response.json()
            usage = extract_openai_usage_metrics(response_payload)
            logger.info(
                "openai_guided_evaluator_usage",
                extra={
                    "component": name,
                    "request_id": (
                        response_payload.get("id")
                        if isinstance(response_payload, dict)
                        else None
                    ),
                    "model": self._model,
                    "prompt_sha256": sha256_text(system_prompt),
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "cached_tokens": usage.cached_tokens,
                    "total_tokens": usage.total_tokens,
                    "latency_ms": round(latency_ms, 3),
                },
            )
            return json.loads(_extract_response_text(response_payload))
        except (TypeError, ValueError, KeyError, ValidationError) as error:
            raise AdapterError(
                "openai_ai_engine",
                f"unparseable guided response: {error}; body={response.text}",
            ) from error

    def build_tutor_message(
        self,
        question: str,
        student_input: str,
        evaluation: EvaluationCategory | None,
        error_type: ErrorType | None,
        response_strategy: str,
        hint_level: int | None,
        phase: LearningPhase,
        conversation_history: list[ConversationMessage],
        canvas_context: dict[str, object] | None,
        rejected_tutor_message: str | None,
        validation_feedback: str | None,
    ) -> OpenAITutorMessage:
        schema = OpenAITutorMessage.model_json_schema()
        content = self._request_json(
            name="tutor_message",
            schema=schema,
            phase=phase,
            active_triggers=[],
            conversation_history=conversation_history,
            user_payload={
                "question": question,
                "student_input": student_input,
                "evaluation": evaluation,
                "error_type": error_type,
                "response_strategy": response_strategy,
                "hint_level": hint_level,
                "canvas_context": canvas_context,
                "rejected_tutor_message": rejected_tutor_message,
                "validation_feedback": validation_feedback,
                "answer_reveal_allowed": False,
            },
        )
        return OpenAITutorMessage.model_validate(content)

    def generate_session_review(
        self,
        context: dict[str, object],
        schema: dict[str, object],
    ) -> dict[str, object]:
        return self._request_json(
            name="session_review_generation",
            schema=schema,
            phase="REVIEW",
            active_triggers=[],
            conversation_history=[],
            user_payload=context,
        )

    def regenerate_session_review(
        self,
        context: dict[str, object],
        schema: dict[str, object],
        stricter_instruction: str,
    ) -> dict[str, object]:
        retry_context: dict[str, object] = {
            **context,
            "guardrail_retry_instruction": stricter_instruction,
        }
        return self._request_json(
            name="session_review_guardrail_retry",
            schema=schema,
            phase="REVIEW",
            active_triggers=[],
            conversation_history=[],
            user_payload=retry_context,
        )

    def _request_json(
        self,
        name: str,
        schema: dict[str, object],
        phase: LearningPhase,
        active_triggers: Collection[Trigger | str],
        conversation_history: list[ConversationMessage],
        user_payload: dict[str, object],
    ) -> dict[str, object]:
        request_payload = {"component": name, **user_payload}
        prompt_metadata = build_openai_tutor_prompt_metadata(
            phase=phase,
            active_triggers=active_triggers,
            session_context=request_payload,
        )
        request_content = json.dumps(
            request_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        messages = build_openai_tutor_messages(
            phase=phase,
            active_triggers=active_triggers,
            session_context=request_payload,
            conversation_history=[message.model_dump() for message in conversation_history],
            current_user_input=request_content,
        )
        request_body = {
            "model": self._model,
            "input": messages,
            "store": self._store_responses,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": name,
                    "schema": schema,
                    "strict": True,
                }
            },
        }
        if self._prompt_cache_key_enabled:
            cache_state = ":".join(
                [
                    prompt_metadata.prompt_version,
                    phase,
                    ",".join(prompt_metadata.canonical_triggers),
                ]
            )
            request_body["prompt_cache_key"] = sha256_text(cache_state)

        response, latency_ms = self._post_with_retries(request_body)

        if response.status_code != 200:
            raise AdapterError("openai_ai_engine", f"status={response.status_code} body={response.text}")

        try:
            response_payload = response.json()
            _log_openai_prompt_usage(
                component=name,
                model=self._model,
                phase=phase,
                prompt_metadata=prompt_metadata,
                response_payload=response_payload,
                latency_ms=latency_ms,
            )
            return json.loads(_extract_response_text(response_payload))
        except (TypeError, ValueError, KeyError, ValidationError) as error:
            raise AdapterError("openai_ai_engine", f"unparseable response: {error}; body={response.text}") from error

    def _post_with_retries(
        self,
        request_body: dict[str, object],
    ) -> tuple[httpx.Response, float]:
        last_error: httpx.HTTPError | None = None
        for attempt in range(self._retry_count + 1):
            try:
                with httpx.Client(timeout=self._timeout_seconds) as http_client:
                    started_at = perf_counter()
                    response = http_client.post(
                        _OPENAI_RESPONSES_URL,
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json=request_body,
                    )
                    latency_ms = (perf_counter() - started_at) * 1000
                if response.status_code < 500 or attempt == self._retry_count:
                    return response, latency_ms
                logger.warning(
                    "openai_request_retry",
                    extra={
                        "attempt": attempt + 1,
                        "status_code": response.status_code,
                        "response_body": response.text,
                    },
                )
            except httpx.HTTPError as error:
                last_error = error
                if attempt == self._retry_count:
                    break
                logger.warning(
                    "openai_request_retry",
                    extra={"attempt": attempt + 1, "error": str(error)},
                )

        if last_error is not None:
            raise AdapterError("openai_ai_engine", f"request failed: {last_error}") from last_error
        raise AdapterError("openai_ai_engine", "request failed without a response")


def extract_openai_usage_metrics(payload: object) -> OpenAIUsageMetrics:
    if not isinstance(payload, dict):
        return OpenAIUsageMetrics(
            cached_tokens=0,
            cache_write_tokens=0,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
        )

    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return OpenAIUsageMetrics(
            cached_tokens=0,
            cache_write_tokens=0,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
        )

    token_details = usage.get("prompt_tokens_details")
    if not isinstance(token_details, dict):
        token_details = usage.get("input_tokens_details")
    if not isinstance(token_details, dict):
        token_details = {}

    return OpenAIUsageMetrics(
        cached_tokens=_optional_int(token_details.get("cached_tokens")) or 0,
        cache_write_tokens=_optional_int(token_details.get("cache_write_tokens")) or 0,
        input_tokens=_optional_int(usage.get("input_tokens")) or _optional_int(usage.get("prompt_tokens")),
        output_tokens=_optional_int(usage.get("output_tokens")) or _optional_int(usage.get("completion_tokens")),
        total_tokens=_optional_int(usage.get("total_tokens")),
    )


def build_openai_prompt_usage_log_metadata(
    model: str,
    phase: LearningPhase,
    prompt_metadata: OpenAITutorPromptMetadata,
    response_payload: object,
    latency_ms: float,
) -> dict[str, object]:
    usage = extract_openai_usage_metrics(response_payload)
    request_id = response_payload.get("id") if isinstance(response_payload, dict) else None

    return {
        "request_id": request_id if isinstance(request_id, str) else None,
        "provider": "openai",
        "model": model,
        "prompt_version": prompt_metadata.prompt_version,
        "phase": phase,
        "canonical_triggers": prompt_metadata.canonical_triggers,
        "diagnostic_layer1_sha256": prompt_metadata.layer1_hash,
        "diagnostic_semi_static_sha256": prompt_metadata.semi_static_hash,
        "layer1_character_count": prompt_metadata.layer1_character_count,
        "semi_static_character_count": prompt_metadata.semi_static_character_count,
        "session_context_character_count": prompt_metadata.session_context_character_count,
        "cached_tokens": usage.cached_tokens,
        "cache_write_tokens": usage.cache_write_tokens,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
        "latency_ms": round(latency_ms, 3),
    }


def _log_openai_prompt_usage(
    component: str,
    model: str,
    phase: LearningPhase,
    prompt_metadata: OpenAITutorPromptMetadata,
    response_payload: object,
    latency_ms: float,
) -> None:
    logger.info(
        "openai_prompt_cache_usage",
        extra={
            "component": component,
            **build_openai_prompt_usage_log_metadata(
                model=model,
                phase=phase,
                prompt_metadata=prompt_metadata,
                response_payload=response_payload,
                latency_ms=latency_ms,
            ),
        },
    )


def _optional_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    return None


def _extract_response_text(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ValueError("OpenAI response body must be an object")

    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        return output_text

    output = payload.get("output")
    if isinstance(output, list):
        for output_item in output:
            if not isinstance(output_item, dict):
                continue
            content = output_item.get("content")
            if not isinstance(content, list):
                continue
            for content_item in content:
                if not isinstance(content_item, dict):
                    continue
                text = content_item.get("text")
                if isinstance(text, str):
                    return text

    choices = payload.get("choices")
    if isinstance(choices, list) and len(choices) > 0 and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]

    raise ValueError("OpenAI response did not contain text output")
