from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.adapters.http_utils import post_json
from app.ai_engine.prompt_registry import build_openai_tutor_messages
from app.ai_engine.teach_back import build_teach_back_context, load_teach_back_config, validate_teach_back_content
from app.core.config import get_settings
from app.models.teach_back_realtime import TeachBackRealtimeContext, TeachBackRealtimeReply, TeachBackRealtimeSession, TeachBackRealtimeStart
from app.services.interaction_service import recover_session_for_read
from app.services.session_service import require_learning_active, require_teach_back_recovered


class RealtimeClientSecret(BaseModel):
    value: str = Field(min_length=1)


async def realtime_teach_back_context(
    request: TeachBackRealtimeStart, access_token: str,
) -> TeachBackRealtimeContext:
    config = load_teach_back_config()
    if not config.realtime.enabled:
        raise HTTPException(status_code=409, detail="Realtime Teach-Back is disabled in teach_back_tutor.yaml.")
    session = await recover_session_for_read(request.session_id, request.student_id, access_token)
    require_learning_active(session)
    require_teach_back_recovered(session)
    content = session.teach_back_content
    if session.current_phase != "TEACH_BACK" or content is None:
        raise HTTPException(status_code=409, detail="Realtime voice is only available during Teach-Back.")
    validate_teach_back_content(content)
    current = content.state.current_micro_skill_id
    if current is None:
        raise HTTPException(status_code=409, detail="Teach-Back has no unfinished target.")
    context = build_teach_back_context(content, "", "VOICE", None)
    # The student utterance arrives over the audio connection after this context is issued.
    context.pop("student_input")
    context.pop("input_requires_clarification")
    last = content.state.last_tutor_response
    context["recent_history"] = [{"role": "assistant", "content": last.tutor_response}] if last is not None else []
    context["completed_micro_skill_ids"] = list(content.state.completed_micro_skill_ids)
    context["completed_concepts"] = [{"micro_skill_id": target.micro_skill_id, "expected_concept": target.expected_concept}
                                     for target in content.targets if target.micro_skill_id in content.state.completed_micro_skill_ids]
    context["teach_back_rules"] = config.model_dump(exclude={"realtime", "evaluation_instructions"})
    messages = build_openai_tutor_messages("TEACH_BACK", [], context, [], "")
    instructions = "\n\n".join(message["content"] for message in messages if message["role"] == "system")
    instructions += "\n" + config.realtime.transport_instructions
    schema = TeachBackRealtimeReply.model_json_schema()
    schema["properties"] = {"student_evidence": schema["properties"]["student_evidence"],
                            **{name: value for name, value in schema["properties"].items() if name != "student_evidence"}}
    schema["required"] = ["student_evidence", *[name for name in schema["required"] if name != "student_evidence"]]
    target = next(target for target in content.targets if target.micro_skill_id == current)
    schema["$defs"]["TeachBackEvaluation"]["properties"]["error_code"] = {
        "enum": [None, *[misconception.error_code for misconception in target.known_misconceptions]],
        "description": "Use only a supplied current-target code when the quoted student claim matches it; otherwise null and describe the explicit unmapped claim.",
    }
    schema["properties"]["next_action"]["enum"] = list(dict.fromkeys([
        *context["discussion_actions"], *context["required_actions"].values(),
    ]))
    schema["properties"]["next_action"]["description"] = f"Copy the current verdict's required action exactly: {context['required_actions']}. Discussion actions apply only to a null verdict."
    return TeachBackRealtimeContext(instructions=instructions, teach_back_id=content.teach_back_id,
                                    micro_skill_id=current, tool_name=config.realtime.tool_name,
                                    tool_description=config.realtime.tool_description, tool_parameters=schema)


async def start_realtime_teach_back(
    request: TeachBackRealtimeStart, access_token: str,
) -> TeachBackRealtimeSession:
    context = await realtime_teach_back_context(request, access_token)
    config = load_teach_back_config().realtime
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="Configure NABLIX_OPENAI_API_KEY before starting Realtime Teach-Back.")
    body = await post_json(
        "teach_back_realtime", config.client_secret_url,
        {"expires_after": {"anchor": "created_at", "seconds": config.token_lifetime_seconds},
         "session": {"type": "realtime", "model": config.model, "instructions": context.instructions,
                     "output_modalities": ["text"], "include": ["item.input_audio_transcription.logprobs"],
                     "audio": {"input": {"transcription": {"model": config.transcription_model}, "turn_detection": None}},
                     "tools": [{"type": "function", "name": config.tool_name,
                                "description": context.tool_description, "parameters": context.tool_parameters}],
                     "tool_choice": {"type": "function", "name": config.tool_name}}},
        {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
        settings.openai_request_timeout_seconds, settings.adapter_request_retry_count,
    )
    secret = RealtimeClientSecret.model_validate(body)
    return TeachBackRealtimeSession(client_secret=secret.value, calls_url=config.calls_url,
                                   response_timeout_seconds=config.response_timeout_seconds,
                                   request_retry_count=settings.adapter_request_retry_count, context=context)
