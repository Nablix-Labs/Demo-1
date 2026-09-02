"""A multiple-choice answer in Independent Practice is an answer, not a voice turn.

Phase 2 coaches an option and Phase 3 grades it, so the client sends
OPTION_SELECTED in Guided Practice and ANSWER_SUBMISSION in Independent
Practice -- it has to, because `_option_selected_interaction_response` answers
409 outside Guided Practice. Only OPTION_SELECTED was routed around
`_student_message_from`, and that function handled TEXT and CANVAS and then
assumed everything left over was VOICE.

InputSource has five members, not three. So a choice submitted as the student's
independent answer was told "voice_transcript is required for VOICE
interactions." (422), and the screen said "The tutor couldn't take that
submission." Observed live on 2 Sep 2026 at 19:01 UTC, on a Phase 3 choice
question with the student's working already on the canvas.
"""

import pytest
from fastapi.testclient import TestClient

from app.adapters import provider
from app.adapters.student_model import StudentModelServiceAdapter
from app.core.config import Settings
from app.main import app
from app.models.student_model_session import (
    StudentModelSessionEvent,
    StudentModelSessionEventResponse,
)
from app.services import session_service
from tests.test_session_events import _event_response, _session_opened_response

client = TestClient(app, headers={"Authorization": "Bearer test-token"})
STUDENT = "ST031"


@pytest.fixture
def independent_practice(monkeypatch: pytest.MonkeyPatch) -> None:
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
            _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
            if event.event_type == "SESSION_OPENED"
            else _event_response(event.event_type, event.request_id)
        )
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(
        StudentModelServiceAdapter, "send_session_event", send_session_event
    )


def _start() -> dict[str, object]:
    started = client.post(
        "/session/start",
        json={
            "student_id": STUDENT,
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert started.status_code == 200, started.text
    return started.json()


def _selected_option_id(session_id: str) -> str:
    question = session_service._sessions[session_id].active_student_model_question
    assert question is not None, "the Phase 3 fixture must serve a question"
    assert question.student_view.options, "this regression needs a choice question"
    return question.student_view.options[0].option_id


def test_a_choice_answer_is_not_asked_for_a_voice_transcript(
    independent_practice: None,
) -> None:
    body = _start()
    session_id = body["session_id"]

    answered = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": STUDENT,
            # What the client actually sends from Phase 3: the option IS the
            # answer, so it is graded rather than discussed.
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "CHOICE",
            "selected_option_id": _selected_option_id(session_id),
            "turn_id": "TURN-ST031-CHOICE",
            "current_phase": body["current_phase"],
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": body["question_id"],
            "hint_count": 0,
        },
    )

    assert answered.status_code != 422, answered.text
    assert "voice_transcript" not in answered.text
    assert answered.status_code == 200, answered.text
