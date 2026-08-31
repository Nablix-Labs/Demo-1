import asyncio
import itertools
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.ai_engine.classifier_config import load_classifier_rules
from app.models.guided_learning import (
    ActiveGuidedRescue,
    GuidedRescue,
    ParallelExample,
    TutorSolved,
)
from app.models.session import (
    RescueAdvanceRequest,
    RescueRenderAckRequest,
    SessionRecord,
)
from fastapi.testclient import TestClient

from app.adapters import provider
from app.adapters.student_model import StudentModelServiceAdapter
from app.core.config import Settings
from app.main import app
from app.models.student_model_session import StudentModelSessionEventResponse
from app.services import interaction_service, rescue_presentation, session_service
from app.services.canvas_annotations import plan_rescue_canvas_actions
from tests.test_canvas import _session_opened_response
from tests.test_session_events import _event_response

client = TestClient(app, headers={"Authorization": "Bearer test-token"})


def test_parallel_rescue_requires_render_ack_before_advancing() -> None:
    rescue = GuidedRescue(
        rescue_type="PARALLEL_EXAMPLE",
        micro_skill_id="T02.M1",
        parallel_example=ParallelExample(
            parallel_example_id="PAR-T02-M1",
            problem="Solve y + 3 = 8.",
            worked_steps=["Subtract 3 from both sides.", "y = 5."],
            final_answer="y = 5",
        ),
        tutor_solved=None,
    )

    active = rescue_presentation.active_rescue_from(
        question_id="Q-T02-004",
        rescue=rescue,
        canonical_answer="x = 5",
        request_id="REQ-1",
    )

    assert active.current_step_index == 1
    assert active.steps == [
        "Solve y + 3 = 8.",
        "Subtract 3 from both sides.",
        "y = 5.",
    ]

    with pytest.raises(HTTPException, match="render acknowledgement"):
        asyncio.run(
            rescue_presentation.advance_active_rescue(
                active,
                question_id="Q-T02-004",
                rescue_id=active.rescue_id,
                current_step_index=1,
            )
        )

    acknowledged = rescue_presentation.acknowledge_active_rescue(
        active,
        action_id=active.current_action_id,
        target_object_id=active.current_target_object_id,
    )
    advanced = asyncio.run(
        rescue_presentation.advance_active_rescue(
            acknowledged,
            question_id="Q-T02-004",
            rescue_id=acknowledged.rescue_id,
            current_step_index=1,
        )
    )

    assert advanced.current_step_index == 2


def test_older_advance_returns_the_current_stable_action() -> None:
    rescue = GuidedRescue(
        rescue_type="PARALLEL_EXAMPLE",
        micro_skill_id="T02.M1",
        parallel_example=ParallelExample(
            parallel_example_id="PAR-T02-M1",
            problem="Solve y + 3 = 8.",
            worked_steps=["Subtract 3 from both sides."],
            final_answer="y = 5",
        ),
        tutor_solved=None,
    )
    active = rescue_presentation.active_rescue_from("Q-T02-004", rescue, "x = 5", "REQ-2")
    acknowledged = rescue_presentation.acknowledge_active_rescue(
        active, active.current_action_id, active.current_target_object_id
    )
    current = asyncio.run(
        rescue_presentation.advance_active_rescue(
            acknowledged, "Q-T02-004", acknowledged.rescue_id, 1
        )
    )

    replayed = asyncio.run(
        rescue_presentation.advance_active_rescue(
            current, "Q-T02-004", current.rescue_id, 1
        )
    )

    assert replayed.current_step_index == 2
    assert rescue_presentation.rescue_action_for(replayed).action_id == (
        f"{current.rescue_id}:step:2"
    )


def test_advance_rejects_a_future_step_index() -> None:
    active = _parallel_active()
    acknowledged = rescue_presentation.acknowledge_active_rescue(
        active, active.current_action_id, active.current_target_object_id
    )

    with pytest.raises(HTTPException, match="future step index"):
        asyncio.run(
            rescue_presentation.advance_active_rescue(
                acknowledged, "Q-T02-004", acknowledged.rescue_id, 2
            )
        )


