from __future__ import annotations

import json
from collections.abc import Collection

import httpx
from pydantic import Field, ValidationError

from app.ai_engine.prompt_registry import (
    Trigger,
    build_openai_tutor_messages,
    build_openai_tutor_prompt_metadata,
    sha256_text,
)
from app.ai_engine.schemas import ErrorType, EvaluationCategory, LearningPhase, StrictSchema
from app.core.exceptions import AdapterError


_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


class OpenAIAnswerEvaluation(StrictSchema):
    evaluation: EvaluationCategory
    confidence: float = Field(ge=0.0, le=1.0)


class OpenAIErrorDiagnosis(StrictSchema):
    error_type: ErrorType
    error_description: str
    confidence: float = Field(ge=0.0, le=1.0)


class OpenAITutorMessage(StrictSchema):
    tutor_message: str
    tutor_message_voice_optimised: str
    confidence: float = Field(ge=0.0, le=1.0)


class OpenAIAIEngineClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: int,
        prompt_cache_key_enabled: bool,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._prompt_cache_key_enabled = prompt_cache_key_enabled

    def evaluate_answer(
        self,
        question: str,
        correct_answer: str,
        student_input: str,
        phase: LearningPhase,
    ) -> OpenAIAnswerEvaluation:
        schema = OpenAIAnswerEvaluation.model_json_schema()
        content = self._request_json(
            name="answer_evaluation",
            schema=schema,
            phase=phase,
            active_triggers=[],
            user_payload={
                "question": question,
                "correct_answer": correct_answer,
                "student_input": student_input,
            },
        )
        return OpenAIAnswerEvaluation.model_validate(content)

    def diagnose_error(
        self,
        question: str,
        correct_answer: str,
        student_input: str,
        phase: LearningPhase,
    ) -> OpenAIErrorDiagnosis:
        schema = OpenAIErrorDiagnosis.model_json_schema()
        content = self._request_json(
            name="error_diagnosis",
            schema=schema,
            phase=phase,
            active_triggers=[],
            user_payload={
                "question": question,
                "correct_answer": correct_answer,
                "student_input": student_input,
            },
        )
        return OpenAIErrorDiagnosis.model_validate(content)

    def build_tutor_message(
        self,
        question: str,
        student_input: str,
        evaluation: EvaluationCategory | None,
        error_type: ErrorType | None,
        response_strategy: str,
        hint_level: int | None,
        phase: LearningPhase,
    ) -> OpenAITutorMessage:
        schema = OpenAITutorMessage.model_json_schema()
        content = self._request_json(
            name="tutor_message",
            schema=schema,
            phase=phase,
            active_triggers=[],
            user_payload={
                "question": question,
                "student_input": student_input,
                "evaluation": evaluation,
                "error_type": error_type,
                "response_strategy": response_strategy,
                "hint_level": hint_level,
            },
        )
        return OpenAITutorMessage.model_validate(content)

    def _request_json(
        self,
        name: str,
        schema: dict[str, object],
        phase: LearningPhase,
        active_triggers: Collection[Trigger | str],
        user_payload: dict[str, object],
    ) -> dict[str, object]:
        request_payload = {"component": name, **user_payload}
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
            conversation_history=[],
            current_user_input=request_content,
        )
        request_body = {
            "model": self._model,
            "input": messages,
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
            metadata = build_openai_tutor_prompt_metadata(
                phase=phase,
                active_triggers=active_triggers,
                session_context=request_payload,
            )
            canonical_trigger_hash = sha256_text(",".join(metadata.canonical_triggers))
            request_body["prompt_cache_key"] = (
                f"ai_tutor:{metadata.prompt_version}:{phase}:{canonical_trigger_hash}"
            )

        try:
            with httpx.Client(timeout=self._timeout_seconds) as http_client:
                response = http_client.post(
                    _OPENAI_RESPONSES_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=request_body,
                )
        except httpx.HTTPError as error:
            raise AdapterError("openai_ai_engine", f"request failed: {error}") from error

        if response.status_code != 200:
            raise AdapterError("openai_ai_engine", f"status={response.status_code} body={response.text}")

        try:
            return json.loads(_extract_response_text(response.json()))
        except (TypeError, ValueError, KeyError, ValidationError) as error:
            raise AdapterError("openai_ai_engine", f"unparseable response: {error}; body={response.text}") from error


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
