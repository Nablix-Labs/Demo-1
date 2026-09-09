"""Returning from a Phase 2 repair cycle to the checkpoint that caused it.

Two different things finish a Guided phase, and until 9 Sep 2026 both took the
same exit. An ordinary first-time completion has earned Independent practice, so
it asks for an Independent question set. A *repair* cycle -- entered because a
Phase 3 checkpoint failed -- owes the student the same checkpoint question back;
asking for a new Independent set there restarts Phase 3, discards the checkpoint,
and loses the repair counts that decide whether a second cycle is still allowed.

Verified on ST010 (session b5eed587..., topic ALG-KS3-01): the backend had no
`GUIDED_REPAIR_COMPLETED` reference at all, so the loop could not close even once
the repair targets were correct.

The decision lives in one place -- `complete_guided_progression` -- because the
deferred Tutor-Solved completion has to reach the same conclusion as an ordinary
correct answer, and a second copy of this branch is how they drift apart.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.remediation import StudentModelIntervention
from app.models.session import SessionRecord
from app.models.student_model_session import (
    CheckpointRepairState,
    GuidedRepairCompletedEvent,
    StudentModelSessionEventResponse,
)
from app.services import session_service
from tests.test_session_events import _event_response

CHECKPOINT_QUESTION = "Q-T01-007"
CHECKPOINT_USAGE = "QU-T01-007-P3"
REPAIR_SKILL = "T02.M1"


def _guided_completed_journey(
    *,
    paused_for_repair: bool,
    repair_count: int = 0,
    repair_cycle_no: int | None = None,
) -> dict:
    """A Guided phase that has just finished, with or without a live checkpoint."""

    body = _event_response("ORIENTATION_COMPLETED", "REQ-SEED")
    journey = body["journey_state"]
    assert isinstance(journey, dict)
    journey["phase_2_guided_learning"].update(
        {
            "status": "COMPLETED",
            "completed_micro_skill_ids": [REPAIR_SKILL],
            "remaining_micro_skill_ids": [],
            "highest_support_used_by_skill": {REPAIR_SKILL: "HINT"},
            "used_question_ids": ["Q-T02-004"],
            "current_question_id": None,
        }
    )
    if repair_cycle_no is not None:
        journey["phase_2_guided_learning"]["repair_cycle_no"] = repair_cycle_no
    if paused_for_repair:
        journey["phase_3_independent_practice"] = {
            "status": "PAUSED_FOR_REPAIR",
            "phase_visit_no": 1,
            "target_micro_skill_ids": [REPAIR_SKILL],
            "retry_required_micro_skill_ids": [REPAIR_SKILL],
            "used_question_ids": ["Q-T02-004"],
            "repair_state_by_skill": {
                REPAIR_SKILL: {
                    "status": (
                        "SECOND_PHASE_2_REPAIR_REQUIRED"
                        if repair_count == 1
                        else "PHASE_2_REPAIR_REQUIRED"
                    ),
                    "phase_2_repair_count": repair_count,
                    "fresh_retry_question_id": CHECKPOINT_QUESTION,
                    "checkpoint_question_usage_id": CHECKPOINT_USAGE,
                }
            },
        }
        journey["return_checkpoint"] = {
            "topic_id": journey["topic_id"],
            "phase": "PHASE_3_INDEPENDENT_PRACTICE",
            "phase_visit_no": 1,
            "question_position_no": 2,
            "micro_skill_id": REPAIR_SKILL,
            "checkpoint_question_id": CHECKPOINT_QUESTION,
            "question_usage_id": CHECKPOINT_USAGE,
            "resume_policy": "SAME_QUESTION_AT_CHECKPOINT",
        }
    return body


def _guided_completed_event(**kwargs: object) -> StudentModelSessionEventResponse:
    return StudentModelSessionEventResponse.model_validate(
        _guided_completed_journey(**kwargs)  # type: ignore[arg-type]
    )


_ids = iter(range(9000, 9999))


def _session(event: StudentModelSessionEventResponse) -> SessionRecord:
    session_id = f"SESSION{next(_ids)}"
    session = SessionRecord.model_construct(
        session_id=session_id,
        student_id="ST010",
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
        student_model_event=event,
    )
    session_service._sessions[session_id] = session
    return session


class _RecordingStudentModel:
    """Records what was sent, and can be made to lose its reply once."""

    def __init__(self, response: object, fail_times: int = 0) -> None:
        self._response = response
        self._fail_times = fail_times
        self.events: list[object] = []

    async def send_session_event(self, event: object, access_token: str) -> object:
        del access_token
        self.events.append(event)
        if self._fail_times > 0:
            self._fail_times -= 1
            raise RuntimeError("connection reset before the reply arrived")
        return self._response


def _stub(monkeypatch: pytest.MonkeyPatch, stub: _RecordingStudentModel) -> None:
    monkeypatch.setattr(
        session_service, "get_adapters", lambda: SimpleNamespace(student_model=stub)
    )


def _resume_response(
    event: StudentModelSessionEventResponse,
    repair_count: int,
) -> StudentModelSessionEventResponse:
    """What Student Model answers GUIDED_REPAIR_COMPLETED with: the same question."""

    body = event.model_dump(mode="json")
    journey = body["journey_state"]
    journey["version"] += 1
    journey["current_phase"] = "PHASE_3_INDEPENDENT_PRACTICE"
    journey["recommended_entry_phase"] = "PHASE_3_INDEPENDENT_PRACTICE"
    journey["phase_3_independent_practice"].update(
        {
            "status": "IN_PROGRESS",
            "phase_visit_no": 2,
            "remaining_micro_skill_ids": [REPAIR_SKILL],
            "current_question_id": CHECKPOINT_QUESTION,
            "current_question_usage_id": CHECKPOINT_USAGE,
            "current_attempt_sequence": 2,
            "current_attempt_type": "CHECKPOINT_REATTEMPT",
            "used_question_ids": ["Q-T02-004"],
        }
    )
    journey["phase_3_independent_practice"]["repair_state_by_skill"][REPAIR_SKILL].update(
        {"status": "RETURNED_FROM_PHASE_2_TO_SAME_QUESTION",
         "phase_2_repair_count": repair_count}
    )
    served = _event_response("INDEPENDENT_QUESTION_SET_REQUESTED", "REQ-RESUME")
    question = served["phase_payload"]["question_set"]["questions"][0]
    question["question_id"] = CHECKPOINT_QUESTION
    question["question_usage_id"] = CHECKPOINT_USAGE
    question["micro_skill_mappings"] = [
        {"micro_skill_id": REPAIR_SKILL, "is_primary": True, "weight": 1.0}
    ]
    body["phase_payload"] = {
        **served["phase_payload"],
        "payload_type": "RESUME_SAME_INDEPENDENT_QUESTION",
    }
    body["routing"] = {
        **body["routing"],
        "reason_code": "GUIDED_REPAIR_COMPLETED",
        "next_action": "RETURN_TO_SAME_PHASE_3_QUESTION",
        "resume_policy": "SAME_QUESTION_AT_CHECKPOINT",
        "resume_question_id": CHECKPOINT_QUESTION,
    }
    return StudentModelSessionEventResponse.model_validate(body)


def _complete(session: SessionRecord, event: StudentModelSessionEventResponse,
              turn_id: str = "TURN-1") -> SessionRecord:
    return asyncio.run(
        session_service.complete_guided_progression(session, event, turn_id, "TOKEN")
    )


def test_an_ordinary_guided_completion_still_starts_independent_practice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No checkpoint outstanding: nothing to return to, so Phase 3 begins."""

    event = _guided_completed_event(paused_for_repair=False)
    session = _session(event)
    stub = _RecordingStudentModel(
        StudentModelSessionEventResponse.model_validate(
            _event_response("INDEPENDENT_QUESTION_SET_REQUESTED", "REQ-P3")
        )
    )
    _stub(monkeypatch, stub)

    _complete(session, event)

    assert [e.event_type for e in stub.events] == ["INDEPENDENT_QUESTION_SET_REQUESTED"]
    sent = stub.events[0]
    assert [r.micro_skill_id for r in sent.phase2_repair_results] == [REPAIR_SKILL]
    assert sent.phase2_repair_results[0].highest_support_used == "HINT"