def test_advance_rejects_a_mismatched_rescue_id() -> None:
    active = _parallel_active()

    with pytest.raises(HTTPException, match="does not own"):
        asyncio.run(
            rescue_presentation.advance_active_rescue(
                active, "Q-T02-004", "OTHER-RESCUE", 1
            )
        )


def test_tutor_solved_rescue_id_tracks_the_student_model_request() -> None:
    rescue = GuidedRescue(
        rescue_type="TUTOR_SOLVED",
        micro_skill_id="T02.M1",
        parallel_example=None,
        tutor_solved=TutorSolved(
            explanation="Undo the addition.",
            answer_steps=["Subtract 6.", "x = 5"],
            final_answer="x = 5",
        ),
    )

    first = rescue_presentation.active_rescue_from("Q-T02-004", rescue, "", "REQ-A")
    second = rescue_presentation.active_rescue_from("Q-T02-004", rescue, "", "REQ-B")
    replay = rescue_presentation.active_rescue_from("Q-T02-004", rescue, "", "REQ-A")

    assert first.rescue_id != second.rescue_id
    assert first.rescue_id == replay.rescue_id


# --- endpoint lifecycle -----------------------------------------------------


def _parallel_active(worked: list[str] | None = None) -> ActiveGuidedRescue:
    worked = worked if worked is not None else ["Subtract 3 from both sides."]
    rescue = GuidedRescue(
        rescue_type="PARALLEL_EXAMPLE",
        micro_skill_id="T02.M1",
        parallel_example=ParallelExample(
            parallel_example_id="PAR-T02-M1",
            problem="Solve y + 3 = 8.",
            worked_steps=worked,
            final_answer="y = 5",
        ),
        tutor_solved=None,
    )
    return rescue_presentation.active_rescue_from(
        "Q-T02-004", rescue, "x = 5", "REQ-PAR"
    )


def _tutor_solved_active() -> ActiveGuidedRescue:
    rescue = GuidedRescue(
        rescue_type="TUTOR_SOLVED",
        micro_skill_id="T02.M1",
        parallel_example=None,
        tutor_solved=TutorSolved(
            explanation="Undo the addition.",
            answer_steps=["Subtract 6 from both sides.", "x = 5"],
            final_answer="x = 5",
        ),
    )
    return rescue_presentation.active_rescue_from(
        "Q-T02-004", rescue, "x = 5", "REQ-TS"
    )


_seeded = itertools.count(900)


def _seed_session(active: ActiveGuidedRescue) -> str:
    session_id = f"SESSION{next(_seeded)}"
    event = session_service.StudentModelSessionEventResponse.model_validate(
        _event_response("ORIENTATION_COMPLETED", "REQ-SEED")
    )
    session_service._sessions[session_id] = SessionRecord.model_construct(
        session_id=session_id,
        student_id="ST001",
        concept_id="ALG_LINEAR_ONE_STEP",
        started_at=datetime.now(timezone.utc),
        current_phase="GUIDED_PRACTICE",
        current_question="Solve for x: x + 6 = 11",
        question_id="Q-T02-004",
        question_number=1,
        interaction_mode="TEXT",
        ui_state="GUIDED_PRACTICE",
        message="",
        hint_count=0,
        last_tutor_response_at=datetime.now(timezone.utc),
        status="started",
        active_guided_rescue=active,
        student_model_event=event,
    )
    return session_id


def _ack(session_id: str, active: ActiveGuidedRescue):
    return asyncio.run(
        session_service.acknowledge_rescue_render(
            session_id,
            RescueRenderAckRequest(
                student_id="ST001",
                action_id=active.current_action_id,
                status="RENDERED",
                target_object_id=active.current_target_object_id,
            ),
            "test-token",
        )
    )


def _advance(session_id: str, rescue_id: str, index: int):
    return asyncio.run(
        session_service.advance_rescue(
            session_id,
            RescueAdvanceRequest(
                student_id="ST001",
                question_id="Q-T02-004",
                rescue_id=rescue_id,
                current_step_index=index,
                trigger="UI_NEXT_STEP",
            ),
        )
    )


