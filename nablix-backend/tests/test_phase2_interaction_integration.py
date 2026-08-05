from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.adapters import provider
from app.adapters.student_model import StudentModelServiceAdapter
from app.core.config import Settings
from app.main import app
from app.ai_engine.schemas import ExplainAgainResponse
from app.models.student_model_session import (
    StudentModelSessionEvent,
    StudentModelSessionEventResponse,
)
from app.services import interaction_service, session_service
from tests.test_session_events import _event_response, _session_opened_response


client = TestClient(app, headers={"Authorization": "Bearer test-token"})


@pytest.fixture(autouse=True)
def schema_student_model(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        student_model_url="https://student-model.test",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        use_mock_student_model=False,
        use_openai_ai_engine=False,
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
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send_session_event)

    class ExplainAgainClient:
        def generate_explain_again_response(
            self,
            request: object,
            system_prompt: str,
        ) -> ExplainAgainResponse:
            del request, system_prompt
            return ExplainAgainResponse(
                tutor_message="Here is a different way to think about the same idea.",
                tutor_message_voice="Voice: here is a different way to think about it.",
                answer_reveal_allowed=False,
                progression_change_requested=False,
                attempt_increment=0,
            )

    monkeypatch.setattr(
        interaction_service,
        "build_openai_ai_engine_client",
        lambda settings: ExplainAgainClient(),
    )


