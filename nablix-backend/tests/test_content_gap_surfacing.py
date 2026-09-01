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
from fastapi import HTTPException

from app.core.logger import logger as app_logger
from app.models.session import SessionRecord
from app.models.student_model_session import StudentModelSessionEventResponse
from app.services import interaction_service, session_service
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


# --- The restore initializer -------------------------------------------------
#
# Same gap, one layer up. A session restored into Phase 3 with no active
# question re-asked Student Model for content on every turn; Student Model
# answered FRESH_CONTENT_UNAVAILABLE every time, and the strict "did not
# initialize the restored phase" check turned that answer into a 503 that named
# neither the gap nor the skill. Observed on T01.M1/T01.M2.


class _CountingStudentModel:
    """Records every content request the initializer makes."""

    def __init__(self, response: StudentModelSessionEventResponse) -> None:
        self.response = response
        self.requests: list[str] = []

    async def send_session_event(
        self, event: object, access_token: str
    ) -> StudentModelSessionEventResponse:
        self.requests.append(getattr(event, "event_type", "UNKNOWN"))
        return self.response


def _restored_phase3_session() -> SessionRecord:
    """Phase 3 restored with skills left to practise but no question in hand."""

    session = _stuck_session()
    event = _content_gap_event()
    event.journey_state.phase_3_independent_practice.status = "IN_PROGRESS"
    event.journey_state.phase_3_independent_practice.remaining_micro_skill_ids = [
        "T01.M1",
        "T01.M2",
    ]
    return session.model_copy(update={"student_model_event": event})


def _restore(session: SessionRecord, adapter: _CountingStudentModel) -> None:
    asyncio.run(
        interaction_service._initialize_restored_schema_phase(session, adapter, "TOKEN")
    )


def test_a_stored_content_gap_is_not_asked_again() -> None:
    adapter = _CountingStudentModel(_content_gap_event())

    with pytest.raises(HTTPException) as raised:
        _restore(_restored_phase3_session(), adapter)

    assert adapter.requests == [], "the gap was re-requested instead of reported"
    assert raised.value.detail == {
        "code": "CONTENT_GAP",
        "message": session_service.CONTENT_GAP_MESSAGE,
    }
    assert raised.value.status_code != 503


def test_a_fresh_content_gap_answer_is_reported_as_one() -> None:
    """Reached when the stored event is clean but the request hits the gap."""

    session = _restored_phase3_session()
    session.student_model_event.routing.content_gap_detected = False
    adapter = _CountingStudentModel(_content_gap_event())

    with pytest.raises(HTTPException) as raised:
        _restore(session, adapter)

    assert adapter.requests == ["INDEPENDENT_QUESTION_SET_REQUESTED"]
    assert raised.value.detail["code"] == "CONTENT_GAP"


def test_the_content_gap_never_becomes_review(
    app_log: pytest.LogCaptureFixture,
) -> None:
    """A missing question is not mastery. Nothing here may promote the student."""

    session = _restored_phase3_session()
    with app_log.at_level(logging.WARNING):
        with pytest.raises(HTTPException):
            _restore(session, _CountingStudentModel(_content_gap_event()))

    assert session.current_phase == "INDEPENDENT_PRACTICE"
    assert session.student_model_event.journey_state.mastery_status != "MASTERED"
    assert session.phase4_review is None
    logged = [r for r in app_log.records if r.getMessage() == "restore_phase_content_gap"]
    assert logged, "the gap left no trace at the restore boundary"
    assert logged[0].missing_micro_skill_ids == ["T01.M6"]
    assert logged[0].phase == "INDEPENDENT_PRACTICE"


def test_a_restore_failure_that_is_not_a_content_gap_says_which_check_failed(
    app_log: pytest.LogCaptureFixture,
) -> None:
    """The 503 stays, but no longer arrives without a reason. Redacted: field
    names and IDs only, never the student's work."""

    session = _restored_phase3_session()
    session.student_model_event.routing.content_gap_detected = False
    empty = _content_gap_event()
    empty.routing.content_gap_detected = False
    empty.status.intervention_required = False
    adapter = _CountingStudentModel(empty)

    with app_log.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as raised:
            _restore(session, adapter)

    assert raised.value.status_code == 503
    record = next(
        r for r in app_log.records if r.getMessage() == "restore_phase_not_initialized"
    )
    assert record.failure_reason == "MISSING_PAYLOAD"
    assert record.phase == "INDEPENDENT_PRACTICE"
    assert record.question_count == 0
    assert record.current_question_id is None
    assert not hasattr(record, "access_token")
