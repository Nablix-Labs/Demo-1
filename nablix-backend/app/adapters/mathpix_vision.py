"""Mathpix implementation of the `VisionOCRAdapter` protocol."""

import re

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.exceptions import AdapterError
from app.models.adapters import OCRTextRegion, VisionOCRResult

_MATHPIX_TEXT_URL = "https://api.mathpix.com/v3/text"
_ARRAY_BLOCK = re.compile(
    r"\\begin\{array\}\{[^{}]+\}(.*?)\\end\{array\}",
    flags=re.DOTALL,
)


class _MathpixLineData(BaseModel):
    text: str | None = None
    cnt: list[list[float]] = Field(default_factory=list)
    confidence: float | None = None
    conversion_output: bool | None = None


class _MathpixOCRPayload(BaseModel):
    text: str = ""
    latex_styled: str | None = None
    confidence: float | None = None
    confidence_rate: float | None = None
    line_data: list[_MathpixLineData] = Field(default_factory=list)
    image_width: int | None = None
    image_height: int | None = None
    error: str | None = None
    error_info: object | None = None


class MathpixVisionOCRAdapter:
    """Recognize handwritten math from a snapshot via Mathpix image OCR."""

    def __init__(
        self,
        app_id: str,
        app_key: str,
        timeout_seconds: int,
        min_confidence: float,
    ) -> None:
        self._app_id = app_id
        self._app_key = app_key
        self._timeout_seconds = timeout_seconds
        self._min_confidence = min_confidence

    async def recognize(self, snapshot_data_url: str) -> VisionOCRResult:
        """Call Mathpix OCR and normalize its line geometry into `VisionOCRResult`."""

        request_body: dict[str, object] = {
            "src": snapshot_data_url,
            "include_line_data": True,
            "rm_spaces": True,
        }
        headers: dict[str, str] = {
            "app_id": self._app_id,
            "app_key": self._app_key,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as http_client:
                response = await http_client.post(_MATHPIX_TEXT_URL, headers=headers, json=request_body)
        except httpx.HTTPError as error:
            raise AdapterError("mathpix_vision", f"request failed: {error}") from error

        if response.status_code != 200:
            raise AdapterError("mathpix_vision", f"status={response.status_code} body={response.text}")

        try:
            payload = _MathpixOCRPayload.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise AdapterError("mathpix_vision", f"unparseable response: {error}; body={response.text}") from error

        if payload.error is not None or payload.error_info is not None:
            raise AdapterError(
                "mathpix_vision",
                f"error={payload.error} error_info={payload.error_info}",
            )

        steps = _steps_for(payload)
        regions = _regions_for(payload, steps)
        detected_steps = [region.text for region in regions]
        raw_text = "\n".join(detected_steps) if detected_steps else payload.text
        confidence = _confidence_for(payload)
        return VisionOCRResult(
            raw_ocr_text=raw_text,
            detected_equation=detected_steps[0] if detected_steps else payload.text,
            detected_steps=detected_steps,
            detected_regions=regions,
            final_answer=detected_steps[-1] if detected_steps else None,
            confidence=confidence,
            needs_clarification=(
                confidence < self._min_confidence
                or _contains_incomplete_equation(detected_steps)
            ),
            latex=payload.latex_styled or payload.text,
            detected_shapes=[],
            confidence_source="ocr_native",
            provider="mathpix",
        )


def _steps_for(payload: _MathpixOCRPayload) -> list[str]:
    source = payload.latex_styled or payload.text
    array_match = _ARRAY_BLOCK.search(source)
    if array_match is not None:
        content = array_match.group(1)
        return [_clean_math_text(step) for step in content.split("\\\\") if _clean_math_text(step)]

    usable_lines = [line for line in payload.line_data if _has_text_and_contour(line)]
    if usable_lines:
        return [_clean_math_text(line.text or "") for line in usable_lines]
    return [_clean_math_text(payload.text)] if payload.text else []


def _regions_for(payload: _MathpixOCRPayload, steps: list[str]) -> list[OCRTextRegion]:
    if payload.image_width is None or payload.image_height is None:
        if payload.line_data:
            raise AdapterError("mathpix_vision", "line_data returned without image_width/image_height")
        return []
    if payload.image_width <= 0 or payload.image_height <= 0:
        raise AdapterError("mathpix_vision", "image_width/image_height must be positive")

    usable_lines = [line for line in payload.line_data if _has_text_and_contour(line)]
    regions = [_region_for(line, payload.image_width, payload.image_height) for line in usable_lines]
    if len(regions) == 1 and len(steps) > 1:
        return _split_region_by_steps(regions[0], steps)
    if len(regions) == len(steps):
        return [region.model_copy(update={"text": step}) for region, step in zip(regions, steps)]
    return regions


def _has_text_and_contour(line: _MathpixLineData) -> bool:
    return (
        line.conversion_output is not False
        and line.text is not None
        and len(line.text.strip()) > 0
        and len(line.cnt) > 0
    )


def _clean_math_text(text: str) -> str:
    return (
        text.replace("\\(", "")
        .replace("\\)", "")
        .replace("\\[", "")
        .replace("\\]", "")
        .replace("&", "")
        .strip()
    )


def _contains_incomplete_equation(steps: list[str]) -> bool:
    for step in steps:
        if step.count("=") != 1:
            continue
        left, right = step.split("=", maxsplit=1)
        if len(left.strip()) == 0 or len(right.strip()) == 0:
            return True
    return False


def _region_for(line: _MathpixLineData, image_width: int, image_height: int) -> OCRTextRegion:
    xs = [point[0] for point in line.cnt if len(point) >= 2]
    ys = [point[1] for point in line.cnt if len(point) >= 2]
    if not xs or not ys:
        raise AdapterError("mathpix_vision", f"line_data item has invalid cnt: {line.cnt}")

    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    confidence = line.confidence if line.confidence is not None else 0.0
    return OCRTextRegion(
        text=line.text or "",
        x=_unit(min_x / image_width),
        y=_unit(min_y / image_height),
        w=_unit((max_x - min_x) / image_width),
        h=_unit((max_y - min_y) / image_height),
        confidence=confidence,
    )


def _split_region_by_steps(region: OCRTextRegion, steps: list[str]) -> list[OCRTextRegion]:
    # ponytail: Mathpix image OCR can return one array box for several rows.
    # Split evenly for now; replace with frontend ink row boxes when precision matters.
    step_height = region.h / len(steps)
    return [
        region.model_copy(update={"text": step, "y": _unit(region.y + index * step_height), "h": step_height})
        for index, step in enumerate(steps)
    ]


def _confidence_for(payload: _MathpixOCRPayload) -> float:
    if payload.confidence is not None:
        return payload.confidence
    if payload.confidence_rate is not None:
        return payload.confidence_rate
    return 0.0


def _unit(value: float) -> float:
    return max(0.0, min(value, 1.0))