def _start(student_id: str) -> dict[str, object]:
    response = client.post(
        "/session/start",
        json={
            "student_id": student_id,
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["inactivity_policy"] == {
        "initial_idle_threshold_ms": 20_000,
        "cooldown_ms": 30_000,
        "max_nudges_per_tutor_turn": 2,
        "generated_nudge_rate_limit": 4,
    }
    return body


def _interaction(
    session: dict[str, object],
    student_id: str,
    turn_id: str,
    interaction_type: str,
    previous_tutor_turn_id: str | None,
) -> dict[str, object]:
    return {
        "session_id": session["session_id"],
        "student_id": student_id,
        "interaction_type": interaction_type,
        "input_source": "TEXT",
        "turn_id": turn_id,
        "previous_tutor_turn_id": previous_tutor_turn_id,
        "text_input": "Please explain that another way",
        "current_phase": session["current_phase"],
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "question_id": session["question_id"],
        "hint_count": session["hint_count"],
    }


def _pedagogical_state(session_id: object) -> dict[str, object]:
    session = session_service._sessions[str(session_id)]
    fields = (
        "attempt_count",
        "wrong_attempt_count",
        "generated_question_rubric",
        "active_teaching_objective",
        "student_model_event",
        "student_model_state",
        "hint_count",
        "scaffold_id",
        "current_scaffold_step_id",
        "scaffold_step_number",
        "scaffold_steps",
        "current_phase",
    )
    return {field: getattr(session, field) for field in fields}


def test_text_duplicate_and_stale_turns_do_not_mutate_state() -> None:
    student_id = "ST151"
    session = _start(student_id)
    request = _interaction(
        session,
        student_id,
        "TURN-TEXT-1",
        "ANSWER_SUBMISSION",
        None,
    )

    first = client.post("/interaction", json=request)
    assert first.status_code == 200, first.text
    first_body = first.json()

    duplicate = client.post("/interaction", json=request)
    assert duplicate.status_code == 200
    duplicate_body = duplicate.json()
    assert duplicate_body["status"] == "DUPLICATE_TURN"
    assert duplicate_body["accepted_turn_id"] == "TURN-TEXT-1"
    assert duplicate_body["interaction_state_version"] == first_body[
        "interaction_state_version"
    ]

    assert duplicate_body["message"] == first_body["message"]
    assert duplicate_body["attempt_count"] == first_body["attempt_count"]

    stale_request = _interaction(
        session,
        student_id,
        "TURN-TEXT-STALE",
        "ANSWER_SUBMISSION",
        "TUTOR-STALE",
    )
    stale = client.post("/interaction", json=stale_request)
    assert stale.status_code == 409
    assert stale.json()["status"] == "STALE_TURN"

    stored = client.get(f"/session/{session['session_id']}")
    assert stored.status_code == 200
    assert stored.json()["attempt_count"] == first_body["attempt_count"]


def test_explain_again_is_cached_and_does_not_grade() -> None:
    student_id = "ST152"
    session = _start(student_id)
    request = _interaction(
        session,
        student_id,
        "TURN-EXPLAIN-1",
        "EXPLAIN_AGAIN",
        None,
    )
    before = _pedagogical_state(session["session_id"])

    first = client.post("/interaction", json=request)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["accepted_turn_id"] == "TURN-EXPLAIN-1"
    assert first_body["attempt_increment"] == 0
    assert first_body["attempt_count"] == session["attempt_count"]
    assert first_body["question_id"] == session["question_id"]
    assert first_body["current_phase"] == session["current_phase"]
    assert first_body["message_voice"] == "Voice: here is a different way to think about it."

    duplicate = client.post("/interaction", json=request)
    assert duplicate.status_code == 200
    duplicate_body = duplicate.json()
    assert duplicate_body["status"] == "DUPLICATE_TURN"
    assert duplicate_body["message"] == first_body["message"]
    assert duplicate_body["interaction_state_version"] == first_body[
        "interaction_state_version"
    ]
    assert duplicate_body["attempt_count"] == first_body["attempt_count"]
    assert _pedagogical_state(session["session_id"]) == before


def test_help_request_without_active_support_is_explicit() -> None:
    student_id = "ST153"
    session = _start(student_id)
    request = _interaction(
        session,
        student_id,
        "TURN-HELP-1",
        "HELP_REQUEST",
        None,
    )

    response = client.post("/interaction", json=request)
    assert response.status_code == 409
    assert response.json()["message"].startswith("NO_ACTIVE_SUPPORT:")

    stored = client.get(f"/session/{session['session_id']}")
    assert stored.status_code == 200
    assert stored.json()["attempt_count"] == session["attempt_count"]


def test_inactivity_nudge_is_cached_without_pedagogical_mutation() -> None:
    student_id = "ST154"
    session = _start(student_id)
    request = _interaction(
        session,
        student_id,
        "TURN-NUDGE-1",
        "INACTIVITY_NUDGE",
        None,
    )
    request["input_source"] = "SYSTEM"
    request["previous_tutor_turn_id"] = session["last_tutor_turn_id"]
    request["idle_duration_ms"] = 20_000
    stored_session = session_service._sessions[str(session["session_id"])]
    session_service._sessions[str(session["session_id"])] = stored_session.model_copy(
        update={
            "last_tutor_response_at": datetime.now(timezone.utc)
            - timedelta(seconds=21)
        }
    )
    before = _pedagogical_state(session["session_id"])

    first = client.post("/interaction", json=request)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["nudge_delivery"]["status"] == "GENERATED"
    assert first_body["attempt_increment"] == 0
    assert first_body["attempt_count"] == session["attempt_count"]
    assert first_body["question_id"] == session["question_id"]
    assert first_body["current_phase"] == session["current_phase"]

    duplicate = client.post("/interaction", json=request)
    assert duplicate.status_code == 200
    duplicate_body = duplicate.json()
    assert duplicate_body["status"] == "DUPLICATE_TURN"
    assert duplicate_body["message"] == first_body["message"]
    assert duplicate_body["interaction_state_version"] == first_body[
        "interaction_state_version"
    ]

    presented_request = _interaction(
        session,
        student_id,
        "TURN-NUDGE-PRESENTED-1",
        "NUDGE_PRESENTED",
        str(session["last_tutor_turn_id"]),
    )
    presented_request.update(
        {
            "input_source": "SYSTEM",
            "text_input": None,
            "nudge_id": first_body["nudge_delivery"]["interaction_id"],
        }
    )
    presented = client.post("/interaction", json=presented_request)
    assert presented.status_code == 200, presented.text
    assert presented.json()["nudge_delivery"]["status"] == "PRESENTED"
    assert presented.json()["attempt_count"] == session["attempt_count"]
    assert presented.json()["current_phase"] == session["current_phase"]
    assert _pedagogical_state(session["session_id"]) == before


def test_inactivity_suppression_has_no_displayable_message() -> None:
    session = _start("ST155")
    request = _interaction(
        session,
        "ST155",
        "TURN-NUDGE-SUPPRESSED-1",
        "INACTIVITY_NUDGE",
        str(session["last_tutor_turn_id"]),
    )
    request.update({"input_source": "SYSTEM", "text_input": None})

    response = client.post("/interaction", json=request)

    assert response.status_code == 200
    assert response.json()["status"] == "NUDGE_SUPPRESSED"
    assert response.json()["nudge_delivery"] is None
    assert response.json()["message"] == ""
    assert response.json()["message_voice"] == ""
