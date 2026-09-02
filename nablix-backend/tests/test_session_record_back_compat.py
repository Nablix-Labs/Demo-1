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
