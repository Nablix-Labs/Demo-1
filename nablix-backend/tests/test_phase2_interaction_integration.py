from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.adapters import provider
from app.adapters.student_model import StudentModelServiceAdapter
from app.ai_engine import classifier
from app.ai_engine.schemas import (
    ExplainAgainRequest,
    ExplainAgainResponse,
    OpenAIExplainAgainMessage,
)
from app.ai_engine.openai_client import OpenAITutorMessage
from app.core.config import Settings
from app.main import app
from app.models.adapters import VisualCue as AdapterVisualCue
from app.models.guided_learning import GeneratedConcept, GeneratedQuestionRubric

from app.models.student_model_session import (
    GuidedSupportEvent,
    RoutingReasonCode,
    StudentModelSessionEvent,
    StudentModelSessionEventResponse,
)
from app.services import interaction_service, session_service
from tests.test_session_events import _event_response, _session_opened_response


client = TestClient(app, headers={"Authorization": "Bearer test-token"})


@pytest.mark.parametrize(
    "reason_code",
    [
        "GUIDED_VISUAL_SUPPORT_REQUIRED",
        "GUIDED_PHASE_COMPLETED",
        "PARALLEL_EXAMPLE_REQUIRED",
        "SESSION_RESUMED",
    ],
)
def test_all_guided_routing_reasons_are_response_safe(reason_code: str) -> None:
    assert RoutingReasonCode(reason_code).value == reason_code


def test_repeated_unresolved_guided_explanation_never_forces_completion() -> None:
    assert interaction_service._may_force_complete_repeated_explanation(
        "GUIDED_PRACTICE",
        False,
        3,
    ) is False
    assert interaction_service._may_force_complete_repeated_explanation(
        "GUIDED_PRACTICE",
        True,
        3,
    ) is False


def test_atomic_guided_events_are_disabled_for_legacy_student_model() -> None:
    assert Settings().student_model_atomic_guided_events_enabled is False
    event = GuidedSupportEvent(
        request_id="REQ-LEGACY-STUCK",
        event_type="GUIDED_SUPPORT_ESCALATION_REQUIRED",
        source_turn_id="TURN-LEGACY-STUCK",
        expected_journey_version=1,
        topic_id="ALG-ORI-02",
        student_id="ST150",
        timestamp="2026-08-05T00:00:00Z",
        question_id="Q-T02-004",
        micro_skill_id="T02.M1",
    )
    assert event.triggering_response is None
    assert event.error_code is None


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

        def build_tutor_message(self, **kwargs: object) -> OpenAITutorMessage:
            # Guided support is narrated through the AI engine since
            # "feat: narrate guided support in tutor responses".
            del kwargs
            return OpenAITutorMessage(
                tutor_message="Look at the support shown and try the next step.",
                tutor_message_voice_optimised=(
                    "Look at the support shown and try the next step."
                ),
                confidence=0.9,
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

    stored = client.get(
        f"/session/{session['session_id']}",
        params={"student_id": session["student_id"]},
    )
    assert stored.status_code == 200
    assert stored.json()["attempt_count"] == first_body["attempt_count"]


def test_duplicate_turn_repeats_the_response_without_new_openai_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class _CountingClient:
        def build_tutor_message(self, **kwargs: object) -> OpenAITutorMessage:
            del kwargs
            calls.append("build_tutor_message")
            return OpenAITutorMessage(
                tutor_message="Look at the support shown and try the next step.",
                tutor_message_voice_optimised=(
                    "Look at the support shown and try the next step."
                ),
                confidence=0.9,
            )

    monkeypatch.setattr(
        interaction_service,
        "build_openai_ai_engine_client",
        lambda settings: _CountingClient(),
    )

    student_id = "ST152"
    session = _start(student_id)
    request = _interaction(
        session,
        student_id,
        "TURN-DUPLICATE-OPENAI",
        "ANSWER_SUBMISSION",
        None,
    )

    first = client.post("/interaction", json=request)
    assert first.status_code == 200, first.text
    calls_after_first = len(calls)
    # Keeps the comparison below honest: the first turn really does call OpenAI.
    assert calls_after_first > 0

    duplicate = client.post("/interaction", json=request)

    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "DUPLICATE_TURN"
    assert duplicate.json()["message"] == first.json()["message"]
    assert duplicate.json()["support_message"] == first.json()["support_message"]
    assert len(calls) == calls_after_first


def test_explain_again_is_cached_and_does_not_grade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_requests: list[ExplainAgainRequest] = []

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
            explain_request = kwargs["request"]
            assert isinstance(explain_request, ExplainAgainRequest)
            captured_requests.append(explain_request)
            return OpenAIExplainAgainMessage(
                tutor_message="Try viewing the current relationship from the starting value.",
                tutor_message_voice_optimised="Try viewing the current relationship from the starting value.",
                answer_reveal_risk=False,
                confidence=0.95,
            )

        def generate_explain_again_response(
            self,
            **kwargs: object,
        ) -> OpenAIExplainAgainMessage:
            return self.generate_explain_again_message(**kwargs)



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
    stored_session = session_service._sessions[str(session["session_id"])]
    # Explain Again reads the persisted authored cue since
    # "fix: preserve authored visual cue payload".
    session_service._sessions[str(session["session_id"])] = stored_session.model_copy(
        update={
            "show_visual_cue": True,
            "active_visual_cue": AdapterVisualCue(
                show=True,
                cue_type="VC-T01-ADD-NOT-MULTIPLY",
                description=(
                    "The starting value changes while the operation stays fixed."
                ),
                actions=[],
            ),
        }
    )
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
    assert captured_requests[0].visible_visual_cue is not None
    assert captured_requests[0].visible_visual_cue.cue_id == "VC-T01-ADD-NOT-MULTIPLY"
    assert captured_requests[0].visible_visual_cue.cue_type is None


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

    stored = client.get(
        f"/session/{session['session_id']}",
        params={"student_id": session["student_id"]},
    )
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
    assert first_body["accepted_turn_id"] == request["turn_id"]
    after_claim = session_service._sessions[str(session["session_id"])]
    assert after_claim.last_processed_turn_id == stored_session.last_processed_turn_id
    assert after_claim.last_tutor_turn_id == stored_session.last_tutor_turn_id

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
    after_presented = session_service._sessions[str(session["session_id"])]
    assert after_presented.last_processed_turn_id == stored_session.last_processed_turn_id
    assert after_presented.last_tutor_turn_id == stored_session.last_tutor_turn_id
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
