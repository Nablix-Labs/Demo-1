"""Student Model reporting it has no content left to serve.

It raises four flags at once when this happens (`content_gap_detected`,
`next_action: WAIT_FOR_CONTENT`, `status_code: CONTENT_GAP`,
`intervention_required`). Until 22 Aug 2026 this repo read none of them, so a
student whose fresh Phase 3 question did not exist was left on a screen with no
question, no explanation, and nothing in the log to say why.

Observed on ST020: the tutor said "We'll review this one before a fresh
independent check", Student Model answered
"No fresh independent question is available for T01.M6", and the session simply
stopped with current_question null.
"""

import asyncio
import logging

import pytest

from app.core.logger import logger as app_logger
from app.models.session import SessionRecord
from app.models.student_model_session import StudentModelSessionEventResponse
from app.services import session_service
from tests.test_session_events import _session_opened_response


@pytest.fixture
def app_log(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    """The app logger sets propagate=False (app/core/logger.py:36), so caplog's
    root handler never sees its records. Attach it directly."""

    app_logger.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        app_logger.removeHandler(caplog.handler)


def _content_gap_event() -> StudentModelSessionEventResponse:
    body = _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
    # What handle_fresh_independent_question_requested returns when the question
    # bank has nothing left for the target skill (session_handlers.py:832).
    body["phase_payload"] = None
    body["routing"] = {
        **body["routing"],
        "reason_code": "FRESH_CONTENT_UNAVAILABLE",
        "reason": "No fresh independent question is available for T01.M6.",
        "next_action": "WAIT_FOR_CONTENT",
        "content_gap_detected": True,
        "missing_micro_skill_ids": ["T01.M6"],
    }
    body["status"] = {
        **body["status"],
        "status_code": "CONTENT_GAP",
        "intervention_required": True,
        "intervention_reason": "Missing fresh independent question for T01.M6.",
    }
    return StudentModelSessionEventResponse.model_validate(body)


def _stuck_session() -> SessionRecord:
    return SessionRecord.model_construct(
        session_id="SESSION-001",
        student_id="ST020",
        current_phase="INDEPENDENT_PRACTICE",
        question_id=None,
        current_question=None,
        message="We'll review this one before a fresh independent check.",
    )


def test_content_gap_is_logged_with_the_missing_skills(
    app_log: pytest.LogCaptureFixture,
) -> None:
    with app_log.at_level(logging.WARNING):
        asyncio.run(session_service._apply_schema_event(_stuck_session(), _content_gap_event()))

    gap = [r for r in app_log.records if r.getMessage() == "student_model_content_gap"]
    assert gap, "the content gap left no trace in the log"
    assert gap[0].missing_micro_skill_ids == ["T01.M6"]
    assert gap[0].status_code == "CONTENT_GAP"


def test_content_gap_replaces_the_promise_of_a_fresh_question() -> None:
    """The last thing the student heard was that a fresh check was coming. Saying
    nothing leaves that promise standing on a screen they cannot act on."""

    updated = asyncio.run(
        session_service._apply_schema_event(_stuck_session(), _content_gap_event())
    )

    assert updated.message == session_service.CONTENT_GAP_MESSAGE
    assert "fresh independent check" not in updated.message


def test_a_normal_turn_is_left_alone() -> None:
    """The message only changes when there is genuinely nothing to answer."""

    event = _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
    updated = asyncio.run(
        session_service._apply_schema_event(
            _stuck_session(), StudentModelSessionEventResponse.model_validate(event)
        )
    )

    assert updated.message != session_service.CONTENT_GAP_MESSAGE
