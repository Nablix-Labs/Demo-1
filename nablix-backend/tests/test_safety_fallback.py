"""What the student gets when the safety gate blocks their message.

The gate has been adapter-shaped since it was written, and until now nothing
exercised the path where it actually blocks. A rename applied one line too far
turned that path into an `AttributeError` -- so the one branch whose entire job
is to answer calmly and stay in control was the branch that 500'd.
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

# MockSafetyServiceAdapter blocks on this token and nothing else
# (app/adapters/safety_service.py), so the test needs no sensitive phrase.
BLOCKING_INPUT = "SAFETY_BLOCK"


@pytest.fixture(autouse=True)
def guided_student_model(monkeypatch: pytest.MonkeyPatch) -> None:
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


def _session() -> str:
    response = client.post(
        "/session/start",
        json={
            "student_id": "ST430",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["session_id"]


def test_a_blocked_message_is_answered_not_crashed() -> None:
    session_id = _session()
    stored = session_service._get_owned_session(session_id, "ST430")

    response = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": "ST430",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "turn_id": "TURN-SAFETY-1",
            "text_input": BLOCKING_INPUT,
            "current_phase": stored.current_phase,
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": stored.question_id,
            "hint_count": stored.hint_count,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["message"] == (
        "Let's pause for a moment and come back to the maths when you're ready."
    )
    # The safe reply is still a turn: it has to reach the screen like any other.
    assert body["accepted_turn_id"] == "TURN-SAFETY-1"