def test_initial_action_is_acknowledged_by_the_endpoint() -> None:
    active = _parallel_active()
    session_id = _seed_session(active)
    planned = plan_rescue_canvas_actions(
        rescue_presentation.rescue_context_for(active),
        "TURN-1",
        "x = 5",
        load_classifier_rules().guided_learning.canvas_rescue_wording,
    )

    assert planned[0].action_id == active.current_action_id

    result = _ack(session_id, active)

    assert result.completed is False
    assert result.action is not None
    assert result.action.action_id == active.current_action_id
    stored = session_service._sessions[session_id].active_guided_rescue
    assert stored is not None
    assert stored.rendered_action_ids == [active.current_action_id]


def test_advance_without_acknowledgement_fails_at_the_endpoint() -> None:
    active = _parallel_active()
    session_id = _seed_session(active)

    with pytest.raises(HTTPException, match="render acknowledgement"):
        _advance(session_id, active.rescue_id, 1)


def test_concurrent_identical_advances_advance_the_cursor_once() -> None:
    active = _parallel_active()
    session_id = _seed_session(active)
    _ack(session_id, active)

    async def both():
        return await asyncio.gather(
            session_service.advance_rescue(
                session_id,
                RescueAdvanceRequest(
                    student_id="ST001",
                    question_id="Q-T02-004",
                    rescue_id=active.rescue_id,
                    current_step_index=1,
                    trigger="UI_NEXT_STEP",
                ),
            ),
            session_service.advance_rescue(
                session_id,
                RescueAdvanceRequest(
                    student_id="ST001",
                    question_id="Q-T02-004",
                    rescue_id=active.rescue_id,
                    current_step_index=1,
                    trigger="VOICE_NEXT",
                ),
            ),
        )

    first, second = asyncio.run(both())

    assert first.action.action_id == second.action.action_id
    assert first.current_step_index == second.current_step_index == 2
    stored = session_service._sessions[session_id].active_guided_rescue
    assert stored is not None
    assert stored.current_step_index == 2


def test_final_parallel_acknowledgement_clears_the_rescue_and_keeps_the_phase() -> None:
    active = _parallel_active(worked=["y = 5"])
    session_id = _seed_session(active)
    _ack(session_id, active)
    _advance(session_id, active.rescue_id, 1)
    final = session_service._sessions[session_id].active_guided_rescue
    assert final is not None and final.is_final_step

    result = _ack(session_id, final)

    assert result.completed is True
    assert result.action is None
    session = session_service._sessions[session_id]
    assert session.active_guided_rescue is None
    assert session.current_phase == "GUIDED_PRACTICE"
    # The replay of a completed acknowledgement stays a 200.
    assert _ack(session_id, final).completed is True


class _StubStudentModel:
    def __init__(self, response: object) -> None:
        self._response = response
        self.events: list[object] = []

    async def send_session_event(self, event: object, access_token: str) -> object:
        self.events.append(event)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _stub_adapters(monkeypatch, response: object) -> _StubStudentModel:
    stub = _StubStudentModel(response)
    monkeypatch.setattr(
        session_service,
        "get_adapters",
        lambda: SimpleNamespace(student_model=stub),
    )
    return stub


def _phase3_response() -> object:
    return session_service.StudentModelSessionEventResponse.model_validate(
        _event_response("INDEPENDENT_QUESTION_SET_REQUESTED", "REQ-PHASE3")
    )


def _drive_to_final(session_id: str, active: ActiveGuidedRescue) -> ActiveGuidedRescue:
    current = active
    while not current.is_final_step:
        _ack(session_id, current)
        _advance(session_id, current.rescue_id, current.current_step_index)
        stored = session_service._sessions[session_id].active_guided_rescue
        assert stored is not None
        current = stored
    return current


