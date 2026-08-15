"""Spatial Overlay Engine for handwritten math token localization.

Associates raw frontend student ink strokes with Mathpix OCR step contours,
parses MathML semantic trees, forms multi-stroke symbol candidates, and produces
SpatialMathTokens with normalized bounding boxes.
"""

import xml.etree.ElementTree as ET
from typing import Literal
from unicodedata import normalize

from app.models.adapters import OCRTextRegion, SpatialMathToken
from app.models.canvas import CanvasPoint, CanvasStroke


_MATH_OPERATOR_EQUIVALENTS = str.maketrans(
    {
        "−": "-",
        "–": "-",
        "—": "-",
        "﹣": "-",
        "×": "*",
        "·": "*",
        "∙": "*",
        "⋅": "*",
        "÷": "/",
        "∕": "/",
        "⁄": "/",
    }
)

_LATEX_OPERATOR_EQUIVALENTS: tuple[tuple[str, str], ...] = (
    (r"\times", "*"),
    (r"\cdot", "*"),
    (r"\div", "/"),
)


def canonical_math_token_text(value: str) -> str:
    """Normalize OCR and MathML text for supported tutor-error comparisons."""

    normalized = value
    for source, replacement in _LATEX_OPERATOR_EQUIVALENTS:
        normalized = normalized.replace(source, replacement)
    return "".join(normalize("NFKC", normalized).translate(_MATH_OPERATOR_EQUIVALENTS).split())


class StrokeBox:

    def __init__(self, stroke_id: str, min_x: float, min_y: float, max_x: float, max_y: float, width: float) -> None:
        self.stroke_id = stroke_id
        self.min_x = min_x
        self.min_y = min_y
        self.max_x = max_x
        self.max_y = max_y
        self.width = width
        self.w = max(0.001, max_x - min_x)
        self.h = max(0.001, max_y - min_y)
        self.cx = (min_x + max_x) / 2.0
        self.cy = (min_y + max_y) / 2.0


def stroke_to_box(stroke: CanvasStroke) -> StrokeBox | None:
    """Compute normalized bounding box for a CanvasStroke."""
    if not stroke.points:
        return None
    xs = [p.x for p in stroke.points]
    ys = [p.y for p in stroke.points]
    return StrokeBox(
        stroke_id=stroke.stroke_id,
        min_x=min(xs),
        min_y=min(ys),
        max_x=max(xs),
        max_y=max(ys),
        width=stroke.width,
    )


def associate_strokes_with_steps(
    strokes: list[CanvasStroke],
    regions: list[OCRTextRegion],
) -> dict[str, list[CanvasStroke]]:
    """Group strokes under step IDs based on vertical & horizontal overlap with regions."""
    if not regions:
        return {}

    step_strokes: dict[str, list[CanvasStroke]] = {
        region.step_id or f"step-{i+1}": [] for i, region in enumerate(regions)
    }

    for stroke in strokes:
        box = stroke_to_box(stroke)
        if box is None:
            continue

        best_step_id: str | None = None
        best_overlap = -1.0

        for index, region in enumerate(regions):
            step_id = region.step_id or f"step-{index+1}"
            reg_top = region.y - 0.05
            reg_bottom = region.y + region.h + 0.05
            if reg_top <= box.cy <= reg_bottom:
                overlap = min(box.max_y, region.y + region.h) - max(box.min_y, region.y)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_step_id = step_id

        if best_step_id is None:
            best_step_id = (regions[0].step_id or "step-1")
            min_dist = float("inf")
            for index, region in enumerate(regions):
                dist = abs(box.cy - (region.y + region.h / 2.0))
                if dist < min_dist:
                    min_dist = dist
                    best_step_id = region.step_id or f"step-{index+1}"

        step_strokes[best_step_id].append(stroke)

    return step_strokes


class ParsedMathMLToken:

    def __init__(self, text: str, role: Literal["number", "identifier", "operator", "fraction_bar", "radical", "fence"], semantic_path: str) -> None:
        self.text = text
        self.role = role
        self.semantic_path = semantic_path


