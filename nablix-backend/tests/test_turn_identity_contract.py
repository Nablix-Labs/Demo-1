"""The identity every reply must carry for the client to apply it.

The frontend gates on `(interaction_state_version, accepted_turn_id)`
(`Numera-ui/lib/responseGate.ts`): a newer version applies, an older one never
does, and an equal version applies only if that `accepted_turn_id` has not been
applied already. So a reply that carries the *previous* turn's id at an
unchanged version is indistinguishable from one the client has already
rendered, and is dropped -- silently, with no error and nothing on screen.

That is how the canvas desync presented in production. This file states the
invariant the whole way round instead of per-path: **every accepted turn is
answered under its own `accepted_turn_id`**. Paths that change no pedagogical
state still have to advance it; they just do not need a new version.
"""

import pytest
from fastapi.testclient import TestClient

from app.adapters.student_model import StudentModelServiceAdapter
from app.main import app
from app.models.student_model_session import (
    StudentModelSessionEvent,
    StudentModelSessionEventResponse,
)
from app.services import session_service
from tests.test_session_events import _session_opened_response


client = TestClient(app, headers={"Authorization": "Bearer test-token"})


@pytest.fixture
def phase3_session(monkeypatch: pytest.MonkeyPatch) -> str:
    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        body = _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(
        StudentModelServiceAdapter, "send_session_event", send_session_event
    )
    response = client.post(
        "/session/start",
        json={
            "student_id": "ST420",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["session_id"]


def _typed_answer(session_id: str, turn_id: str, text: str = "x = 9"):
    stored = session_service._get_owned_session(session_id, "ST420")
    return client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": "ST420",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "turn_id": turn_id,
            "text_input": text,
            "current_phase": stored.current_phase,
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": stored.question_id,
            "hint_count": stored.hint_count,
        },
    )


def test_a_phase_3_typed_answer_is_answered_under_its_own_turn_id(
    phase3_session: str,
) -> None:
    """Independent Practice refuses typed answers -- "use the canvas" -- but
    that refusal is still an accepted turn, and the student has to see it."""

    first = _typed_answer(phase3_session, "TURN-P3-1")

    assert first.status_code == 200, first.text
    assert first.json()["accepted_turn_id"] == "TURN-P3-1"


def test_a_second_typed_answer_is_not_mistaken_for_the_first(
    phase3_session: str,
) -> None:
    """The failure mode in full: a student who types twice must be answered
    twice. Sharing one identity at one version makes the second reply
    indistinguishable from a replay of the first, and the client drops it."""

    first = _typed_answer(phase3_session, "TURN-P3-1")
    second = _typed_answer(phase3_session, "TURN-P3-2", "x = 10")

    assert first.status_code == 200 and second.status_code == 200
    first_body, second_body = first.json(), second.json()
    # Either a new turn id or a higher version satisfies the gate; this path
    # changes no pedagogical state, so the turn id is what has to move.
    assert second_body["accepted_turn_id"] == "TURN-P3-2"
    assert second_body["accepted_turn_id"] != first_body["accepted_turn_id"]


def test_the_stored_session_agrees_with_what_the_client_was_told(
    phase3_session: str,
) -> None:
    """The next request echoes `previous_tutor_turn_id` back from this reply,
    and it is checked against the stored session. If the reply advertises a
    tutor turn the session never recorded, that next request reads as stale."""

    body = _typed_answer(phase3_session, "TURN-P3-1").json()

    stored = session_service._get_owned_session(phase3_session, "ST420")
    assert stored.last_processed_turn_id == body["accepted_turn_id"]
    assert stored.last_tutor_turn_id == body["tutor_turn_id"]


def test_a_phase_3_clarification_request_also_carries_its_own_turn_id(
    phase3_session: str,
) -> None:
    """The sibling refusal on the same branch, refused the same way."""

    stored = session_service._get_owned_session(phase3_session, "ST420")
    response = client.post(
        "/interaction",
        json={
            "session_id": phase3_session,
            "student_id": "ST420",
            "interaction_type": "CLARIFICATION_REQUEST",
            "input_source": "VOICE",
            "transcript_final": True,
            "turn_id": "TURN-P3-CLARIFY",
            "text_input": "what do you mean?",
            "current_phase": stored.current_phase,
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": stored.question_id,
            "hint_count": stored.hint_count,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["accepted_turn_id"] == "TURN-P3-CLARIFY"


def test_a_duplicate_retry_still_replays_one_identity(phase3_session: str) -> None:
    """The counterpart guarantee: the same turn id sent twice must NOT look
    like two turns, or the client renders the refusal twice."""

    first = _typed_answer(phase3_session, "TURN-P3-1")
    duplicate = _typed_answer(phase3_session, "TURN-P3-1")

    assert duplicate.status_code == 200
    assert duplicate.json()["accepted_turn_id"] == first.json()["accepted_turn_id"]
    assert (
        duplicate.json()["interaction_state_version"]
        == first.json()["interaction_state_version"]
    )
