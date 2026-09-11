"""A checkpoint that exhausts both Guided repairs must not end the lesson.

The third failure on the same checkpoint uses up both Phase 2 repair cycles and
Student Model escalates (TC-29): reason_code MAX_GUIDED_REPAIRS_EXHAUSTED,
next_action CHECK_PREREQUISITE_REMEDIATION_ROUTE, no phase_payload, Phase 3
parked at PAUSED_FOR_PREREQUISITE_LOOKUP. It is asking which micro-skills sit
beneath the one the student cannot clear; it cannot look that up itself, and it
will not move until it is told.

Nothing on this side answered. The session persisted with question_id null and
the practice screen went empty, which the student reads as "no more questions
left" -- how ST-018's run ended on 11 Sep 2026, and where ST-008 was heading.

Every envelope here is built from the authoritative testcase payloads
(Nablix_Phase3_TC_Changes_and_New_TC26_Onward_v3.docx), NOT from a convenient
existing fixture. An earlier version of this file built the resolved-route
response out of a DIAGNOSTIC_COMPLETED fixture, which carries an orientation
delivery_sequence that Student Model never sends for a remediation route; the
tests passed against a shape production does not produce and hid two 503s.
"""

import pytest
from copy import deepcopy

from app.adapters.student_model import StudentModelServiceAdapter
from app.models.adapters import AdapterContext, RAGResult, StudentModelResult, TutorResult
from app.models.student_model_session import (
    PrerequisiteRouteLookup,
    StudentModelSessionEvent,
    StudentModelSessionEventResponse,
)
from app.services import interaction_service, session_service
from tests.test_canvas import (
    VALID_SNAPSHOT_DATA_URL,
    client,
    _incorrect_independent_tutor,
    _start_session,
)
from tests.test_session_events import _session_opened_response

STUDENT = "ST018"
# The fixture topic's own skill and checkpoint. A retry event names a skill the
# question actually tests -- Student Model rejects it otherwise -- so these
# track the Phase 3 fixture rather than ST-018's real ids.
SKILL = "T02.M1"
CHECKPOINT = "Q-T02-004"

# TC-30's answer for a skill that has a route. Echoed back to Student Model
# untouched -- it groups these into the remediation plan itself.
PREREQUISITE_CHAIN = [
    {
        "micro_skill_id": "T01.M3",
        "lowest_topic_id": "ALG-KS3-01",
        "lowest_topic_sequence": 1,
        "active": True,
    }
]


def _independent_practice_response(request_id: str) -> dict[str, object]:
    """Phase 3 mid-topic, with this checkpoint already under retry.

    The persisted return_checkpoint matters: production always has one here
    (Student Model records it on the first checkpoint failure), and the guard in
    _apply_schema_event compares against it. A fixture without one silently
    skips that guard.
    """

    body = deepcopy(_session_opened_response("PHASE_3_INDEPENDENT_PRACTICE"))
    body["request_id"] = request_id
    journey = body["journey_state"]
    assert isinstance(journey, dict)
    journey["phase_3_independent_practice"]["retry_required_micro_skill_ids"] = [SKILL]
    journey["return_checkpoint"] = {
        "topic_id": journey["topic_id"],
        "micro_skill_id": SKILL,
        "phase_visit_no": 1,
        "question_position_no": 3,
        "checkpoint_question_id": CHECKPOINT,
    }
    return body


def _tc29_escalation(request_id: str) -> dict[str, object]:
    """TC-29: both repair cycles spent. A question for us, not a verdict."""

    body = _independent_practice_response(request_id)
    body["phase_payload"] = None
    journey = body["journey_state"]
    routing = body["routing"]
    status = body["status"]
    assert isinstance(journey, dict) and isinstance(routing, dict) and isinstance(status, dict)
    journey["recommended_entry_phase"] = None
    journey["continuity_status"] = "REMEDIATION_REQUIRED"
    journey["mastery_status"] = "LEARNING_GAP"
    phase3 = journey["phase_3_independent_practice"]
    phase3["status"] = "PAUSED_FOR_PREREQUISITE_LOOKUP"
    phase3["repair_state_by_skill"] = {
        SKILL: {
            "status": "PREREQUISITE_LOOKUP_REQUIRED",
            "phase_2_repair_count": 2,
            "fresh_retry_question_id": CHECKPOINT,
        }
    }
    routing.update(
        {
            "reason_code": "MAX_GUIDED_REPAIRS_EXHAUSTED",
            "reason": (
                f"The maximum of 2 Phase 2 repair cycles is used for {SKILL}. "
                "Checking the prerequisite remediation route."
            ),
            "next_action": "CHECK_PREREQUISITE_REMEDIATION_ROUTE",
            "prerequisite_check_required": True,
            "content_gap_detected": False,
            "return_topic_id": journey["topic_id"],
            "return_question_id": CHECKPOINT,
        }
    )
    status.update({"status_code": "PREREQUISITE_LOOKUP_REQUIRED"})
    return body


