from functools import lru_cache
from pathlib import Path
import re

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.ai_engine.classifier import (
    build_openai_ai_engine_client, check_student_message_safety, is_low_confidence,
)
from app.ai_engine.classifier_config import load_classifier_rules
from app.core.config import get_settings
from app.core.exceptions import AdapterError
from app.core.logger import logger
from app.models.adapters import ConversationMessage
from app.models.teach_back import TeachBackAction, TeachBackEvaluation, TeachBackPayload, TeachBackReply


class TeachBackRealtimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    model: str
    transcription_model: str
    client_secret_url: str
    calls_url: str
    token_lifetime_seconds: int = Field(ge=10, le=600)
    response_timeout_seconds: int = Field(ge=5, le=120)
    tool_name: str
    tool_description: str
    transport_instructions: str


class TeachBackConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    realtime: TeachBackRealtimeConfig
    max_failed_explanations: int = Field(ge=1)
    opening_message: str
    return_to_orientation_message: str
    voice_clarification_message: str
    acknowledgement_message: str
    completion_message: str
    forbidden_student_text_patterns: list[str]
    non_explanation_patterns: list[str]


@lru_cache(maxsize=1)
def load_teach_back_config() -> TeachBackConfig:
    path = Path(__file__).resolve().parents[2] / "configs" / "teach_back_tutor.yaml"
    return TeachBackConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def teach_back_action(content: TeachBackPayload, verdict: str | None) -> TeachBackAction:
    state = content.state
    if verdict == "UNDERSTOOD":
        remaining = set(state.target_micro_skill_ids) - set(state.completed_micro_skill_ids)
        return "NEXT_MICRO_SKILL" if len(remaining) > 1 else "MOVE_TO_PHASE_2"
    if verdict == "MISCONCEPTION":
        count = state.failed_explanation_count
        if count is None:
            if state.status != "NOT_STARTED":
                raise AdapterError("teach_back", "Student Model omitted failed_explanation_count for an active run.")
            count = 0
        return ("RETURN_TO_ORIENTATION" if count + 1 >= load_teach_back_config().max_failed_explanations
                else "ASK_REEXPLANATION")
    return "ASK_TEACH_BACK"


def validate_teach_back_content(content: TeachBackPayload) -> None:
    state = content.state
    if content.teach_back_id != state.teach_back_id:
        raise AdapterError("teach_back", "Teach-Back payload and state identify different runs.")
    current = state.current_micro_skill_id
    target = next((t for t in content.targets if t.micro_skill_id == current), None)
    if target is None or content.phase1_context is None or content.worked_example_context is None:
        raise AdapterError("teach_back", "Current target or teaching context is missing.")
    if not target.expected_concept.strip() or not target.micro_skill_definition.strip():
        raise AdapterError("teach_back", "Current target has an empty expected concept or definition.")
    if not any(s.micro_skill_id == current and s.skill_name.strip() for s in content.phase1_context.teaching_summary):
        raise AdapterError("teach_back", "Current target is missing its teaching summary and name.")
    if current not in content.phase1_context.taught_micro_skill_ids:
        raise AdapterError("teach_back", "Current target was not taught during orientation.")
    completed = set(content.phase1_context.completed_content_ids.worked_example_ids)
    if not any(e.worked_example_id in completed and current in e.covered_micro_skill_ids
               for e in content.worked_example_context.worked_examples):
        raise AdapterError("teach_back", "No completed worked example covers the current target.")
    if state.status != "NOT_STARTED" and state.failed_explanation_count is None:
        raise AdapterError("teach_back", "Student Model omitted the persisted failure count.")


def validate_teach_back_reply(content: TeachBackPayload, reply: TeachBackReply) -> None:
    verdict = reply.evaluation.understanding_status
    required = teach_back_action(content, verdict)
    if verdict is None:
        if reply.next_action not in {"ASK_TEACH_BACK", "DISCUSS_AND_CLARIFY", "ASK_REEXPLANATION"}:
            raise ValueError("A discussion turn cannot complete a skill or change phase.")
    elif reply.next_action != required:
        raise ValueError(f"Backend progress requires {required}, received {reply.next_action}.")
    target = next(t for t in content.targets if t.micro_skill_id == content.state.current_micro_skill_id)
    codes = {m.error_code for m in target.known_misconceptions}
    if reply.evaluation.error_code is not None and reply.evaluation.error_code not in codes:
        raise ValueError("The error code is not in the current skill's misconception catalogue.")
    identifiers = [content.teach_back_id, *content.state.target_micro_skill_ids,
                   *[s.question_id for t in content.targets for s in t.source_diagnostic_questions],
                   *[s.question_usage_id for t in content.targets for s in t.source_diagnostic_questions if s.question_usage_id],
                   *[m.error_code for t in content.targets for m in t.known_misconceptions]]
    forbidden = [*identifiers, *load_teach_back_config().forbidden_student_text_patterns]
    for text in (reply.tutor_message, reply.tutor_message_voice):
        if any(value.lower() in text.lower() for value in forbidden if value):
            raise ValueError("Teach-Back reply exposes an internal reference.")
        if text.count("?") > 1:
            raise ValueError("Teach-Back reply must ask at most one question.")
        if reply.next_action == "NEXT_MICRO_SKILL" and text.count("?") != 1:
            raise ValueError("NEXT_MICRO_SKILL must ask one conceptual question about the next target.")
        if reply.next_action in {"MOVE_TO_PHASE_2", "RETURN_TO_ORIENTATION"} and "?" in text:
            raise ValueError("A phase transition must not ask another Teach-Back question.")
        if not check_student_message_safety(text, load_classifier_rules()).passed:
            raise ValueError("Teach-Back reply failed the existing safety check.")