def parse_mathml_tokens(mathml_xml: str | None) -> list[ParsedMathMLToken]:
    """Recursively parse a MathML XML string into a flat list of tokens."""
    if not mathml_xml or not mathml_xml.strip():
        return []

    tokens: list[ParsedMathMLToken] = []
    try:
        root = ET.fromstring(mathml_xml)
    except ET.ParseError:
        return tokens

    def _walk(element: ET.Element, path: str) -> None:
        tag = element.tag.split("}")[-1]
        text = (element.text or "").strip()

        if tag == "mn":
            if text:
                tokens.append(ParsedMathMLToken(text=text, role="number", semantic_path=f"{path}/mn"))
        elif tag == "mi":
            if text:
                tokens.append(ParsedMathMLToken(text=text, role="identifier", semantic_path=f"{path}/mi"))
        elif tag == "mo":
            if text:
                tokens.append(ParsedMathMLToken(text=text, role="operator", semantic_path=f"{path}/mo"))
        elif tag == "mfrac":
            tokens.append(ParsedMathMLToken(text="/", role="fraction_bar", semantic_path=f"{path}/mfrac_bar"))
            for idx, child in enumerate(element):
                _walk(child, f"{path}/mfrac[{idx}]")
        elif tag in ("mroot", "msqrt"):
            tokens.append(ParsedMathMLToken(text="√", role="radical", semantic_path=f"{path}/{tag}"))
            for idx, child in enumerate(element):
                _walk(child, f"{path}/{tag}[{idx}]")
        else:
            for idx, child in enumerate(element):
                _walk(child, f"{path}/{tag}[{idx}]")

    _walk(root, "/math")
    return tokens


def group_strokes_into_candidates(strokes: list[CanvasStroke]) -> list[list[StrokeBox]]:
    """Group multi-stroke operators (+, =, ±, i) and single strokes left-to-right."""
    boxes = [b for b in (stroke_to_box(s) for s in strokes) if b is not None]
    if not boxes:
        return []

    boxes.sort(key=lambda b: b.min_x)

    visited = set()
    clusters: list[list[StrokeBox]] = []

    for i, b1 in enumerate(boxes):
        if i in visited:
            continue
        cluster = [b1]
        visited.add(i)

        for j in range(i + 1, len(boxes)):
            if j in visited:
                continue
            b2 = boxes[j]

            x_overlap = min(b1.max_x, b2.max_x) - max(b1.min_x, b2.min_x)
            y_overlap = min(b1.max_y, b2.max_y) - max(b1.min_y, b2.min_y)

            x_close = abs(b1.cx - b2.cx) < 0.04
            y_close = abs(b1.cy - b2.cy) < 0.04

            if (x_overlap > -0.01 and y_close) or (y_overlap > -0.01 and x_close):
                cluster.append(b2)
                visited.add(j)

        clusters.append(cluster)

    clusters.sort(key=lambda c: sum(b.cx for b in c) / len(c))
    return clusters


def align_step_tokens(
    step_id: str,
    mathml_xml: str | None,
    text_fallback: str,
    strokes: list[CanvasStroke],
    step_region: OCRTextRegion | None = None,
) -> list[SpatialMathToken]:
    """Align parsed MathML or fallback text tokens with candidate stroke clusters."""
    mathml_tokens = parse_mathml_tokens(mathml_xml)

    if not mathml_tokens:
        cleaned_text = text_fallback.replace(" ", "")
        mathml_tokens = [
            ParsedMathMLToken(
                text=char,
                role="operator" if char in "+-=/*^" else ("number" if char.isdigit() else "identifier"),
                semantic_path=f"/text/{idx}",
            )
            for idx, char in enumerate(cleaned_text)
        ]

    clusters = group_strokes_into_candidates(strokes)
    spatial_tokens: list[SpatialMathToken] = []

    for idx, token in enumerate(mathml_tokens, start=1):
        token_id = f"{step_id}:token-{idx}"

        if idx - 1 < len(clusters):
            cluster = clusters[idx - 1]
            stroke_ids = [b.stroke_id for b in cluster]
            min_x = min(b.min_x for b in cluster)
            min_y = min(b.min_y for b in cluster)
            max_x = max(b.max_x for b in cluster)
            max_y = max(b.max_y for b in cluster)

            pad = 0.005
            box_dict = {
                "x": max(0.0, min_x - pad),
                "y": max(0.0, min_y - pad),
                "width": max(0.01, (max_x - min_x) + 2 * pad),
                "height": max(0.01, (max_y - min_y) + 2 * pad),
            }
            confidence = 0.95
        else:
            stroke_ids = []
            if step_region is not None:
                box_dict = {
                    "x": step_region.x,
                    "y": step_region.y,
                    "width": step_region.w,
                    "height": step_region.h,
                }
                confidence = 0.5
            else:
                box_dict = {"x": 0.0, "y": 0.0, "width": 0.1, "height": 0.1}
                confidence = 0.1

        spatial_tokens.append(
            SpatialMathToken(
                token_id=token_id,
                step_id=step_id,
                text=token.text,
                latex=token.text,
                role=token.role,
                semantic_path=token.semantic_path,
                stroke_ids=stroke_ids,
                bounding_box=box_dict,
                alignment_confidence=confidence,
            )
        )

    return spatial_tokens