def test_a_repair_completion_returns_to_the_same_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point: same question, same usage, same attempt sequence."""

    event = _guided_completed_event(
        paused_for_repair=True, repair_count=0, repair_cycle_no=1
    )
    session = _session(event)
    stub = _RecordingStudentModel(_resume_response(event, repair_count=1))
    _stub(monkeypatch, stub)

    updated = _complete(session, event)

    assert [e.event_type for e in stub.events] == ["GUIDED_REPAIR_COMPLETED"]
    sent = stub.events[0]
    assert sent.micro_skill_ids == [REPAIR_SKILL]
    assert sent.repair_cycle_no == 1
    assert sent.expected_journey_version == event.journey_state.version
    assert sent.topic_id == event.journey_state.topic_id

    # Applied, not merely received.
    assert updated.current_phase == "INDEPENDENT_PRACTICE"
    assert updated.question_id == CHECKPOINT_QUESTION
    phase3 = updated.student_model_event.journey_state.phase_3_independent_practice
    assert phase3.current_question_usage_id == CHECKPOINT_USAGE
    assert phase3.current_attempt_sequence == 2
    assert "Q-T02-004" in phase3.used_question_ids
    # The checkpoint identity survives, and the projection names the return.
    checkpoint = updated.student_model_event.journey_state.return_checkpoint
    assert checkpoint is not None
    assert checkpoint.checkpoint_question_id == CHECKPOINT_QUESTION
    assert checkpoint.question_usage_id == CHECKPOINT_USAGE
    assert (
        updated.student_model_event.phase_payload.payload_type
        == "RESUME_SAME_INDEPENDENT_QUESTION"
    )
    # Position comes from the checkpoint, not from a recount of the served set.
    assert updated.question_number == 2


def test_the_second_repair_cycle_carries_its_own_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cycle 2 must not be reported as cycle 1, or the count never reaches the max."""

    event = _guided_completed_event(
        paused_for_repair=True, repair_count=1, repair_cycle_no=2
    )
    session = _session(event)
    stub = _RecordingStudentModel(_resume_response(event, repair_count=2))
    _stub(monkeypatch, stub)

    updated = _complete(session, event)

    assert stub.events[0].repair_cycle_no == 2
    repair = (
        updated.student_model_event.journey_state.phase_3_independent_practice
        .repair_state_by_skill[REPAIR_SKILL]
    )
    assert repair.phase_2_repair_count == 2
    assert updated.question_id == CHECKPOINT_QUESTION


