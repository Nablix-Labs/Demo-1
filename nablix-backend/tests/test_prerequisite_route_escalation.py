"""A checkpoint that exhausts both Guided repairs must not end the lesson.

The third failure on the same checkpoint uses up both Phase 2 repair cycles,
and Student Model escalates: reason_code MAX_GUIDED_REPAIRS_EXHAUSTED,
next_action CHECK_PREREQUISITE_REMEDIATION_ROUTE, no phase_payload, and a
journey parked at PAUSED_FOR_PREREQUISITE_LOOKUP. It is asking which
micro-skills sit beneath the one the student cannot clear; it cannot look that
up itself, and it will not move until it is told.

Nothing on this side answered. The session persisted with question_id null and
the practice screen went empty, which the student reads as "no more questions
left" -- how ST-018's run ended on 11 Sep 2026, and where ST-008 was heading.

The escalation itself was reached through a misgraded choice (see
test_ai_engine.py::test_choice_contract_reads_the_selected_option_the_ui_submits),
but a student can genuinely fail a checkpoint three times, and the route out
has to exist either way.
"""

import pytest
from copy import deepcopy
from fastapi.testclient import TestClient

from app.adapters.student_model import StudentModelServiceAdapter
from app.main import app
from app.models.adapters import AdapterContext, RAGResult, StudentModelResult, TutorResult
from app.models.student_model_session import (
    PrerequisiteRouteLookup,
    StudentModelSessionEvent,
    StudentModelSessionEventResponse,
)
from app.services import interaction_service, session_service
from tests.test_canvas import (
    VALID_SNAPSHOT_DATA_URL,
    _incorrect_independent_tutor,
    _start_session,
)
from tests.test_session_events import _event_response, _session_opened_response

client = TestClient(app, headers={"Authorization": "Bearer test-token"})
STUDENT = "ST018"
SKILL = "T01.M6"
CHECKPOINT = "Q-T01-010"

# The chain the curriculum lookup returns for T01.M6. Ordered by the repository,
# and echoed back to Student Model untouched.
PREREQUISITE_CHAIN = [
    {
        "micro_skill_id": "T01.M2",
        "lowest_topic_id": "ALG-KS3-01",
        "lowest_topic_sequence": 1,
        "active": True,
    }
]


def _exhausted_response(request_id: str) -> dict[str, object]:
    """The escalation envelope: a question for us, not a verdict."""

    response = deepcopy(_session_opened_response("PHASE_3_INDEPENDENT_PRACTICE"))
    response["request_id"] = request_id
    response["phase_payload"] = None
    journey = response["journey_state"]
    assert isinstance(journey, dict)
    journey["recommended_entry_phase"] = None
    journey["return_checkpoint"] = {
        "topic_id": journey["topic_id"],
        "micro_skill_id": SKILL,
        "phase_visit_no": 1,
        "question_position_no": 3,
        "checkpoint_question_id": CHECKPOINT,
        "phase": "PHASE_3_INDEPENDENT_PRACTICE",
        "resume_policy": "SAME_QUESTION_AT_CHECKPOINT",
    }
    routing = response["routing"]
    status = response["status"]
    assert isinstance(routing, dict)
    assert isinstance(status, dict)
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
    return response


def _remediation_response(request_id: str) -> dict[str, object]:
    """What Student Model sends once the resolved route reaches it."""

    response = deepcopy(_event_response("DIAGNOSTIC_COMPLETED", request_id))
    journey = response["journey_state"]
    routing = response["routing"]
    assert isinstance(journey, dict)
    assert isinstance(routing, dict)
    journey["recommended_entry_phase"] = "PHASE_1_ORIENTATION"
    routing.update(
        {
            "reason_code": "PREREQUISITE_REMEDIATION_REQUIRED",
            "reason": (
                f"Routing {SKILL}'s unresolved prerequisites to Phase 1 "
                "Orientation at Difficulty 1."
            ),
            "next_action": "START_PREREQUISITE_ORIENTATION",
            "return_question_id": CHECKPOINT,
        }
    )
    status = response["status"]
    assert isinstance(status, dict)
    status.update({"status_code": "PREREQUISITE_REMEDIATION_REQUIRED"})
    return response


@pytest.fixture
def exhausted_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> list[StudentModelSessionEvent]:
    """Independent Practice where the next answer exhausts the repair budget."""

    sent: list[StudentModelSessionEvent] = []

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        sent.append(event)
        if event.event_type == "INDEPENDENT_RETRY_COMPLETED":
            body = _exhausted_response(event.request_id)
        elif event.event_type == "PREREQUISITE_ROUTE_RESOLVED":
            body = _remediation_response(event.request_id)
        else:
            body = deepcopy(_session_opened_response("PHASE_3_INDEPENDENT_PRACTICE"))
            # The checkpoint is already a retry -- two repair cycles are spent,
            # which is what makes the next failure the exhausting one.
            body["journey_state"]["phase_3_independent_practice"][
                "retry_required_micro_skill_ids"
            ] = [SKILL]
            body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    async def fetch_prerequisite_route(
        adapter: StudentModelServiceAdapter,
        topic_id: str,
        micro_skill_id: str,
        request_id: str,
    ) -> PrerequisiteRouteLookup:
        del adapter, topic_id, micro_skill_id, request_id
        return PrerequisiteRouteLookup.model_validate(
            {"prerequisite_micro_skills": PREREQUISITE_CHAIN}
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


def test_an_exhausted_checkpoint_resolves_its_prerequisite_route(
    exhausted_checkpoint: list[StudentModelSessionEvent],
) -> None:
    session_id = _start_session(STUDENT)

    answered = _fail_the_checkpoint(session_id)
    assert answered.status_code == 200, answered.text

    resolved = [
        event
        for event in exhausted_checkpoint
        if event.event_type == "PREREQUISITE_ROUTE_RESOLVED"
    ]
    assert len(resolved) == 1, "the escalation must be answered exactly once"
    # Keyed by the skill Student Model parked, not the one we last saw served:
    # it indexes repair_state_by_skill directly and 409s on any other.
    assert resolved[0].source_micro_skill_id == SKILL
    assert [
        skill.micro_skill_id for skill in resolved[0].prerequisite_micro_skills
    ] == ["T01.M2"]


def test_the_student_is_not_left_on_an_empty_practice_screen(
    exhausted_checkpoint: list[StudentModelSessionEvent],
) -> None:
    session_id = _start_session(STUDENT)

    answered = _fail_the_checkpoint(session_id)
    assert answered.status_code == 200, answered.text

    # The whole point: the session moves on to the remediation Student Model
    # routed it to, rather than persisting in Independent Practice with nothing
    # to answer -- which is the state the UI renders as "no questions left".
    session = session_service._sessions[session_id]
    assert session.current_phase == "CONCEPT_ORIENTATION"
    assert session.student_model_event is not None
    assert (
        session.student_model_event.routing.reason_code
        == "PREREQUISITE_REMEDIATION_REQUIRED"
    )
