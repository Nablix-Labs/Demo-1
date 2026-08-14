"""The Student Model owns the routing vocabulary; the backend must not 500 on it.

StudentModelRouting.reason_code is typed `str` on the way in, but
InteractionResponse typed routing_reason_code/support_reason_code as a closed
enum on the way out. Any code the Student Model adds therefore passes ingress
silently and then fails response validation, turning a completed turn into a
500 - the student sees "the tutor couldn't take that submission" even though
their progress was already recorded.

GUIDED_STARTED is the live example: mathtutor-student's guided question-set
handler returns it, and it was never in the backend's enum. Nothing in the
backend or the frontend branches on this field, so a closed enum here buys
nothing and costs whole turns.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.adapters import provider
from app.adapters.student_model import StudentModelServiceAdapter
from app.core.config import Settings
from app.main import app
from app.models.interaction import InteractionResponse
from app.models.student_model_session import (
    StudentModelSessionEvent,
    StudentModelSessionEventResponse,
)
from app.services import session_service
from tests.test_session_events import _event_response, _session_opened_response

client = TestClient(app, headers={"Authorization": "Bearer test-token"})

# Emitted by mathtutor-student/app/services/session_handlers.py for
# GUIDED_QUESTION_SET_REQUESTED - the event the restore/recovery path fires.
UNKNOWN_CODE = "GUIDED_STARTED"


@pytest.mark.parametrize("field", ["routing_reason_code", "support_reason_code"])
def test_unknown_routing_code_is_not_rejected(field: str) -> None:
    """Validate a payload carrying only this field and assert it is not the
    thing that fails. Other fields are legitimately missing here; the point is
    that an unrecognised routing code contributes no error of its own."""

    with pytest.raises(ValidationError) as raised:
        InteractionResponse.model_validate({field: UNKNOWN_CODE})

    offending = [error for error in raised.value.errors() if error["loc"] == (field,)]
    assert offending == [], offending


@pytest.fixture
def schema_student_model(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        student_model_url="https://student-model.test",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        use_mock_student_model=False,
        use_mock_voice=True,
        use_mock_vision=True,
        use_openai_ai_engine=False,
        qdrant_url="https://qdrant.test",
        qdrant_api_key="test-key",
    )

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        body = (
            _session_opened_response("PHASE_2_GUIDED_LEARNING")
            if event.event_type == "SESSION_OPENED"
            else _event_response(event.event_type, event.request_id)
        )
        routing = body["routing"]
        assert isinstance(routing, dict)
        routing["reason_code"] = UNKNOWN_CODE
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send_session_event)


def test_interaction_turn_survives_an_unknown_routing_code(
    schema_student_model: None,
) -> None:
    """The production shape: a real turn whose Student Model reply carries a
    routing code the backend has never heard of must still return 200."""

    started = client.post(
        "/session/start",
        json={
            "student_id": "ST030",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert started.status_code == 200, started.json()
    body = started.json()

    answered = client.post(
        "/interaction",
        json={
            "session_id": body["session_id"],
            "student_id": "ST030",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "text_input": "x = 4",
            "turn_id": "TURN-ST030-1",
            "current_phase": body["current_phase"],
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": body["question_id"],
            "hint_count": 0,
        },
    )

    assert answered.status_code == 200, answered.json()
