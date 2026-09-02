"""The Review lifecycle: accept, materialize, replay, hand off.

Four distinct things used to be one indistinguishable outcome -- "the student
answered and the Review screen did not appear":

  * the answer was accepted and the review was still being built,
  * the answer was accepted and building it failed,
  * the response was lost in a restart and the retry re-did the whole turn,
  * the review was completed but nothing said which topic came next.

Each is now a separate, readable state, and this file is the seam test for all
four. Only the HTTP layer and review generation are faked.
"""

import base64
from io import BytesIO

import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app.adapters import provider, student_model
from app.adapters.student_model import StudentModelServiceAdapter
from app.core.config import Settings
from app.main import app
from app.models.adapters import AdapterContext, RAGResult, StudentModelResult, TutorResult
from app.models.session import SessionRecord
from app.models.student_model_session import (
    StudentModelSessionEvent,
    StudentModelSessionEventResponse,
)
from app.services import canvas_service, interaction_service, session_service
from app.services.session_store import restore_review_materialization_state
from tests.test_phase4_review_integration import _review
from tests.test_session_events import _session_opened_response

STUDENT = "ST950"
TURN_ID = "TURN-ST950-FINAL"
client = TestClient(app, headers={"Authorization": "Bearer this-students-own-token"})


def _png_data_url(colour: str = "white") -> str:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), colour).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def _history(topic_id: str, student_id: str) -> dict[str, object]:
    return {
        "topic_id": topic_id,
        "student_id": student_id,
        "topic_info": {
            "title": "Writing general rules",
            "concept": "A letter can stand for any starting number.",
            "learning_goals": ["Translate words into an expression."],
        },
        "attempts": [
            {
                "attempt_id": "ATTEMPT-950",
                "question_id": "Q-T01-005",
                "question_usage_id": "QU-T01-005-P3",
                "phase": "PHASE_3_INDEPENDENT_PRACTICE",
                "evaluation": "INCORRECT",
                "attempted_at": "2026-09-02T10:15:23Z",
                "question_text": "A temperature starts at t and falls by 3.",
                "canonical_answer": "t - 3",
                "answer_steps": ["Identify t.", "Subtract 3."],
                "detected_errors": [
                    {"error_code": "ERR-DIRECTION-REVERSED", "micro_skill_id": "T01.M3"}
                ],
            }
        ],
    }


def _review_completed_body(request_id: str, **routing: object) -> dict[str, object]:
    body = _session_opened_response("REVIEW")
    body["request_id"] = request_id
    body["phase_payload"] = None
    journey = body["journey_state"]
    assert isinstance(journey, dict)
    journey["topic_status"] = "COMPLETED"
    journey["mastery_status"] = "MASTERED"
    journey["recommended_entry_phase"] = None
    journey["review"] = {"status": "COMPLETED", "phase_visit_no": 1}
    routing_block = body["routing"]
    assert isinstance(routing_block, dict)
    routing_block.update(
        {
            "reason_code": "REVIEW_COMPLETED",
            "next_action": "START_NEXT_TOPIC",
            "next_topic_id": "ALG-ORI-03",
            "next_topic_entry_phase": "PHASE_0_DIAGNOSTIC",
            **routing,
        }
    )
    return body


