from __future__ import annotations

import json

import httpx
from pydantic import Field, ValidationError

from app.ai_engine.schemas import ErrorType, EvaluationCategory, StrictSchema
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
    def __init__(self, api_key: str, model: str, timeout_seconds: int) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds

    def evaluate_answer(
        self,
        question: str,
        correct_answer: str,
        student_input: str,
    ) -> OpenAIAnswerEvaluation:
        schema = OpenAIAnswerEvaluation.model_json_schema()
        content = self._request_json(
            name="answer_evaluation",
            schema=schema,
            system_prompt=(
                "You are the answer evaluation component inside the AI Tutor Response Engine. "
                "Your only job is to classify the student's algebra answer. Do not generate "
                "a tutor message. Do not diagnose the error type. Do not reveal the correct "
                "answer to the student. Use only one evaluation value: CORRECT, "
                "PARTIALLY_CORRECT, INCORRECT, UNCLEAR, NO_ATTEMPT, or IRRELEVANT. "
                "Choose CORRECT when the final answer and shown method are correct. "
                "Choose PARTIALLY_CORRECT when at least one correct method step is visible "
                "but execution is wrong or incomplete. Choose INCORRECT when the answer is "
                "mathematically wrong and no correct step is visible. Choose UNCLEAR when "
                "the input is ambiguous. Choose NO_ATTEMPT when no math answer is provided. "
                "Choose IRRELEVANT when the response is off topic. If unclear, choose "
                "UNCLEAR and do not guess. Output JSON only, no markdown, no extra text."
            ),
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
    ) -> OpenAIErrorDiagnosis:
        schema = OpenAIErrorDiagnosis.model_json_schema()
        content = self._request_json(
            name="error_diagnosis",
            schema=schema,
            system_prompt=(
                "You are the error diagnosis component inside the AI Tutor Response Engine. "
                "Your only job is to classify the main student error and give a short "
                "diagnostic description for downstream response strategy selection. Do not "
                "generate a student-facing tutor message. Do not reveal the final answer as "
                "advice to the student. Use only approved error_type values: "
                "ARITHMETIC_ERROR, SIGN_ERROR, OPPOSITE_OPERATION_ERROR, "
                "CONCEPTUAL_MISUNDERSTANDING, PROCEDURAL_ERROR, NOTATION_ISSUE, "
                "INSUFFICIENT_INFORMATION, UNKNOWN_ERROR. If the value is correct but the "
                "format is wrong, use NOTATION_ISSUE. If there is too little information to "
                "diagnose, use INSUFFICIENT_INFORMATION. If a specific approved type fits, "
                "do not use UNKNOWN_ERROR. Keep error_description short and factual. Do not "
                "include hidden reasoning or chain-of-thought. Output JSON only, no markdown, "
                "no extra text."
            ),
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
    ) -> OpenAITutorMessage:
        schema = OpenAITutorMessage.model_json_schema()
        content = self._request_json(
            name="tutor_message",
            schema=schema,
            system_prompt=(
                "You are the tutor message component inside the AI Tutor Response Engine. "
                "Write one short student-facing message for ages 11-14 and one natural "
                "voice-optimised version. Follow the response strategy exactly. Do not give "
                "the final answer. Do not complete all solution steps. Do not include hidden "
                "reasoning or chain-of-thought. If evaluation is CORRECT and response_strategy "
                "is CONFIRM_CORRECT, only confirm that the student's answer or method is "
                "correct. Do not ask the student to solve the same question again. Do not ask "
                "what x equals. If response_strategy is GUIDED_HINT, give a hint based on "
                "hint_level without calculating the final answer. If response_strategy is "
                "CLARIFY, ask for clarification or redirect safely. Keep voice wording short "
                "and easy to say aloud. Output JSON only, no markdown, no extra text."
            ),
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
        system_prompt: str,
        user_payload: dict[str, object],
    ) -> dict[str, object]:
        request_body = {
            "model": self._model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": name,
                    "schema": schema,
                    "strict": True,
                }
            },
        }

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
