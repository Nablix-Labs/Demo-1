from dataclasses import dataclass
from time import perf_counter

from fastapi import HTTPException

from app.adapters.base import VisionOCRAdapter
from app.core.config import get_settings
from app.models.adapters import OCRTextRegion, SpatialMathToken, VisionOCRResult
from app.models.canvas import CanvasStroke
from app.models.canvas_memory import CanvasEvent
from app.services.canvas_annotations import assign_step_ids
from app.services.canvas_spatial import (
    align_step_tokens,
    associate_strokes_with_steps,
    parse_mathml_tokens,
)
from app.services.snapshot_store import build_reference, store_snapshot


MAX_CANVAS_STROKE_POINTS = 10_000
MAX_CANVAS_EVENTS = 500


@dataclass(frozen=True)
class CanvasEvidence:
    submission_id: str
    snapshot_reference: str
    ocr: VisionOCRResult
    spatial_tokens: list[SpatialMathToken]
    ocr_latency_ms: float


def validate_canvas_payload(
    strokes: list[CanvasStroke],
    canvas_events: list[CanvasEvent],
) -> None:
    stroke_points = sum(len(stroke.points) for stroke in strokes)
    if stroke_points > MAX_CANVAS_STROKE_POINTS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Canvas strokes contain {stroke_points} points; "
                f"the limit is {MAX_CANVAS_STROKE_POINTS}."
            ),
        )
    if len(canvas_events) > MAX_CANVAS_EVENTS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Canvas events contain {len(canvas_events)} entries; "
                f"the limit is {MAX_CANVAS_EVENTS}."
            ),
        )


def canvas_events_are_stale(
    canvas_events: list[CanvasEvent],
    active_question_id: str | None,
) -> bool:
    question_ids = {
        event.question_id for event in canvas_events if event.question_id is not None
    }
    return bool(question_ids) and question_ids != {active_question_id}


def _normalised_mathml_tokens(mathml: str) -> str:
    return "".join(token.text for token in parse_mathml_tokens(mathml)).replace(
        " ", ""
    )


def _with_confirmed_mathml_regions(ocr: VisionOCRResult) -> VisionOCRResult:
    """Attach MathML only when Mathpix returned one unambiguous block per line."""

    if len(ocr.mathml_blocks) != len(ocr.detected_regions):
        return ocr
    regions: list[OCRTextRegion] = []
    for region, mathml in zip(ocr.detected_regions, ocr.mathml_blocks):
        if _normalised_mathml_tokens(mathml) != region.text.replace(" ", ""):
            return ocr
        regions.append(region.model_copy(update={"mathml": mathml}))
    return ocr.model_copy(update={"detected_regions": regions})


async def collect_canvas_evidence(
    snapshot_data_url: str,
    strokes: list[CanvasStroke],
    submission_id: str,
    vision: VisionOCRAdapter,
) -> CanvasEvidence:
    settings = get_settings()
    if len(snapshot_data_url) > settings.max_snapshot_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Canvas snapshot exceeds the {settings.max_snapshot_bytes} byte limit.",
        )

    snapshot_reference = build_reference(submission_id)
    store_snapshot(snapshot_reference, snapshot_data_url)
    started = perf_counter()
    ocr = await vision.recognize(snapshot_data_url)
    ocr = ocr.model_copy(
        update={"detected_regions": assign_step_ids(ocr.detected_regions)}
    )
    ocr = _with_confirmed_mathml_regions(ocr)
    strokes_by_step = associate_strokes_with_steps(strokes, ocr.detected_regions)
    spatial_tokens: list[SpatialMathToken] = []
    for region in ocr.detected_regions:
        if region.step_id is None or region.mathml is None:
            continue
        spatial_tokens.extend(
            align_step_tokens(
                region.step_id,
                region.mathml,
                region.text,
                strokes_by_step.get(region.step_id, []),
                region,
            )
        )
    return CanvasEvidence(
        submission_id=submission_id,
        snapshot_reference=snapshot_reference,
        ocr=ocr,
        spatial_tokens=spatial_tokens,
        ocr_latency_ms=(perf_counter() - started) * 1000,
    )