class _Harness:
    """What the run actually did, counted rather than inferred."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.ocr_calls = 0
        self.tutor_calls = 0
        self.review_calls = 0
        self.generation_failures = 0
        self.review_completed_routing: dict[str, object] = {}
        # When False, an attempt keeps the journey in Independent Practice
        # instead of mastering the topic.
        self.attempt_masters_topic = True


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> _Harness:
    seen = _Harness()

    settings = Settings(
        student_model_url="https://student-model.test",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        student_model_jwt_secret="shared-with-student-model-at-least-32-bytes",
        use_mock_student_model=False,
        use_mock_voice=True,
        use_mock_vision=True,
        use_openai_ai_engine=False,
    )
    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)

    async def post_json(name, url, body, headers, timeout, retries):
        del name, headers, timeout, retries
        if url.endswith("/work-artifacts"):
            return {
                "artifact_id": "ART-950",
                "pdf_url": "/work-artifacts/ART-950/pdf",
                "page_count": body["page_count"],
            }
        if url.endswith("/topic/event-history"):
            return _history(body["topic_id"], body["student_id"])
        if url.endswith("/phase4-review"):
            return {"status": "ok"}
        raise AssertionError(f"unexpected Student Model call: {url}")

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        seen.events.append(event.event_type)
        if event.event_type == "REVIEW_COMPLETED":
            body = _review_completed_body(
                event.request_id, **seen.review_completed_routing
            )
        else:
            entered_review = (
                event.event_type != "SESSION_OPENED" and seen.attempt_masters_topic
            )
            body = _session_opened_response(
                "REVIEW" if entered_review else "PHASE_3_INDEPENDENT_PRACTICE"
            )
            body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    original_evidence = canvas_service.collect_canvas_evidence

    async def counted_evidence(*args, **kwargs):
        seen.ocr_calls += 1
        return await original_evidence(*args, **kwargs)

    async def correct_pipeline(
        context: AdapterContext,
    ) -> tuple[RAGResult, StudentModelResult, TutorResult]:
        del context
        seen.tutor_calls += 1
        student = StudentModelResult(
            mastery_status="MASTERED",
            continuity_status="on_track",
            recommended_entry_phase="REVIEW",
            hint_dependency_score=0.0,
            intervention_required=False,
        )
        tutor = TutorResult(
            evaluation="CORRECT",
            error_type="NONE",
            intent="SUBMITTING_ANSWER",
            response_strategy="CONFIRM_CORRECT",
            tutor_message="Correct.",
            tutor_message_voice="Correct.",
            voice_optimised=True,
            hint_level=0,
            answer_reveal_allowed=False,
            confidence=0.95,
            input_source="CANVAS",
            attempt_increment=1,
            recommended_conversation_action="ADVANCE_TO_NEXT_QUESTION",
            question_completed=True,
            answer_value_confirmed=True,
            reasoning_complete=True,
        )
        return RAGResult(documents=[], retrieval_confidence=0.0), student, tutor

    def generate(request):
        del request
        seen.review_calls += 1
        if seen.generation_failures > 0:
            seen.generation_failures -= 1
            raise ValueError("review generator is unavailable")
        return _review()

    monkeypatch.setattr(student_model, "post_json", post_json)
    monkeypatch.setattr(
        StudentModelServiceAdapter, "send_session_event", send_session_event
    )
    monkeypatch.setattr(canvas_service, "collect_canvas_evidence", counted_evidence)
    monkeypatch.setattr(interaction_service, "run_tutor_pipeline", correct_pipeline)
    monkeypatch.setattr(session_service, "generate_phase4_review", generate)
    return seen


def _start() -> str:
    start = client.post(
        "/session/start",
        json={
            "student_id": STUDENT,
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert start.status_code == 200, start.text
    return start.json()["session_id"]


def _submit_final(session_id: str, turn_id: str = TURN_ID, **overrides):
    body = {
        "session_id": session_id,
        "student_id": STUDENT,
        "turn_id": turn_id,
        "submission_role": "STANDALONE_ATTEMPT",
        "snapshot_data_url": _png_data_url(),
    }
    body.update(overrides)
    return client.post("/canvas/submit", json=body)


def _forget_process_caches(session_id: str) -> None:
    """Everything a restart takes with it, and nothing it does not.

    The session record survives (it is persisted); the response cache and the
    payload fingerprints do not. This is the exact state the 2 Sep restart left
    behind, minus the restart.
    """

    for key in list(session_service._last_interaction_responses):
        if key[0] == session_id:
            del session_service._last_interaction_responses[key]
    for key in list(session_service._interaction_payload_fingerprints):
        if key[0] == session_id:
            del session_service._interaction_payload_fingerprints[key]


def test_the_final_turn_is_accepted_into_review_with_a_materialization_state(
    harness: _Harness,
) -> None:
    """The happy path, stated as three separate facts rather than one.

    "The answer was accepted", "the journey moved to Review" and "the review is
    built" used to be inferred from a single null-or-not phase4_review, which is
    why a review that was merely still being built read as a failed turn.
    """

    session_id = _start()

    submit = _submit_final(session_id)

    assert submit.status_code == 200, submit.text
    body = submit.json()
    assert body["current_phase"] == "REVIEW"
    assert body["review_materialization_state"] == "READY"
    # Exactly one, and it is the mastery decision: a second would be a second
    # CORRECT_ATTEMPT counted against the same piece of evidence.
    assert harness.events.count("CORRECT_ATTEMPT") == 1
    stored = session_service._sessions[session_id]
    assert stored.review_materialization_state == "READY"
    assert stored.phase4_review is not None
    assert stored.final_turn_receipt is not None
    assert stored.final_turn_receipt.turn_id == TURN_ID
    assert stored.final_turn_receipt.phase == "REVIEW"


def test_a_failed_review_leaves_the_answer_accepted_and_pending(
    harness: _Harness,
) -> None:
    """The failure that used to look like a rejected answer.

    Phase 4 generation is down for both bounded attempts. The transition is
    already persisted, so the student stays in Review with the answer counted
    and nothing to re-answer -- and the read that exists to be retried is the
    only thing that moves.
    """

    session_id = _start()
    harness.generation_failures = 2

    submit = _submit_final(session_id)

    assert submit.status_code == 200, submit.text
    assert submit.json()["current_phase"] == "REVIEW"
    assert submit.json()["review_materialization_state"] == "PENDING"
    # Bounded: two attempts, not a loop against a service that is down.
    assert harness.review_calls == 2
    stored = session_service._sessions[session_id]
    assert stored.review_materialization_state == "PENDING"
    assert stored.phase4_review is None

    events_after_submit = list(harness.events)
    journey_version = stored.student_model_event.journey_state.version
    attempts = stored.independent_attempt_count

    read = client.get(f"/session/{session_id}", params={"student_id": STUDENT})

    assert read.status_code == 200, read.text
    assert read.json()["review_materialization_state"] == "READY"
    assert read.json()["phase4_review"] is not None
    # The retry is materialization only. Not one Student Model event, so the
    # journey version and the attempt count cannot have moved.
    assert harness.events == events_after_submit
    reread = session_service._sessions[session_id]
    assert reread.student_model_event.journey_state.version == journey_version
    assert reread.independent_attempt_count == attempts


def test_a_retry_after_a_restart_replays_the_receipt_instead_of_the_turn(
    harness: _Harness,
) -> None:
    """The response cache is process-local; last_processed_turn_id is not.

    A restart between losing the response and the client retrying left the
    backend certain it had processed the turn and unable to say what happened,
    so the retry paid for OCR, tutor evaluation and a second CORRECT_ATTEMPT.
    """

    session_id = _start()
    assert _submit_final(session_id).status_code == 200
    ocr_before = harness.ocr_calls
    tutor_before = harness.tutor_calls
    events_before = list(harness.events)
    _forget_process_caches(session_id)

    replay = _submit_final(session_id)

    assert replay.status_code == 200, replay.text
    assert replay.json()["status"] == "DUPLICATE_TURN"
    assert replay.json()["current_phase"] == "REVIEW"
    assert replay.json()["review_materialization_state"] == "READY"
    # None of the three expensive halves of a turn ran again.
    assert harness.ocr_calls == ocr_before
    assert harness.tutor_calls == tutor_before
    assert harness.events == events_before


def test_the_same_turn_with_different_evidence_is_still_a_conflict(
    harness: _Harness,
) -> None:
    """The receipt carries the fingerprint, so the 409 survives the restart too.

    Without it a restart turns "you already sent this turn with other work" into
    a silent second acceptance of whichever evidence arrived last.
    """

    session_id = _start()
    assert _submit_final(session_id).status_code == 200
    _forget_process_caches(session_id)

    changed = _submit_final(session_id, snapshot_data_url=_png_data_url("black"))

    assert changed.status_code == 409, changed.text


def test_review_completion_returns_the_handoff_and_ends_the_source_session(
    harness: _Harness,
) -> None:
    session_id = _start()
    assert _submit_final(session_id).status_code == 200

    completed = client.post(
        f"/session/{session_id}/review/complete",
        json={"student_id": STUDENT, "turn_id": "TURN-REVIEW-DONE"},
    )

    assert completed.status_code == 200, completed.text
    body = completed.json()
    handoff = body["next_topic_handoff"]
    assert handoff is not None
    assert handoff["topic_id"] == "ALG-ORI-03"
    assert handoff["entry_phase"] == "PHASE_0_DIAGNOSTIC"
    assert handoff["source_session_id"] == session_id
    # Atomically: the source session stops accepting turns exactly when the
    # handoff becomes durable.
    assert body["status"] == "ended"
    assert session_service._sessions[session_id].status == "ended"

    repeat = client.post(
        f"/session/{session_id}/review/complete",
        json={"student_id": STUDENT, "turn_id": "TURN-REVIEW-DONE"},
    )

    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["next_topic_handoff"] == handoff
    assert harness.events.count("REVIEW_COMPLETED") == 1


def test_a_start_next_topic_with_no_topic_is_refused_not_guessed(
    harness: _Harness,
) -> None:
    """The backend has the curriculum order in reach and must not use it.

    Filling the gap here is how two systems end up choosing different next
    topics for the same student.
    """

    session_id = _start()
    assert _submit_final(session_id).status_code == 200
    harness.review_completed_routing = {
        "next_topic_id": None,
        "next_topic_entry_phase": None,
    }

    completed = client.post(
        f"/session/{session_id}/review/complete",
        json={"student_id": STUDENT, "turn_id": "TURN-REVIEW-MALFORMED"},
    )

    assert completed.status_code == 503, completed.text
    assert completed.json()["error_code"] == "NEXT_TOPIC_HANDOFF_INVALID"
    assert session_service._sessions[session_id].status == "started"
    assert session_service._sessions[session_id].next_topic_handoff is None


def test_no_next_topic_completes_the_review_without_a_handoff(
    harness: _Harness,
) -> None:
    """End of the curriculum: no handoff, and still a completed session."""

    session_id = _start()
    assert _submit_final(session_id).status_code == 200
    harness.review_completed_routing = {
        "next_action": "NONE",
        "next_topic_id": None,
        "next_topic_entry_phase": None,
    }

    completed = client.post(
        f"/session/{session_id}/review/complete",
        json={"student_id": STUDENT, "turn_id": "TURN-REVIEW-LAST"},
    )

    assert completed.status_code == 200, completed.text
    assert completed.json()["next_topic_handoff"] is None
    assert completed.json()["status"] == "ended"


def test_the_public_session_carries_one_source_of_progression(
    harness: _Harness,
) -> None:
    """last_student_model is a legacy snapshot; two sources can only disagree."""

    session_id = _start()
    assert _submit_final(session_id).status_code == 200

    read = client.get(f"/session/{session_id}", params={"student_id": STUDENT})

    assert read.status_code == 200, read.text
    body = read.json()
    assert "last_student_model" not in body
    assert "final_turn_receipt" not in body
    assert body["student_model_state"]["current_phase"] == "REVIEW"


def test_a_review_session_stored_before_these_fields_existed_still_loads(
    harness: _Harness,
) -> None:
    """Cold start, the way session_store does it: dump, drop the keys, revalidate.

    A required field here would abort the boot on every session written before
    this deploy -- which is exactly how independent_attempts took 8001 down on
    2 Sep 2026.
    """

    harness.generation_failures = 2
    session_id = _start()
    assert _submit_final(session_id).status_code == 200

    stored = session_service._sessions[session_id].model_dump(mode="json")
    assert stored["current_phase"] == "REVIEW"
    # What a writer from before this deploy would have persisted.
    for field in (
        "review_materialization_state",
        "next_topic_handoff",
        "final_turn_receipt",
    ):
        del stored[field]

    pending = dict(stored)
    restore_review_materialization_state(pending)
    restored = SessionRecord.model_validate(pending)

    # Honest, not invented: Review with no review attached is still pending one.
    assert restored.review_materialization_state == "PENDING"
    assert restored.next_topic_handoff is None
    assert restored.final_turn_receipt is None

    # A stored Review that already has its review is READY, not built again.
    ready = {**stored, "phase4_review": _review().model_dump(mode="json")}
    restore_review_materialization_state(ready)
    assert SessionRecord.model_validate(ready).review_materialization_state == "READY"

    # A session that never reached Review is given no state at all -- claiming
    # one would claim a Review it never had.
    never = {**stored, "current_phase": "GUIDED_PRACTICE"}
    restore_review_materialization_state(never)
    assert "review_materialization_state" not in never


def test_a_correct_answer_that_is_not_the_last_one_stays_in_independent_practice(
    harness: _Harness,
) -> None:
    """Only a Student Model MASTERED outcome may enter Review.

    Verification step 2. A correct Phase 3 answer is evidence, not a verdict --
    if the backend could reach Review on its own the whole authority contract
    would be decorative.
    """

    harness.attempt_masters_topic = False
    session_id = _start()

    submit = _submit_final(session_id, turn_id="TURN-NOT-LAST")

    assert submit.status_code == 200, submit.text
    body = submit.json()
    assert body["current_phase"] == "INDEPENDENT_PRACTICE"
    assert body["review_materialization_state"] is None
    stored = session_service._sessions[session_id]
    assert stored.phase4_review is None
    # No receipt either: this turn is not the one whose replay is expensive.
    assert stored.final_turn_receipt is None


def test_a_later_turn_in_review_does_not_overwrite_the_final_turn_receipt(
    harness: _Harness,
) -> None:
    """The receipt is one slot, and Review is a screen the student sits on.

    Gating the write on "the session is in REVIEW" rather than "this turn
    entered REVIEW" let an inactivity nudge take the slot. The final answer's
    replay was then gone, so the retry it exists for fell through to a second
    CORRECT_ATTEMPT and the changed-evidence 409 quietly became a 200.
    """

    session_id = _start()
    assert _submit_final(session_id).status_code == 200
    stored = session_service._sessions[session_id]
    assert stored.final_turn_receipt is not None
    tutor_turn_id = stored.last_tutor_turn_id

    nudge = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": STUDENT,
            "interaction_type": "INACTIVITY_NUDGE",
            "input_source": "SYSTEM",
            "turn_id": "TURN-NUDGE-IN-REVIEW",
            "previous_tutor_turn_id": tutor_turn_id,
            "current_phase": "REVIEW",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": "Q-T01-005",
            "hint_count": 0,
            "idle_duration_ms": 60000,
        },
    )
    assert nudge.status_code in {200, 409, 422}, nudge.text

    # Whatever the nudge did, it did not take the final answer's receipt.
    receipt = session_service._sessions[session_id].final_turn_receipt
    assert receipt is not None
    assert receipt.turn_id == TURN_ID

    # And the replay it guards still works after a restart.
    _forget_process_caches(session_id)
    replay = _submit_final(session_id)
    assert replay.status_code == 200, replay.text
    assert replay.json()["status"] == "DUPLICATE_TURN"


def test_the_next_topic_starts_from_the_handoff_and_not_the_completed_one(
    harness: _Harness,
) -> None:
    """Verification step 7: the handoff is consumed verbatim.

    The caller passes the returned topic and entry phase through. Recomputing
    either -- or reopening the source topic because its session id is the one
    the browser still holds -- is the failure this whole contract exists to
    stop.
    """

    session_id = _start()
    assert _submit_final(session_id).status_code == 200
    completed = client.post(
        f"/session/{session_id}/review/complete",
        json={"student_id": STUDENT, "turn_id": "TURN-REVIEW-HANDOFF"},
    )
    assert completed.status_code == 200, completed.text
    handoff = completed.json()["next_topic_handoff"]
    harness.attempt_masters_topic = False

    started = client.post(
        "/session/start",
        json={
            "student_id": STUDENT,
            "topic_code": handoff["topic_id"],
            "interaction_mode": "TEXT",
        },
    )

    assert started.status_code == 200, started.text
    assert started.json()["session_id"] != session_id
    assert started.json()["status"] == "started"
    # The completed source session is untouched by starting the next topic.
    assert session_service._sessions[session_id].status == "ended"