def test_a_deferred_tutor_solved_completion_takes_the_same_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tutor-Solved defers the transition; deferring must not change where it goes.

    The rescue owes the Phase 2 -> Phase 3 move at the moment the student
    acknowledges the last step. If that path decided separately it would ask for
    a fresh Independent set and lose the checkpoint -- the same bug, reachable
    only through the rescue.
    """

    event = _guided_completed_event(
        paused_for_repair=True, repair_count=0, repair_cycle_no=1
    )
    session = _session(event)
    stub = _RecordingStudentModel(_resume_response(event, repair_count=1))
    _stub(monkeypatch, stub)
    active = SimpleNamespace(current_action_id="ACTION-RESCUE-FINAL")

    updated = asyncio.run(
        session_service._complete_tutor_solved_rescue(session, active, "TOKEN")
    )

    assert [e.event_type for e in stub.events] == ["GUIDED_REPAIR_COMPLETED"]
    assert stub.events[0].micro_skill_ids == [REPAIR_SKILL]
    assert updated.question_id == CHECKPOINT_QUESTION


def test_a_lost_reply_resends_the_identical_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The event is persisted before it is sent, so a retry cannot re-decide.

    A lost reply is indistinguishable from a lost request at this end. Deciding
    again would read a journey that may already have moved; re-sending the stored
    event keeps one request identity, so Student Model's own replay returns the
    first answer instead of grading or counting a second time.
    """

    event = _guided_completed_event(
        paused_for_repair=True, repair_count=0, repair_cycle_no=1
    )
    session = _session(event)
    stub = _RecordingStudentModel(
        _resume_response(event, repair_count=1), fail_times=1
    )
    _stub(monkeypatch, stub)

    # A transport failure must reach the client as a recoverable 503, not as the
    # 500 an unhandled exception would produce. The distinction is the whole
    # point: the client is told to reopen the session, and 500 INTERNAL_ERROR
    # reads as a bug to give up on rather than a state to retry.
    with pytest.raises(HTTPException) as failed:
        _complete(session, event)
    assert failed.value.status_code == 503
    assert failed.value.detail["code"] == "PROGRESSION_RETRY_REQUIRED"

    # The pending event outlived the failure, and no work may be submitted until
    # it is resolved.
    pending = session_service._sessions[session.session_id]
    assert pending.pending_guided_progression is not None
    assert pending.pending_guided_progression.event_type == "GUIDED_REPAIR_COMPLETED"
    with pytest.raises(HTTPException) as refused:
        session_service.require_learning_active(pending)
    assert refused.value.detail["code"] == "SESSION_STATE_REFRESH_REQUIRED"

    recovered = asyncio.run(
        session_service.resume_guided_progression(pending, "TOKEN")
    )

    assert len(stub.events) == 2
    first, second = stub.events
    assert first.request_id == second.request_id, "the retry booked a new attempt"
    assert first.model_dump() == second.model_dump()
    assert recovered.question_id == CHECKPOINT_QUESTION
    assert recovered.pending_guided_progression is None
    assert recovered.journey_recovery_required is False
    repair = (
        recovered.student_model_event.journey_state.phase_3_independent_practice
        .repair_state_by_skill[REPAIR_SKILL]
    )
    assert repair.phase_2_repair_count == 1, "the repair was counted twice"


