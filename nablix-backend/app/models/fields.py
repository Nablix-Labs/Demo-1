import base64
import binascii
import re
from typing import Annotated, Literal

from pydantic import AfterValidator

from app.core.config import get_settings


def _check_session_id(value: str) -> str:
    settings = get_settings()
    if re.fullmatch(settings.session_id_pattern, value) is None:
        raise ValueError("session_id must use the SESSION### format.")
    return value


def _check_student_id(value: str) -> str:
    settings = get_settings()
    if re.fullmatch(settings.student_id_pattern, value) is None:
        raise ValueError("student_id must use the ST### format.")
    return value


def _check_nonempty(value: str) -> str:
    if len(value.strip()) == 0:
        raise ValueError("value must not be empty.")
    return value


def _check_bounded_text(value: str) -> str:
    settings = get_settings()
    if len(value.strip()) == 0:
        raise ValueError("value must not be empty.")
    if len(value) > settings.max_text_input_length:
        raise ValueError("value exceeds the maximum allowed length.")
    return value


def _check_snapshot_data_url(value: str) -> str:
    prefix = "data:image/png;base64,"
    if not value.startswith(prefix):
        raise ValueError("snapshot_data_url must use a data:image/png;base64, prefix.")

    payload = value[len(prefix):]
    if len(payload) == 0:
        raise ValueError("snapshot_data_url must include a base64 payload.")

    try:
        base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("snapshot_data_url must contain valid base64 data.") from error
    return value


SessionId = Annotated[str, AfterValidator(_check_session_id)]
StudentId = Annotated[str, AfterValidator(_check_student_id)]
NonEmptyText = Annotated[str, AfterValidator(_check_nonempty)]
BoundedText = Annotated[str, AfterValidator(_check_bounded_text)]
SnapshotDataUrl = Annotated[str, AfterValidator(_check_snapshot_data_url)]

# Concept and question identifiers (e.g. "ALG_LINEAR_ONE_STEP", "ALG_EQ_DIAG_001").
# Non-empty for now; tighten to a pattern when the concept catalog is defined.
ConceptId = NonEmptyText
QuestionId = NonEmptyText

# Shared enums from the Chirudeva module guide (Submodules 6.1-6.4).
Phase = Literal[
    "DIAGNOSTIC",
    "CONCEPT_ORIENTATION",
    "GUIDED_PRACTICE",
    "INDEPENDENT_PRACTICE",
    "REVIEW",
]
InteractionMode = Literal["VOICE", "TEXT"]
InteractionType = Literal[
    "ANSWER_SUBMISSION",
    "HINT_REQUEST",
    "CANVAS_SUBMISSION",
    "SESSION_START",
    "SESSION_END",
]
InputSource = Literal["TEXT", "VOICE"]
