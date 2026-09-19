import asyncio
from dataclasses import dataclass, field
import re
from time import perf_counter
from typing import TYPE_CHECKING

from fastapi import HTTPException

from app.adapters.base import VisionOCRAdapter
from app.ai_engine.classifier import normalize_exact_notation
from app.core.config import get_settings
from app.models.adapters import OCRTextRegion, SpatialMathToken, VisionOCRResult
from app.models.canvas import CanvasStroke
from app.models.canvas_memory import CanvasEvent

if TYPE_CHECKING:
    from app.models.session import SessionRecord
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
    if additional_pages and len(additional_pages) > 4:
        raise HTTPException(
            status_code=422,
            detail="Exceeded maximum of 4 additional pages (5 pages total).",
        )
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
    semaphore = asyncio.Semaphore(3)

    async def _recognize_bounded(page: str) -> VisionOCRResult:
        async with semaphore:
            return await vision.recognize(page)

    page_results = await asyncio.gather(*(_recognize_bounded(page) for page in pages))
    ocr = page_results[0]
    ocr = ocr.model_copy(
        update={"detected_regions": assign_step_ids(ocr.detected_regions)}
    )
    ocr = _with_confirmed_mathml_regions(ocr)
    strokes_by_step = associate_strokes_with_steps(strokes, ocr.detected_regions)
    if strokes:
        # A region with no associated student stroke wasn't written by the
        # student — most often it's the tutor's own layer, captured into the
        # same snapshot. Drop it before it can be graded as an answer.
        # ponytail: filters region-derived text only. `latex` and
        # `mathml_blocks` stay whole-image; they don't reach `written_work`.
        # Filter them too if a tutor element ever shows up in a
        # MathML-grounded correction.
        kept_regions = [
            region
            for region in ocr.detected_regions
            if strokes_by_step.get(region.step_id or "", [])
        ]
        if len(kept_regions) != len(ocr.detected_regions):
            detected_steps = [region.text for region in kept_regions]
            ocr = ocr.model_copy(
                update={
                    "detected_regions": kept_regions,
                    "detected_steps": detected_steps,
                    # No stale fallback: when every region is dropped, the
                    # text fields must go empty too, not silently revert to
                    # the unfiltered (tutor-ink-included) originals.
                    "raw_ocr_text": "\n".join(detected_steps),
                    "detected_equation": detected_steps[0] if detected_steps else "",
                    "final_answer": detected_steps[-1] if detected_steps else None,
                }
            )
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
    page_ocr_texts = [
        ocr.raw_ocr_text,
        *(result.raw_ocr_text for result in page_results[1:]),
    ]
    if len(page_ocr_texts) > 1:
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


_SPOKEN_DIGITS: dict[str, str] = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
}

_EXPLICIT_ASSIGNMENT = re.compile(
    r"\b([A-Za-z])\s*=\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\b"
)
_SPOKEN_NUMERIC_ANSWER = re.compile(
    r"\b(?:got|answer\s*(?:=|is)?|solution\s*(?:=|is)?)\s*"
    r"(-?(?:\d+(?:\.\d*)?|\.\d+))\b",
    flags=re.IGNORECASE,
)


def normalize_voice_transcript(transcript: str) -> str:
    normalized = " ".join(transcript.split())
    for word, digit in _SPOKEN_DIGITS.items():
        normalized = re.sub(rf"\b{word}\b", digit, normalized, flags=re.IGNORECASE)
    normalized = re.sub(
        r"\b(?:is\s+)?equals?\s+to\b",
        "=",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\bequals?\b", "=", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s*=\s*", " = ", normalized)
    return " ".join(normalized.split())


def spoken_answer_conflicts_with_canvas(
    student_message: str,
    canvas_final_answer: str | None,
) -> bool:
    """Detect a plainly stated numeric answer that disagrees with the board."""

    if canvas_final_answer is None:
        return False
    normalized_message = normalize_voice_transcript(student_message)
    spoken = _EXPLICIT_ASSIGNMENT.search(normalized_message)
    board = _EXPLICIT_ASSIGNMENT.search(canvas_final_answer)
    if board is None:
        return False
    if spoken is not None:
        return (
            spoken.group(1).lower() == board.group(1).lower()
            and spoken.group(2) != board.group(2)
        )
    spoken_number = _SPOKEN_NUMERIC_ANSWER.search(normalized_message)
    if spoken_number is not None:
        return spoken_number.group(1) != board.group(2)
    return False


def contains_complete_notation(candidate: str, expected: str) -> bool:
    """Match an exact expression even when earlier canvas work remains visible."""

    normalized = normalize_exact_notation(candidate)
    if normalized == expected:
        return True
    if expected == "":
        return False
    start_boundary = r"(?<![A-Za-z0-9])" if expected[0].isalnum() else ""
    end_boundary = r"(?![A-Za-z0-9])" if expected[-1].isalnum() else ""
    return re.search(f"{start_boundary}{re.escape(expected)}{end_boundary}", normalized) is not None


def is_complete_correct_canvas(
    ocr: VisionOCRResult | None,
    correct_answer: str | None,
) -> bool:
    if ocr is None or ocr.needs_clarification or correct_answer is None:
        return False
    expected = normalize_exact_notation(correct_answer)
    candidates = [
        ocr.final_answer,
        ocr.detected_equation,
        *ocr.detected_steps,
        ocr.raw_ocr_text,
        *(region.text for region in ocr.detected_regions),
        *(region.text for region in ocr.word_regions),
    ]
    return any(
        candidate is not None and contains_complete_notation(candidate, expected)
        for candidate in candidates
    )


def canvas_submission_is_pending(session: "SessionRecord") -> bool:
    """Return whether the active question still needs its required canvas work."""

    return (
        session.question_id is not None
        and session.pending_canvas_submission_question_id == session.question_id
    )


def legacy_ocr_needs_writing(
    ocr: VisionOCRResult,
    minimum_ocr_confidence: float,
) -> bool:
    """Reject uncertain canvas evidence before the legacy tutor records a turn."""

    return ocr.needs_clarification or ocr.confidence < minimum_ocr_confidence
