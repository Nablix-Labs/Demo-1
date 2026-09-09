"""Sessions written before a field existed must still load.

Every persisted session is revalidated through `SessionRecord` at startup
(`session_store.open_session_store`), and one unreadable row does not degrade
the service -- it aborts the boot. So adding a required field to anything
reachable from `SessionRecord` is a migration, not an edit: rows already in the
table do not have it.

`independent_attempts` was added to `SessionPerformance` without a default on
2 Sep 2026. Every session stored before that deploy carried a
`session_summary.session_performance` without the key, so `model_validate`
raised and the backend would not start at all.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.adapters.student_model import StudentModelServiceAdapter
from app.main import app
from app.models.session import SessionPerformance, SessionRecord
from app.models.student_model_session import (
    GuidedRepairCompletedEvent,
    StudentModelSessionEvent,
    StudentModelSessionEventResponse,
)
from app.services import session_service
from tests.test_session_events import _session_opened_response


# Exactly the shape the old code wrote: the seven fields that existed before
# independent_attempts was introduced.
LEGACY_PERFORMANCE = {
    "total_attempts": 3,
    "correct_attempts": 2,
    "incorrect_attempts": 1,
    "hints_used": 0,
    "hint_levels_used": [],
    "scaffold_steps_delivered": None,
    "canvas_submissions": 1,
}


def test_a_performance_block_written_before_the_counter_still_loads() -> None:
    performance = SessionPerformance.model_validate(LEGACY_PERFORMANCE)

    # Nothing was counted for it, and nothing may be invented for it either.
    assert performance.independent_attempts == 0
    assert performance.total_attempts == 3


def test_a_stored_session_carrying_that_block_still_loads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failure was at this level: one such row aborted the whole boot.

    Built by round-tripping a real session the way the store does -- dump it,
    drop the key an older writer would not have written, revalidate.
    """

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        body = _session_opened_response("PHASE_2_GUIDED_LEARNING")
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(
        StudentModelServiceAdapter, "send_session_event", send_session_event
    )
    client = TestClient(app, headers={"Authorization": "Bearer test-token"})
    session_id = client.post(
        "/session/start",
        json={
            "student_id": "ST440",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    ).json()["session_id"]
    client.post("/session/end", json={"session_id": session_id, "student_id": "ST440"})

    stored = session_service._sessions[session_id].model_dump(mode="json")
    assert stored["session_summary"] is not None
    # What a writer from before 2 Sep 2026 would have persisted.
    del stored["session_summary"]["session_performance"]["independent_attempts"]
    del stored["independent_attempt_count"]

    try:
        session = SessionRecord.model_validate(stored)
    except ValidationError as error:  # pragma: no cover - the regression itself
        pytest.fail(f"a pre-existing session no longer loads: {error}")

    assert session.session_summary is not None
    assert session.session_summary.session_performance.independent_attempts == 0
    assert session.independent_attempt_count == 0


def test_a_session_written_before_the_recovery_fields_still_loads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The repair/recovery bookkeeping is the same kind of migration.

    `pending_guided_progression` and `journey_recovery_required` were added to
    `SessionRecord` for the Phase 3 repair contract. Every row already in the
    table predates them, so both must default -- and they must default to
    "nothing pending, nothing to recover" rather than to a state that would make
    the next request refuse work or replay an event that was never sent.
    """

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        body = _session_opened_response("PHASE_2_GUIDED_LEARNING")
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(
        StudentModelServiceAdapter, "send_session_event", send_session_event
    )
    client = TestClient(app, headers={"Authorization": "Bearer test-token"})
    session_id = client.post(
        "/session/start",
        json={
            "student_id": "ST441",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    ).json()["session_id"]

    stored = session_service._sessions[session_id].model_dump(mode="json")
    del stored["pending_guided_progression"]
    del stored["journey_recovery_required"]

    try:
        session = SessionRecord.model_validate(stored)
    except ValidationError as error:  # pragma: no cover - the regression itself
        pytest.fail(f"a pre-recovery session no longer loads: {error}")

    assert session.pending_guided_progression is None
    assert session.journey_recovery_required is False
    # And the defaults let learning continue: a refusal here would strand every
    # session that predates the field.
    session_service.require_learning_active(session)


def test_an_inconsistent_stored_repair_event_fails_loudly() -> None:
    """A persisted repair event missing its identity must not load as a guess.

    The defaults above are for rows written before the field existed. A row that
    *does* carry a pending repair has to carry the whole of it: a repair event
    with no skill or no cycle number cannot be sent, and inventing either would
    return the student to a checkpoint nobody identified.
    """

    incomplete = {
        "request_id": "SESSION-1:TURN-1:GUIDED_REPAIR_COMPLETED",
        "event_type": "GUIDED_REPAIR_COMPLETED",
        "source_turn_id": "TURN-1",
        "expected_journey_version": 8,
        "topic_id": "ALG-KS3-01",
        "student_id": "ST010",
        "timestamp": "2026-09-09T14:49:19Z",
        "micro_skill_ids": [],
        "repair_cycle_no": 1,
    }

    with pytest.raises(ValidationError):
        GuidedRepairCompletedEvent.model_validate(incomplete)

    with pytest.raises(ValidationError):
        GuidedRepairCompletedEvent.model_validate({**incomplete,
                                                  "micro_skill_ids": ["T01.M5"],
                                                  "repair_cycle_no": 3})
