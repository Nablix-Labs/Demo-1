from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.adapters import provider
from app.adapters.student_model import StudentModelServiceAdapter
from app.ai_engine import classifier
from app.ai_engine.schemas import OpenAIExplainAgainMessage
from app.core.config import Settings
from app.main import app
from app.models.guided_learning import GeneratedConcept, GeneratedQuestionRubric
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
    return response.json()


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
    assert first.status_code == 200
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


def test_explain_again_is_cached_and_does_not_grade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ExplainAgainClient:
        def generate_guided_rubric(self, **kwargs: object) -> GeneratedQuestionRubric:
            return GeneratedQuestionRubric(
                question_id=str(kwargs["question_id"]),
                required_concepts=[
                    GeneratedConcept(
                        concept_id="CURRENT_CONCEPT",
                        description="Explains the current concept.",
                        required=True,
                    )
                ],
                completion_rule="ALL_REQUIRED_CONCEPTS",
                cache_key="phase2-explain-test",
                prompt_version="1.0.0",
            )

        def generate_explain_again_message(
            self,
            **kwargs: object,
        ) -> OpenAIExplainAgainMessage:
            return OpenAIExplainAgainMessage(
                tutor_message="Try viewing the current relationship from the starting value.",
                tutor_message_voice_optimised="Try viewing the current relationship from the starting value.",
                answer_reveal_risk=False,
                confidence=0.95,
            )

    explain_client = _ExplainAgainClient()
    monkeypatch.setattr(
        interaction_service,
        "build_openai_ai_engine_client",
        lambda settings: explain_client,
    )
    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: explain_client,
    )
    student_id = "ST152"
    session = _start(student_id)
    request = _interaction(
        session,
        student_id,
        "TURN-EXPLAIN-1",
        "EXPLAIN_AGAIN",
        None,
    )

    first = client.post("/interaction", json=request)
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["accepted_turn_id"] == "TURN-EXPLAIN-1"
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
    assert duplicate_body["attempt_count"] == first_body["attempt_count"]


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
    request.pop("text_input")

    stored_session = session_service._sessions[str(session["session_id"])]
    session_service._sessions[str(session["session_id"])] = stored_session.model_copy(
        update={
            "last_tutor_response_at": datetime.now(timezone.utc)
            - timedelta(seconds=21)
        }
    )

    first = client.post("/interaction", json=request)
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["attempt_increment"] == 0
    assert first_body["attempt_count"] == session["attempt_count"]
    assert first_body["question_id"] == session["question_id"]
    assert first_body["current_phase"] == session["current_phase"]
    assert first_body["nudge_delivery"] == {
        "interaction_id": "TURN-NUDGE-1",
        "status": "GENERATED",
        "message": first_body["message"],
    }
    assert first_body["inactivity_policy"] == {
        "initial_idle_threshold_ms": 20000,
        "cooldown_ms": 30000,
        "max_nudges_per_tutor_turn": 2,
        "generated_nudge_rate_limit": 4,
    }

    duplicate = client.post("/interaction", json=request)
    assert duplicate.status_code == 200
    duplicate_body = duplicate.json()
    assert duplicate_body["status"] == "DUPLICATE_TURN"
    assert duplicate_body["message"] == first_body["message"]
    assert duplicate_body["interaction_state_version"] == first_body[
        "interaction_state_version"
    ]

    presented_request = {
        **request,
        "interaction_type": "NUDGE_PRESENTED",
        "turn_id": "TURN-NUDGE-PRESENTED-1",
        "nudge_id": "TURN-NUDGE-1",
    }
    presented = client.post("/interaction", json=presented_request)
    assert presented.status_code == 200
    presented_body = presented.json()
    assert presented_body["nudge_delivery"]["status"] == "PRESENTED"
    assert presented_body["attempt_count"] == session["attempt_count"]
    assert presented_body["consecutive_stuck_count"] == 0


def test_inactivity_nudge_is_suppressed_before_server_threshold() -> None:
    student_id = "ST155"
    session = _start(student_id)
    request = _interaction(
        session,
        student_id,
        "TURN-NUDGE-EARLY",
        "INACTIVITY_NUDGE",
        None,
    )
    request["input_source"] = "SYSTEM"
    request.pop("text_input")

    response = client.post("/interaction", json=request)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "NUDGE_SUPPRESSED"
    assert body["nudge_delivery"] is None
    assert body["attempt_increment"] == 0