def _tc31_route_applied(request_id: str) -> dict[str, object]:
    """TC-31: a route exists. Note the orientation_bundle's real shape.

    Student Model sends {topic_id, target_micro_skill_ids, difficulty,
    remediation_reason} here -- no delivery_sequence, which is what the
    orientation bundles everywhere else in the schema carry.
    """

    body = _independent_practice_response(request_id)
    journey = body["journey_state"]
    routing = body["routing"]
    status = body["status"]
    assert isinstance(journey, dict) and isinstance(routing, dict) and isinstance(status, dict)
    # apply_prerequisite_route_resolved POPS the checkpoint onto the
    # remediation plan's return_target, so the resolved response carries none.
    journey["return_checkpoint"] = None
    journey["recommended_entry_phase"] = "PHASE_1_ORIENTATION"
    body["phase_payload"] = {
        "phase": "PHASE_1_ORIENTATION",
        "payload_type": "PREREQUISITE_REMEDIATION",
        "question_set": None,
        "orientation_bundle": {
            "topic_id": "ALG-KS3-01",
            "target_micro_skill_ids": ["T01.M3"],
            "difficulty": 1,
            "remediation_reason": "PREREQUISITE_GAP",
        },
    }
    routing.update(
        {
            "reason_code": "PREREQUISITE_REMEDIATION_REQUIRED",
            "reason": (
                f"Routing {SKILL}'s unresolved prerequisites to Phase 1 "
                "Orientation at Difficulty 1."
            ),
            "next_action": "START_PREREQUISITE_ORIENTATION",
            "next_topic_id": "ALG-KS3-01",
            "return_topic_id": journey["topic_id"],
            "return_question_id": CHECKPOINT,
            "prerequisite_check_required": False,
        }
    )
    status.update({"status_code": "PREREQUISITE_REMEDIATION_REQUIRED"})
    return body


def _tc34_no_route(request_id: str) -> dict[str, object]:
    """TC-34: the chain came back empty, so automated remediation stops."""

    body = _independent_practice_response(request_id)
    journey = body["journey_state"]
    routing = body["routing"]
    status = body["status"]
    assert isinstance(journey, dict) and isinstance(routing, dict) and isinstance(status, dict)
    journey["return_checkpoint"] = None
    journey["continuity_status"] = "INTERVENTION_REQUIRED"
    journey["recommended_entry_phase"] = None
    journey["intervention"] = {
        "intervention_id": "INT-T02-002",
        "scope": "TOPIC",
        "topic_id": journey["topic_id"],
        "trigger_micro_skill_ids": [SKILL],
        "reason_code": "NO_PREREQUISITE_ROUTE_AVAILABLE",
        "student_input_status": "REQUIRED",
    }
    body["phase_payload"] = {
        "phase": "PHASE_3_INDEPENDENT_PRACTICE",
        "payload_type": "INTERVENTION_INPUT_REQUIRED",
        "question_set": None,
        "intervention_input_request": {
            "intervention_id": "INT-T02-002",
            "prompt": "What are you finding difficult?",
            "selection_required": True,
            "voice_input_enabled": True,
            "voice_input_required": False,
        },
    }
    routing.update(
        {
            "reason_code": "NO_PREREQUISITE_ROUTE_AVAILABLE",
            "reason": (
                "No valid prerequisite micro-skill / earlier topic route is "
                "available. Automated remediation stops for this topic."
            ),
            "next_action": "COLLECT_INTERVENTION_INPUT",
            "prerequisite_check_required": False,
        }
    )
    status.update(
        {"status_code": "INTERVENTION_REQUIRED", "intervention_required": True}
    )
    return body


