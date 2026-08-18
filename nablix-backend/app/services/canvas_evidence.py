from dataclasses import dataclass, field
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
    canonical_math_token_text,
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
    # Ordered per-page data, page 1 first. Single-page submissions carry one
    # entry each; both are consumed when building the work artifact (PDF +
    # per-page OCR) for Phase 4 review.
    page_ocr_texts: list[str] = field(default_factory=list)
    page_data_urls: list[str] = field(default_factory=list)


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
    return canonical_math_token_text(
        "".join(token.text for token in parse_mathml_tokens(mathml))
    )


def _with_confirmed_mathml_regions(ocr: VisionOCRResult) -> VisionOCRResult:
    """Attach each MathML block only to its unique matching OCR region."""

    available_blocks: set[int] = set(range(len(ocr.mathml_blocks)))
    regions: list[OCRTextRegion] = []
    for region in ocr.detected_regions:
        region_text = canonical_math_token_text(region.text)
        matching_blocks = [
            index
            for index in available_blocks
            if _normalised_mathml_tokens(ocr.mathml_blocks[index]) == region_text
        ]
        if len(matching_blocks) == 1:
            block_index = matching_blocks[0]
            available_blocks.remove(block_index)
            regions.append(
                region.model_copy(update={"mathml": ocr.mathml_blocks[block_index]})
            )
        else:
            regions.append(region)
    return ocr.model_copy(update={"detected_regions": regions})


def _word_regions_within(
    word_regions: list[OCRTextRegion],
    step_region: OCRTextRegion,
) -> list[OCRTextRegion]:
    """Return the word boxes whose vertical centre sits inside this step line."""

    inside = [
        word
        for word in word_regions
        if step_region.y <= word.y + word.h / 2 <= step_region.y + step_region.h
    ]
    return sorted(inside, key=lambda word: word.x)


async def collect_canvas_evidence(
    snapshot_data_url: str,
    strokes: list[CanvasStroke],
    submission_id: str,
    vision: VisionOCRAdapter,
    additional_pages: list[str] | None = None,
) -> CanvasEvidence:
    settings = get_settings()
    pages = [snapshot_data_url, *(additional_pages or [])]
    for page in pages:
        if len(page) > settings.max_snapshot_bytes:
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
                _word_regions_within(ocr.word_regions, region),
            )
        )
    # Pages 2..N: OCR each in order and keep the text only. Structural analysis
    # (regions, spatial tokens) stays page-1-only because strokes belong to the
    # live canvas. Never stitch pages into one tall image before OCR.
    page_ocr_texts = [ocr.raw_ocr_text]
    for page in pages[1:]:
        page_ocr_texts.append((await vision.recognize(page)).raw_ocr_text)

    if len(pages) > 1:
        ocr = ocr.model_copy(
            update={"raw_ocr_text": "\n".join(page_ocr_texts)}
        )

    return CanvasEvidence(
        submission_id=submission_id,
        snapshot_reference=snapshot_reference,
        ocr=ocr,
        spatial_tokens=spatial_tokens,
        ocr_latency_ms=(perf_counter() - started) * 1000,
        page_ocr_texts=page_ocr_texts,
        page_data_urls=pages,
    )
