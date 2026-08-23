"""Canvas submit -> Review transition -> phase4_review survives -> PDF proxy.

The one test that crosses every boundary this feature has. Each half of this
chain already had unit coverage and every unit passed while the feature was
dead end to end, because the two seams that were broken -- the credential
Nablix presents to Student Model's internal-only endpoints, and the shape of
`whole_topic_evidence` on a student's first pass through a topic -- exist only
BETWEEN the units.

Only the HTTP layer is faked (`post_json` / `get_bytes`) and the review
generation itself. Auth headers, the submission_id -> artifact correlation and
the PDF proxy route are the real ones.
"""

import base64
from io import BytesIO

import jwt
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app.adapters import provider, student_model
from app.adapters.student_model import StudentModelServiceAdapter
from app.core.config import Settings
from app.main import app
from app.models.adapters import AdapterContext, RAGResult, StudentModelResult, TutorResult
from app.models.phase4_review import (
    FirstError,
    Phase4ReviewResponse,
    StudentInsights,
    TutorReplay,
    TutorReplayStep,
)
from app.models.student_model_session import (
    StudentModelSessionEvent,
    StudentModelSessionEventResponse,
)
from app.services import interaction_service, session_service
from tests.test_session_events import _session_opened_response

JWT_SECRET = "shared-with-student-model-at-least-32-bytes"
STUDENT_TOKEN = "this-students-own-token"
TURN_ID = "TURN-ST900-CANVAS-1"
ARTIFACT_ID = "ART-900"
PDF_BYTES = b"%PDF-1.4 the student's own working"

client = TestClient(app, headers={"Authorization": f"Bearer {STUDENT_TOKEN}"})


def _png_data_url() -> str:
    """A decodable PNG -- PDF assembly actually renders these."""

    buffer = BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def _role_of(headers: dict[str, str]) -> str:
    scheme, _, token = headers["Authorization"].partition(" ")
    assert scheme == "Bearer"
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])["role"]


def _review() -> Phase4ReviewResponse:
    return Phase4ReviewResponse(
        tutor_replays=[
            TutorReplay(
                review_item_id="REV-001",
                question_id="Q-T01-005",
                attempt_id="ATTEMPT-900",
                artifact_id=ARTIFACT_ID,
                first_error=FirstError(summary="Falls by 3 was treated as adding."),
                replay_steps=[
                    TutorReplayStep(
                        sequence_no=1,
                        narration="You started with t, which is right.",
                        tutor_write="t",
                    )
                ],
            )
        ],
        student_insights=StudentInsights(
            strength_summary="You chose the right starting value.",
            development_summary="Check whether the amount goes up or down.",
            next_practice_focus="Decide the direction before writing the rule.",
            personalised_notes=[
                "A letter can stand for any starting number.",
                "Falls means subtract.",
                "Read the direction word before choosing the operation.",
            ],
        ),
    )