def _exhausted_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    chain: list[dict[str, object]],
    resolved: object,
) -> list[StudentModelSessionEvent]:
    """Drive a checkpoint into TC-29 and answer the lookup with `chain`."""

    sent: list[StudentModelSessionEvent] = []

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        sent.append(event)
        if event.event_type == "INDEPENDENT_RETRY_COMPLETED":
            body = _tc29_escalation(event.request_id)
        elif event.event_type == "PREREQUISITE_ROUTE_RESOLVED":
            body = resolved(event.request_id)
        else:
            body = _independent_practice_response(event.request_id)
        return StudentModelSessionEventResponse.model_validate(body)

    async def fetch_prerequisite_route(
        adapter: StudentModelServiceAdapter,
        topic_id: str,
        micro_skill_id: str,
        request_id: str,
    ) -> PrerequisiteRouteLookup:
        del adapter, topic_id, micro_skill_id, request_id
        return PrerequisiteRouteLookup.model_validate(
            {"prerequisite_micro_skills": chain}
        )

    async def incorrect_pipeline(
        context: AdapterContext,
    ) -> tuple[RAGResult, StudentModelResult, TutorResult]:
        del context
        return (
            RAGResult(documents=[], retrieval_confidence=0.0),
            StudentModelResult(
                mastery_status="LEARNING_GAP",
                continuity_status="on_track",
                recommended_entry_phase="GUIDED_PRACTICE",
                hint_dependency_score=0.0,
                intervention_required=True,
            ),
            _incorrect_independent_tutor(),
        )

    monkeypatch.setattr(
        StudentModelServiceAdapter, "send_session_event", send_session_event
    )
    monkeypatch.setattr(
        StudentModelServiceAdapter,
        "fetch_prerequisite_route",
        fetch_prerequisite_route,
    )
    monkeypatch.setattr(interaction_service, "run_tutor_pipeline", incorrect_pipeline)
    return sent


def _fail_the_checkpoint(session_id: str) -> object:
    return client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": STUDENT,
            "turn_id": "TURN-ST018-EXHAUSTED",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
        },
    )


def test_the_escalation_is_answered_with_the_resolved_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _exhausted_checkpoint(monkeypatch, PREREQUISITE_CHAIN, _tc31_route_applied)
    session_id = _start_session(STUDENT)

    answered = _fail_the_checkpoint(session_id)
    assert answered.status_code == 200, answered.text

    resolved = [e for e in sent if e.event_type == "PREREQUISITE_ROUTE_RESOLVED"]
    assert len(resolved) == 1, "the escalation must be answered exactly once"
    # Keyed by the skill Student Model parked, not whichever one was last
    # served: it indexes repair_state_by_skill directly and 409s on any other.
    assert resolved[0].source_micro_skill_id == SKILL
    assert resolved[0].source_topic_id == resolved[0].topic_id
    assert [s.micro_skill_id for s in resolved[0].prerequisite_micro_skills] == ["T01.M3"]


def test_a_resolved_route_pauses_the_topic_with_the_work_saved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TC-31 arrives and is persisted as a pause, not as a dead screen.

    The route itself (TC-32: run the earlier topic, return to this checkpoint)
    is not built, so the student is stopped with an explanation rather than sent
    into a journey that cannot finish. What must NOT happen is the old
    behaviour: a session left in Independent Practice with no question and no
    message.
    """

    _exhausted_checkpoint(monkeypatch, PREREQUISITE_CHAIN, _tc31_route_applied)
    session_id = _start_session(STUDENT)

    answered = _fail_the_checkpoint(session_id)
    assert answered.status_code == 200, answered.text

    session = session_service._sessions[session_id]
    assert session.question_id is None
    assert session.message == session_service.PREREQUISITE_REMEDIATION_MESSAGE
    # The frontend gates its paused panel on exactly this pair.
    assert session.student_model_event is not None
    assert (
        session.student_model_event.routing.reason_code
        == "PREREQUISITE_REMEDIATION_REQUIRED"
    )
    assert session.allow_text_input is False
    assert session.allow_voice_input is False


def test_an_empty_route_still_reports_back_and_raises_the_intervention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TC-34/TC-35: an empty chain is an answer, not a failure to look.

    Student Model cannot tell EARLIEST_TOPIC_NO_BACKWARD_ROUTE from
    NO_PREREQUISITE_ROUTE_AVAILABLE unless the empty result is reported, so
    skipping the event on an empty chain would strand the topic silently.
    """

    sent = _exhausted_checkpoint(monkeypatch, [], _tc34_no_route)
    session_id = _start_session(STUDENT)

    answered = _fail_the_checkpoint(session_id)
    assert answered.status_code == 200, answered.text

    resolved = [e for e in sent if e.event_type == "PREREQUISITE_ROUTE_RESOLVED"]
    assert len(resolved) == 1, "an empty chain must still be reported"
    assert resolved[0].prerequisite_micro_skills == []

    session = session_service._sessions[session_id]
    assert session.intervention is not None
    assert session.intervention.reason_code == "NO_PREREQUISITE_ROUTE_AVAILABLE"