def teach_back_input_reply(
    student_input: str, input_source: str, transcript_confidence: float | None,
) -> TeachBackReply | None:
    config = load_teach_back_config()
    rules = load_classifier_rules()
    clarification: str | None = None
    if not check_student_message_safety(student_input, rules).passed:
        clarification = rules.messages.SAFETY_RESPONSE
    elif input_source == "VOICE" and is_low_confidence(transcript_confidence, rules):
        clarification = config.voice_clarification_message
    elif (not student_input.strip() or student_input.strip().lower() in rules.conversation_rules.acknowledgement_phrases
          or any(re.fullmatch(pattern, student_input.strip(), flags=re.IGNORECASE) for pattern in config.non_explanation_patterns)):
        clarification = config.acknowledgement_message
    if clarification is not None:
        return TeachBackReply(
            evaluation=TeachBackEvaluation(understanding_status=None, misconception_detected=False,
                                          error_code=None, unmapped_misconception_description=None),
            tutor_message=clarification, tutor_message_voice=clarification, next_action="ASK_TEACH_BACK",
        )
    if any(phrase in student_input.lower() for phrase in rules.guided_learning.critical_thinking.distress_phrases):
        return TeachBackReply(
            evaluation=TeachBackEvaluation(understanding_status=None, misconception_detected=False,
                                          error_code=None, unmapped_misconception_description=None),
            tutor_message=rules.guided_learning.critical_thinking.distress_message,
            tutor_message_voice=rules.guided_learning.critical_thinking.distress_message, next_action="ASK_TEACH_BACK",
        )
    return None


def build_teach_back_context(
    content: TeachBackPayload, student_input: str, input_source: str,
    transcript_confidence: float | None,
) -> dict[str, object]:
    current = next(t for t in content.targets if t.micro_skill_id == content.state.current_micro_skill_id)
    next_target = next((t for t in content.targets if t.micro_skill_id != current.micro_skill_id
                        and t.micro_skill_id not in content.state.completed_micro_skill_ids), None)
    return {
        "current_target": current.model_dump(),
        "next_target": next_target.model_dump() if next_target is not None else None,
        "phase1_context": content.phase1_context.model_dump(),
        "worked_example_context": content.worked_example_context.model_dump(),
        "conversation_mode": content.state.conversation_mode,
        "student_input": student_input,
        "input_requires_clarification": teach_back_input_reply(student_input, input_source, transcript_confidence) is not None,
        "input_source": input_source,
        "transcript_confidence": transcript_confidence,
        "required_actions": {v: teach_back_action(content, v) for v in ("UNDERSTOOD", "MISCONCEPTION")},
        "discussion_actions": ["ASK_TEACH_BACK", "DISCUSS_AND_CLARIFY", "ASK_REEXPLANATION"],
    }


def generate_teach_back_reply(
    content: TeachBackPayload,
    student_input: str,
    input_source: str,
    transcript_confidence: float | None,
    history: list[ConversationMessage],
) -> TeachBackReply:
    validate_teach_back_content(content)
    input_reply = teach_back_input_reply(student_input, input_source, transcript_confidence)
    if input_reply is not None:
        return input_reply
    rules = load_classifier_rules()
    settings = get_settings()
    client = build_openai_ai_engine_client(settings)
    if client is None:
        raise AdapterError("teach_back", "Teach-Back requires the configured AI engine and an API key.")
    context = build_teach_back_context(content, student_input, input_source, transcript_confidence)
    for attempt in range(settings.adapter_request_retry_count + 1):
        raw_reply = client.generate_teach_back(
            context, TeachBackReply.model_json_schema(), history[-rules.conversation_rules.max_recent_messages:] if rules.conversation_rules.max_recent_messages else []
        )
        try:
            reply = TeachBackReply.model_validate(raw_reply)
            validate_teach_back_reply(content, reply)
            return reply
        except (ValidationError, ValueError) as error:
            if attempt == settings.adapter_request_retry_count:
                raise AdapterError("teach_back", f"Invalid Teach-Back response: {error}; response={raw_reply}") from error
            logger.warning("teach_back_response_retry", extra={"attempt": attempt + 1, "reason": str(error), "response": raw_reply})
            context = {**context, "response_validation_error": str(error)}
            try:
                evaluation = TeachBackEvaluation.model_validate(raw_reply.get("evaluation"))
            except ValidationError:
                continue
            if evaluation.understanding_status is not None:
                context = {**context, "required_response_action": teach_back_action(content, evaluation.understanding_status)}
    raise AdapterError("teach_back", "Teach-Back response retry count must be nonnegative.")