@pytest.mark.parametrize(
    ("repair_count", "repair_cycle_no", "status"),
    [
        # Cycle number disagrees with the count already recorded.
        (0, 2, "PHASE_2_REPAIR_REQUIRED"),
        (1, 1, "SECOND_PHASE_2_REPAIR_REQUIRED"),
        # Counts line up, but the checkpoint is not waiting for a repair at all:
        # the topic is frozen pending an intervention review, and accepting a
        # completion here would flip Phase 3 back to IN_PROGRESS behind it.
        (1, 2, "AUTOMATED_REMEDIATION_EXHAUSTED"),
    ],
)
def test_an_inconsistent_repair_state_is_refused_rather_than_guessed(
    monkeypatch: pytest.MonkeyPatch,
    repair_count: int,
    repair_cycle_no: int,
    status: str,
) -> None:
    """A repair whose identity does not add up must not be completed anyway.

    Guessing here returns the student to a checkpoint nobody agreed on, and
    increments a count that decides whether remediation escalates.
    """

    event = _guided_completed_event(
        paused_for_repair=True, repair_count=repair_count, repair_cycle_no=repair_cycle_no
    )
    event.journey_state.phase_3_independent_practice.repair_state_by_skill[
        REPAIR_SKILL
    ].status = status
    session = _session(event)
    stub = _RecordingStudentModel(_resume_response(event, repair_count=repair_count + 1))
    _stub(monkeypatch, stub)

    with pytest.raises(HTTPException) as raised:
        _complete(session, event)

    assert raised.value.status_code == 503
    assert stub.events == [], "an inconsistent repair was sent anyway"


def test_a_repair_state_without_a_count_still_parses() -> None:
    """Student Model legitimately sends a repair state carrying only `status`.

    Two of its transitions build the entry with `.setdefault(skill, {})` and then
    write `status` alone. That is reachable whenever a skill enters
    retry_required through apply_fresh_question_unavailable, which creates no
    repair state at all -- the ST017 T01.M7 content gap, which becomes a
    *successful* retry as soon as the missing question is authored.

    Requiring phase_2_repair_count made the whole event unparseable, so the turn
    500'd on a reply that was perfectly valid upstream.
    """

    body = _event_response("INDEPENDENT_QUESTION_SET_REQUESTED", "REQ-PARTIAL")
    body["journey_state"]["phase_3_independent_practice"]["repair_state_by_skill"] = {
        "T01.M7": {"status": "FRESH_RETRY_COMPLETED"}
    }

    parsed = StudentModelSessionEventResponse.model_validate(body)

    repair = parsed.journey_state.phase_3_independent_practice.repair_state_by_skill
    assert repair["T01.M7"].status == "FRESH_RETRY_COMPLETED"
    # A skill that has been through no repair cycle reads as zero.
    assert repair["T01.M7"].phase_2_repair_count == 0


