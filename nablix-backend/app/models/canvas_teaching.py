from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


CanvasTeachingOperationKind = Literal[
    "FOCUS",
    "HIGHLIGHT",
    "CIRCLE",
    "CONNECT",
    "WRITE_TEXT",
    "WRITE_MATH",
    "BOX",
    "CHECK",
]
CanvasTeachingTargetKind = Literal["QUESTION_ANCHOR", "STUDENT_TOKEN", "CANVAS_ZONE"]
CanvasTeachingZone = Literal["QUESTION", "REASONING", "TUTOR_SOLUTION"]
CanvasTeachingPersistence = Literal["PULSE", "PERSIST"]
CanvasTeachingMode = Literal[
    "GUIDED",
    "DIRECT_EXPLANATION",
    "HINT",
    "VISUAL_CUE",
    "SCAFFOLD",
    "PARALLEL_EXAMPLE",
    "TUTOR_SOLVED",
]


class CanvasSpeechAnchor(BaseModel):
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_range(self) -> "CanvasSpeechAnchor":
        if self.end_char <= self.start_char:
            raise ValueError("speech anchor end_char must be greater than start_char")
        return self


class CanvasTeachingOperation(BaseModel):
    operation_id: str = Field(min_length=1, max_length=120)
    kind: CanvasTeachingOperationKind
    target_kind: CanvasTeachingTargetKind
    target_ids: list[str] = Field(min_length=1, max_length=4)
    zone: CanvasTeachingZone
    persistence: CanvasTeachingPersistence
    evidence_ref: str | None = Field(default=None, max_length=120)
    text: str | None = Field(default=None, max_length=160)
    latex: str | None = Field(default=None, max_length=160)
    color_role: Literal["NAVY", "AMBER", "TEAL"] = "NAVY"
    scene_slot: str | None = Field(default=None, min_length=1, max_length=80)

    @model_validator(mode="after")
    def validate_content(self) -> "CanvasTeachingOperation":
        writes = self.kind in {"WRITE_TEXT", "WRITE_MATH"}
        if writes and not (self.text or self.latex):
            raise ValueError("written canvas operations require text or latex")
        if not writes and (self.text is not None or self.latex is not None):
            raise ValueError("non-writing canvas operations cannot include text or latex")
        if self.target_kind == "CANVAS_ZONE" and any(not target.startswith("ZONE:") for target in self.target_ids):
            raise ValueError("canvas-zone targets must start with ZONE:")
        return self


class CanvasTeachingBeat(BaseModel):
    beat_id: str = Field(min_length=1, max_length=120)
    sequence: int = Field(ge=1, le=12)
    speech_anchor: CanvasSpeechAnchor
    operations: list[CanvasTeachingOperation] = Field(min_length=1, max_length=4)


class CanvasTeachingPlanDraft(BaseModel):
    beats: list[CanvasTeachingBeat] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "CanvasTeachingPlanDraft":
        beat_ids = [beat.beat_id for beat in self.beats]
        if len(beat_ids) != len(set(beat_ids)):
            raise ValueError("canvas teaching beat IDs must be unique")
        sequences = [beat.sequence for beat in self.beats]
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise ValueError("canvas teaching beats must have unique ascending sequences")
        return self


class CanvasTeachingPlan(CanvasTeachingPlanDraft):
    plan_id: str = Field(min_length=1, max_length=180)
    question_id: str = Field(min_length=1, max_length=120)
    source_turn_id: str = Field(min_length=1, max_length=120)
    tutor_turn_id: str | None = Field(default=None, max_length=120)
    scene_revision: int = Field(ge=0)
    mode: Literal["append", "replace"]
    teaching_mode: CanvasTeachingMode
