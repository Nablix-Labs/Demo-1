"""OpenAI implementation of the `VisionOCRAdapter` protocol.

Uses the existing `httpx` dependency rather than the OpenAI SDK. The public
contract stays `VisionOCRResult`, so Gemini or Mathpix can replace this later by
implementing the same `recognize` method. Nothing in the services changes.

This adapter asks the model to transcribe visible math work, not solve it. The
normalization step maps OpenAI's JSON payload into the provider-neutral
`VisionOCRResult` used by canvas and interaction services.
"""

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.exceptions import AdapterError
from app.models.adapters import DetectedShape, OCRTextRegion, VisionOCRResult

_OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"

_SYSTEM_PROMPT = (
    "You are a verbatim OCR and structuring engine for student math canvases. "
    "Transcribe every visible line of student math work from top to bottom. "
    "Do not stop after the first equation or summarize the work. "
    "Do not solve the math, simplify expressions, correct arithmetic, or infer the intended answer. "
    "Your job is to copy what the student wrote, even when it is mathematically wrong. "
    "If a later line contradicts an earlier line, preserve the contradiction exactly as written. "
    "Read the image and return only JSON with these keys: "
    '"raw_ocr_text" (the full transcription as one string, exactly as written), '
    '"detected_equation" (the main/starting equation the student is working on, as written, or "" if none), '
    '"detected_steps" (a list of strings, one per visible line/step exactly as written), '
    '"detected_regions" (a list of text-line regions; [] if none), '
    '"final_answer" (the student\'s final written answer line such as "x = 5", or null if they wrote none; never compute it yourself), '
    '"latex" (LaTeX for the written math, or null if not applicable), '
    '"detected_shapes" (a list of geometry figures drawn on the canvas; [] if none), '
    '"confidence" (a float from 0.0 to 1.0 estimating how sure you are). '
    "If a final answer is visible but the written steps do not show how that answer was obtained, "
    "keep the transcription verbatim and lower confidence below 0.75 so the app can ask the student to explain their reasoning. "
    "Each detected_shapes item has: shape_type, label (or null), description, "
    "properties (visible cues such as parallel, perpendicular, right_angle, equal_sides, radius), "
    "and confidence (0.0 to 1.0). "
    "Only describe shapes that are visibly drawn. Do not infer a syllabus concept "
    "(e.g. the Pythagorean theorem) unless the image clearly shows it. "
    "Do not put shape descriptions into the text fields. "
    "For a shapes-only canvas with no written math, raw_ocr_text and detected_equation may be empty. "
    "Each detected_regions item has: text, x, y, w, h, confidence. "
    "x, y, w, and h are normalized 0.0 to 1.0 relative to the full image, where x/y are the top-left corner. "
    "Use one region per visible math line or text fragment. "
    "If handwriting is ambiguous, preserve the most visually likely reading and lower the confidence. "
    "Never replace an ambiguous or wrong-looking written value with the mathematically correct value. "
    "Read every digit and operator by its written stroke shape ALONE. The numeric value of an "
    "expression is irrelevant to transcription: never swap an operand for a different one that gives "
    "the same result. For example, '9 - 4' must NOT be transcribed as '7 - 2' just because both equal 5 "
    "— copy the digits that are actually drawn. "
    "Commonly confused handwritten characters: 1/7, 2/4, 3/5, 5/6, 6/0, 7/9, x/×. Tell them apart by their "
    "strokes, not by what would make the arithmetic look tidy (e.g. a 9 has a closed top loop with a tail; "
    "a 7 has a flat top and a single diagonal). "
    "When a character is genuinely unclear, pick the most stroke-faithful reading and set confidence below "
    "0.75 so it is flagged — do not guess a tidier or value-preserving alternative."
)


class _OpenAIOCRPayload(BaseModel):
    """The raw JSON shape we ask OpenAI to return, before normalization."""

    raw_ocr_text: str = ""
    detected_equation: str = ""
    detected_steps: list[str] = Field(default_factory=list)
    detected_regions: list[OCRTextRegion] = Field(default_factory=list)
    final_answer: str | None = None
    confidence: float
    latex: str | None = None
    detected_shapes: list[DetectedShape] = Field(default_factory=list)


def _raw_text_for(payload: _OpenAIOCRPayload) -> str:
    """Prefer explicit raw text, then rebuild it from detected step lines."""

    if payload.raw_ocr_text:
        return payload.raw_ocr_text
    return "\n".join(payload.detected_steps)


def _needs_reason_for_final_answer(payload: _OpenAIOCRPayload) -> bool:
    if payload.final_answer is None or len(payload.final_answer.strip()) == 0:
        return False

    visible_steps = [step for step in payload.detected_steps if step.strip()]
    return len(visible_steps) < 3


class OpenAIVisionOCRAdapter:
    """Recognize handwritten math from a snapshot via OpenAI vision."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: int,
        min_confidence: float,
    ) -> None:
        # Copy only the fields we need so the adapter doesn't pin the whole
        # Settings object for its lifetime.
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._min_confidence = min_confidence

    async def recognize(self, snapshot_data_url: str) -> VisionOCRResult:
        """Call OpenAI vision and normalize the model JSON into `VisionOCRResult`."""

        request_body = {
            "model": self._model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Return each visible math line in detected_steps exactly as written. "
                                "Do not use algebra to fix or complete any line. "
                                "Read each digit by its shape, not its arithmetic — do not change an operand "
                                "to a different value that gives the same result (e.g. 9-4 is not 7-2). "
                                "If a line is partially ambiguous, include the best visual reading and lower confidence."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": snapshot_data_url}},
                    ],
                },
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as http_client:
                response = await http_client.post(
                    _OPENAI_CHAT_COMPLETIONS_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=request_body,
                )
        except httpx.HTTPError as error:
            raise AdapterError("openai_vision", f"request failed: {error}") from error

        if response.status_code != 200:
            raise AdapterError(
                "openai_vision",
                f"status={response.status_code} body={response.text}",
            )

        try:
            content = response.json()["choices"][0]["message"]["content"]
            payload = _OpenAIOCRPayload.model_validate_json(content)
        except (KeyError, ValueError, ValidationError) as error:
            raise AdapterError(
                "openai_vision",
                f"unparseable response: {error}; body={response.text}",
            ) from error

        needs_clarification = (
            payload.confidence < self._min_confidence
            or any(shape.confidence < self._min_confidence for shape in payload.detected_shapes)
            or _needs_reason_for_final_answer(payload)
        )
        return VisionOCRResult(
            raw_ocr_text=_raw_text_for(payload),
            detected_equation=payload.detected_equation,
            detected_steps=payload.detected_steps,
            detected_regions=payload.detected_regions,
            final_answer=payload.final_answer,
            confidence=payload.confidence,
            needs_clarification=needs_clarification,
            latex=payload.latex,
            detected_shapes=payload.detected_shapes,
            confidence_source="model_estimated",
            provider="openai",
        )