def test_a_partial_repair_state_cannot_pass_as_a_completed_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defaulting the count must not soften the repair-completion check.

    Reading a missing count as zero is only safe because the *status* still has
    to say a repair is awaiting completion. A FRESH_RETRY_COMPLETED entry with a
    defaulted zero must still be refused rather than accepted as cycle 1.
    """

    event = _guided_completed_event(
        paused_for_repair=True, repair_count=0, repair_cycle_no=1
    )
    repair = event.journey_state.phase_3_independent_practice.repair_state_by_skill
    repair[REPAIR_SKILL] = CheckpointRepairState.model_validate(
        {"status": "FRESH_RETRY_COMPLETED"}
    )
    session = _session(event)
    stub = _RecordingStudentModel(_resume_response(event, repair_count=1))
    _stub(monkeypatch, stub)

    with pytest.raises(HTTPException) as raised:
        _complete(session, event)

    assert raised.value.status_code == 503
    assert stub.events == []


def test_an_intervention_is_reported_before_a_refresh_is_demanded() -> None:
    """Both conditions can hold; the intervention is the one that matters.

    A frozen topic can still hit a version conflict, and refreshing does not
    clear an intervention. Reporting SESSION_STATE_REFRESH_REQUIRED first told
    the student to refresh and then showed them the intervention anyway, and hid
    the code an intervention-aware client branches on.
    """

    event = _guided_completed_event(paused_for_repair=False)
    session = _session(event)
    frozen = session.model_copy(
        update={
            "journey_recovery_required": True,
            "intervention": StudentModelIntervention.model_validate(
                {
                    "intervention_id": "INT-ALG-KS3-01-T01.M5",
                    "scope": "TOPIC",
                    "topic_id": "ALG-KS3-01",
                    "trigger_micro_skill_ids": ["T01.M5"],
                    "reason_code": "EARLIEST_TOPIC_NO_BACKWARD_ROUTE",
                    "student_input_status": "REQUIRED",
                }
            ),
        }
    )

    with pytest.raises(HTTPException) as raised:
        session_service.require_learning_active(frozen)

    assert raised.value.detail["code"] == "INTERVENTION_REQUIRED"

    # Without an intervention, the refresh demand still stands.
    with pytest.raises(HTTPException) as refresh:
        session_service.require_learning_active(
            session.model_copy(update={"journey_recovery_required": True})
        )
    assert refresh.value.detail["code"] == "SESSION_STATE_REFRESH_REQUIRED"


def test_the_recovery_route_returns_a_retryable_503_not_a_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /session is the route the client is told to call to recover.

    Proving this at the HTTP boundary rather than at the function, because the
    defect was what the client received: an unhandled transport error became 500
    INTERNAL_ERROR on the one request that was supposed to get the student moving
    again, so the advice in the frontend handoff led nowhere.
    """

    from fastapi.testclient import TestClient

    from app.adapters.student_model import StudentModelServiceAdapter
    from app.main import app

    event = _guided_completed_event(
        paused_for_repair=True, repair_count=0, repair_cycle_no=1
    )
    session = _session(event)
    # The route validates the id format, unlike the direct function calls above.
    session_service._sessions.pop(session.session_id, None)
    session = session.model_copy(update={"session_id": f"SESSION{uuid4().hex}"})
    pending = session.model_copy(
        update={
            "pending_guided_progression": GuidedRepairCompletedEvent(
                request_id=f"{session.session_id}:TURN-1:GUIDED_REPAIR_COMPLETED",
                event_type="GUIDED_REPAIR_COMPLETED",
                source_turn_id="TURN-1",
                expected_journey_version=event.journey_state.version,
                topic_id=event.journey_state.topic_id,
                student_id=session.student_id,
                timestamp="2026-09-09T14:49:19Z",
                micro_skill_ids=[REPAIR_SKILL],
                repair_cycle_no=1,
            )
        }
    )
    session_service._sessions[session.session_id] = pending

    async def unreachable(
        adapter: StudentModelServiceAdapter, event: object, access_token: str
    ) -> object:
        del adapter, event, access_token
        raise RuntimeError("connection reset before the reply arrived")

    monkeypatch.setattr(
        StudentModelServiceAdapter, "send_session_event", unreachable
    )
    client = TestClient(app, headers={"Authorization": "Bearer test-token"})

    response = client.get(
        f"/session/{session.session_id}", params={"student_id": "ST010"}
    )

    assert response.status_code == 503, response.text
    assert response.json()["error_code"] == "PROGRESSION_RETRY_REQUIRED"
    # And the pending event is still there, so the retry is the same event.
    still_pending = session_service._sessions[session.session_id]
    assert still_pending.pending_guided_progression is not None
