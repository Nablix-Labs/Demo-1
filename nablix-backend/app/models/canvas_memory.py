from typing import Literal

from pydantic import BaseModel, Field


CanvasActor = Literal["STUDENT", "TUTOR", "SYSTEM_SUPPORT"]
CanvasActionType = Literal[
    "WRITE",
    "ERASE",
    "CLEAR",
    "HIGHLIGHT",
    "CIRCLE",
    "ARROW",
    "INSERT_MATH",
    "ANNOTATE",
    "SHOW_CUE",
    "HIDE_CUE",
    "SCAFFOLD_STEP",
    "GROUP",
    "INSERT_LABEL",
    "FOCUS",
    "SHOW_PARALLEL",
    "TUTOR_SOLVED_STEP",
]
CanvasActiveState = Literal["ACTIVE", "SUPERSEDED", "CLEARED"]


class CanvasBoundingBox(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(ge=0.0, le=1.0)
    h: float = Field(ge=0.0, le=1.0)


class CanvasEvent(BaseModel):
    order_index: int = Field(ge=0)
    turn_id: str | None
    question_id: str | None
    actor: CanvasActor
    action_type: CanvasActionType
    content: str | None
    math_text: str | None
    target_object_id: str | None
    bbox: CanvasBoundingBox | None
    semantic_tag: str | None
    source_id: str | None
    active_state: CanvasActiveState


def validate_canvas_event_order(events: list[CanvasEvent]) -> None:
    mismatch = next(
        (
            (expected, event.order_index)
            for expected, event in enumerate(events)
            if event.order_index != expected
        ),
        None,
    )
    if mismatch is not None:
        expected, received = mismatch
        raise ValueError(
            "canvas_events order_index values must be contiguous from zero; "
            f"expected {expected}, received {received}"
        )