def test_final_tutor_solved_acknowledgement_sends_one_phase3_event(monkeypatch) -> None:
    active = _tutor_solved_active()
    session_id = _seed_session(active)
    stub = _stub_adapters(monkeypatch, _phase3_response())
    final = _drive_to_final(session_id, active)

    result = _ack(session_id, final)

    assert result.completed is True
    assert [event.event_type for event in stub.events] == [
        "INDEPENDENT_QUESTION_SET_REQUESTED"
    ]
    assert stub.events[0].request_id == final.current_action_id
    session = session_service._sessions[session_id]
    assert session.active_guided_rescue is None
    assert session.current_phase == "INDEPENDENT_PRACTICE"
    assert session.question_id == "Q-T02-004"

    # Replay after completion neither 409s nor sends a second event.
    assert _ack(session_id, final).completed is True
    assert len(stub.events) == 1


def test_failed_final_transition_stays_retryable(monkeypatch) -> None:
    active = _tutor_solved_active()
    session_id = _seed_session(active)
    stub = _stub_adapters(monkeypatch, RuntimeError("student model down"))
    final = _drive_to_final(session_id, active)

    with pytest.raises(HTTPException) as failure:
        _ack(session_id, final)

    assert failure.value.status_code == 503
    pending = session_service._sessions[session_id].active_guided_rescue
    assert pending is not None
    assert pending.is_final_step
    assert final.current_action_id in pending.rendered_action_ids

    stub._response = _phase3_response()
    assert _ack(session_id, final).completed is True
    assert session_service._sessions[session_id].active_guided_rescue is None


def test_snapshots_restore_rescue_state() -> None:
    legacy = SessionRecord.model_validate(
        {
            **session_service._sessions[_seed_session(_parallel_active())].model_dump(),
            "active_guided_rescue": None,
        }
    )
    assert legacy.active_guided_rescue is None

    active = _parallel_active()
    session_id = _seed_session(active)
    _ack(session_id, active)
    _advance(session_id, active.rescue_id, 1)
    snapshot = session_service._sessions[session_id].model_dump()

    restored = SessionRecord.model_validate(snapshot)

    assert restored.active_guided_rescue is not None
    assert restored.active_guided_rescue.current_step_index == 2
    assert restored.active_guided_rescue.rendered_action_ids == [
        active.current_action_id
    ]


def _stepwise_rules():
    rules = load_classifier_rules()
    return rules.model_copy(
        update={
            "guided_learning": rules.guided_learning.model_copy(
                update={"canvas_rescue_presentation_enabled": True}
            )
        }
    )


async def _tutor_solved_rescue_event(adapter, event, access_token):
    del adapter, access_token
    if event.event_type == "SESSION_OPENED":
        body = _session_opened_response("PHASE_2_GUIDED_LEARNING")
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)
    response = StudentModelSessionEventResponse.model_validate(
        _event_response(event.event_type, event.request_id)
    )
    assert response.phase_payload is not None
    return response.model_copy(
        update={
            "phase_payload": response.phase_payload.model_copy(
                update={
                    "payload_type": "RESCUE",
                    "question_set": None,
                    "rescue_to_serve": {
                        "rescue_type": "TUTOR_SOLVED",
                        "micro_skill_id": "T02.M1",
                        "tutor_solved": {
                            "explanation": "Undo the addition.",
                            "final_answer": "x = 5",
                            "answer_steps": [
                                "Subtract 4 from both sides.",
                                "The correct answer is x = 5.",
                            ],
                        },
                    },
                }
            )
        }
    )


def test_stepwise_interaction_hides_the_full_rescue_payload(monkeypatch) -> None:
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
    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(
        StudentModelServiceAdapter, "send_session_event", _tutor_solved_rescue_event
    )
    monkeypatch.setattr(interaction_service, "load_classifier_rules", _stepwise_rules)
    started = client.post(
        "/session/start",
        json={
            "student_id": "ST920",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert started.status_code == 200, started.text
    session_id = started.json()["session_id"]

    response = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": "ST920",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "turn_id": "TURN-STEPWISE-1",
            "text_input": "x = 4",
            "current_phase": "GUIDED_PRACTICE",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": "Q-T02-004",
            "hint_count": 0,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["guided_rescue"] is None
    serialized = response.text
    assert "The correct answer is x = 5." not in serialized
    active = session_service._get_owned_session(session_id, "ST920").active_guided_rescue
    assert active is not None
    assert active.current_step_index == 1