@pytest.fixture
def student_model_service(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """A Student Model that enforces the same role rules the real one does."""

    seen: dict[str, object] = {"roles": {}, "artifact_submission_id": None}

    settings = Settings(
        student_model_url="https://student-model.test",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        student_model_jwt_secret=JWT_SECRET,
        use_mock_student_model=False,
        use_mock_voice=True,
        use_mock_vision=True,
        use_openai_ai_engine=False,
    )
    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)

    async def post_json(name, url, body, headers, timeout, retries):
        if url.endswith("/work-artifacts"):
            # Accepts a student's own token, and does here too.
            seen["artifact_submission_id"] = body["submission_id"]
            return {
                "artifact_id": ARTIFACT_ID,
                "pdf_url": f"/work-artifacts/{ARTIFACT_ID}/pdf",
                "page_count": body["page_count"],
            }
        if url.endswith("/topic/event-history"):
            seen["roles"]["event-history"] = _role_of(headers)
            return {
                "topic_id": body["topic_id"],
                "student_id": body["student_id"],
                "topic_info": {
                    "title": "Writing general rules",
                    "concept": "A letter can stand for any starting number.",
                    "learning_goals": ["Translate words into an expression."],
                },
                # Null, not absent: what the service sends for a student with no
                # topic learning summary row yet, i.e. a first pass.
                "whole_topic_evidence": {
                    "strong_micro_skill_ids": None,
                    "developing_micro_skill_ids": None,
                    "root_gap_micro_skill_ids": None,
                    "error_cluster_counts": None,
                    "misconception_recurrence_counts": None,
                    "phase_2_repair_required": False,
                },
                "attempts": [
                    {
                        "attempt_id": "ATTEMPT-900",
                        "question_id": "Q-T01-005",
                        "question_usage_id": "QU-T01-005-P3",
                        "phase": "PHASE_3_INDEPENDENT_PRACTICE",
                        "evaluation": "INCORRECT",
                        "attempted_at": "2026-08-21T10:15:23Z",
                        "question_text": "A temperature starts at t and falls by 3.",
                        "canonical_answer": "t - 3",
                        "answer_steps": ["Identify t.", "Subtract 3."],
                        "detected_errors": [
                            {
                                "error_code": "ERR-DIRECTION-REVERSED",
                                "micro_skill_id": "T01.M3",
                            }
                        ],
                        # Correlated by submission_id, exactly as the service
                        # keys it against the attempt's source_turn_id.
                        "work_artifact": {
                            "artifact_id": ARTIFACT_ID,
                            "pdf_url": f"/work-artifacts/{ARTIFACT_ID}/pdf",
                            "page_count": 1,
                        },
                    }
                ],
            }
        if url.endswith("/phase4-review"):
            seen["roles"]["phase4-review"] = _role_of(headers)
            return {"status": "ok"}
        raise AssertionError(f"unexpected Student Model call: {url}")

    async def get_bytes(name, url, headers, timeout, retries):
        seen["pdf_url"] = url
        seen["pdf_headers"] = headers
        return PDF_BYTES, "application/pdf"

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        body = (
            _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
            if event.event_type == "SESSION_OPENED"
            else _session_opened_response("REVIEW")
        )
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    async def wrong_pipeline(
        context: AdapterContext,
    ) -> tuple[RAGResult, StudentModelResult, TutorResult]:
        del context
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

    monkeypatch.setattr(student_model, "post_json", post_json)
    monkeypatch.setattr(student_model, "get_bytes", get_bytes)
    monkeypatch.setattr(
        StudentModelServiceAdapter, "send_session_event", send_session_event
    )
    monkeypatch.setattr(interaction_service, "run_tutor_pipeline", wrong_pipeline)
    monkeypatch.setattr(
        session_service, "generate_phase4_review", lambda request: _review()
    )
    return seen


def test_canvas_submit_to_rendered_pdf(student_model_service: dict[str, object]) -> None:
    seen = student_model_service

    start = client.post(
        "/session/start",
        json={
            "student_id": "ST900",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert start.status_code == 200, start.text
    session_id = start.json()["session_id"]

    submit = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST900",
            "turn_id": TURN_ID,
            "submission_role": "STANDALONE_ATTEMPT",
            "snapshot_data_url": _png_data_url(),
        },
    )
    assert submit.status_code == 200, submit.text
    assert submit.json()["current_phase"] == "REVIEW"

    # The artifact is stored under the turn id, which is what the history is
    # keyed on downstream -- a mismatch here silently drops the replay.
    assert seen["artifact_submission_id"] == TURN_ID

    # The two orchestration endpoints are internal_service-only. Forwarding the
    # student's own bearer is a 403 that degrades to a missing review.
    assert seen["roles"] == {
        "event-history": "internal_service",
        "phase4-review": "internal_service",
    }

    # Survives onto the session record, and out through /session/end -- the only
    # response the Review screen reads it from.
    ended = client.post(
        "/session/end",
        json={"session_id": session_id, "student_id": "ST900"},
    )
    assert ended.status_code == 200, ended.text
    review = ended.json()["phase4_review"]
    assert review is not None, "phase4_review did not survive to /session/end"
    replay = review["tutor_replays"][0]
    assert replay["question_text"] == "A temperature starts at t and falls by 3."
    pdf_url = replay["work_artifact"]["pdf_url"]
    assert pdf_url == f"/work-artifacts/{ARTIFACT_ID}/pdf"
    assert review["topic_outcome"] is not None
    assert review["topic_outcome"]["mastery_status"]
    assert review["topic_outcome"]["recommended_next_action"]
    assert review["question_journey"] is not None
    assert review["question_journey"][0]["question_id"] == "Q-T01-005"
    assert review["question_journey"][0]["evaluation"] == "INCORRECT"

    pdf = client.get(pdf_url)

    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content == PDF_BYTES
    assert seen["pdf_url"] == f"https://student-model.test{pdf_url}"
    # Ownership on this read is per-student, so the proxy must forward the
    # caller's bearer here and NOT the service token used above.
    assert seen["pdf_headers"] == {"Authorization": f"Bearer {STUDENT_TOKEN}"}
