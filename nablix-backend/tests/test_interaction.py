import asyncio

from fastapi.testclient import TestClient

from app.adapters.rag_service import MockRAGServiceAdapter
from app.models.adapters import (
    AdapterContext,
    CanvasFeedback,
    RAGResult,
    RetrievedDocument,
    SafetyCheckResult,
    StudentModelEvent,
    StudentModelResult,
    TutorResult,
    VisualCue,
)
from app.main import app
from app.services import interaction_service

client = TestClient(app)


def _start_session(student_id: str, mode: str = "TEXT", **overrides) -> str:
    body = {
        "student_id": student_id,
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "interaction_mode": mode,
    }
    body.update(overrides)
    response = client.post("/session/start", json=body)
    assert response.status_code == 200
    return response.json()["session_id"]


def _interaction_body(session_id: str, student_id: str, **overrides) -> dict:
    body = {
        "session_id": session_id,
        "student_id": student_id,
        "interaction_type": "ANSWER_SUBMISSION",
        "input_source": "TEXT",
        "text_input": "Is 7 + 5 = 13?",
        "current_phase": "GUIDED_PRACTICE",
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "question_id": "ALG_EQ_DIAG_001",
        "hint_count": 0,
    }
    body.update(overrides)
    return body


def test_interaction_returns_session_view() -> None:
    session_id = _start_session("ST001")

    response = client.post("/interaction", json=_interaction_body(session_id, "ST001"))

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["student_id"] == "ST001"
    assert body["message"] == "Let us review the equation and try the next step carefully."
    assert body["message_voice"] == "Let us review the equation and try the next step carefully."
    assert body["current_phase"] == "GUIDED_PRACTICE"
    assert body["voice_state"] == {
        "stream_active": False,
        "current_turn": "STUDENT",
        "last_transcript_confidence": None,
        "fallback_active": False,
    }
    assert body["canvas_state"]["canvas_active"] is True
    assert body["ui_state"] == "GUIDED_PRACTICE"
    assert body["phase_indicator"] == "GUIDED_PRACTICE"
    assert body["interaction_mode"] == "TEXT"
    assert body["show_canvas"] is True
    assert body["show_hint_button"] is True
    assert body["show_visual_cue"] is False
    assert body["visual_cue"] is None
    assert body["show_scaffold_panel"] is False
    assert body["scaffold_steps"] == []
    assert body["allow_text_input"] is True
    assert body["allow_voice_input"] is True
    assert body["current_question"]
    assert body["hint_count"] == 0
    assert body["session_summary"] is None


def test_interaction_returns_visual_cue_for_addition_opposite_operation_error() -> None:
    session_id = _start_session("ST001")

    response = client.post(
        "/interaction",
        json=_interaction_body(session_id, "ST001", text_input="x = 13"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["show_visual_cue"] is True
    assert body["visual_cue"]["show"] is True
    assert body["visual_cue"]["cue_type"] == "EQUATION_BLOCK"


def test_interaction_rejects_malformed_session_id() -> None:
    response = client.post("/interaction", json=_interaction_body("bad", "ST001"))

    assert response.status_code == 422
    assert response.json()["field"] == "session_id"


def test_interaction_returns_404_for_unknown_session() -> None:
    response = client.post("/interaction", json=_interaction_body("SESSION777", "ST404"))

    assert response.status_code == 404


def test_interaction_voice_updates_transcript_confidence() -> None:
    session_id = _start_session("ST002", mode="VOICE")

    response = client.post(
        "/interaction",
        json=_interaction_body(
            session_id,
            "ST002",
            input_source="VOICE",
            text_input=None,
            voice_transcript="I think x equals 5",
            transcript_confidence=0.78,
        ),
    )

    assert response.status_code == 200
    assert response.json()["voice_state"]["last_transcript_confidence"] == 0.78


def test_interaction_voice_normalizes_spoken_correct_answer() -> None:
    session_id = _start_session("ST014", mode="VOICE")

    response = client.post(
        "/interaction",
        json=_interaction_body(
            session_id,
            "ST014",
            input_source="VOICE",
            text_input=None,
            voice_transcript="x is equal to 5",
            transcript_confidence=0.88,
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Correct. Nice work explaining your answer."
    assert body["message_voice"] == "Correct. Nice work explaining your answer."


def test_interaction_voice_accepts_answer_intro_phrases() -> None:
    cases = [
        "I think the answer is five",
        "It might be five",
    ]

    for index, transcript in enumerate(cases, start=15):
        session_id = _start_session(f"ST{index:03d}", mode="VOICE")

        response = client.post(
            "/interaction",
            json=_interaction_body(
                session_id,
                f"ST{index:03d}",
                input_source="VOICE",
                text_input=None,
                voice_transcript=transcript,
                transcript_confidence=0.88,
            ),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["message"] == "Correct. Nice work explaining your answer."
        assert body["message_voice"] == "Correct. Nice work explaining your answer."


def test_interaction_safety_failure_short_circuits_pipeline() -> None:
    session_id = _start_session("ST003")

    response = client.post(
        "/interaction",
        json=_interaction_body(session_id, "ST003", text_input="SAFETY_BLOCK"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Let's pause for a moment and come back to the maths when you're ready."
    assert body["show_visual_cue"] is False
    assert body["scaffold_steps"] == []


class _FakeRAGAdapter:
    async def retrieve(self, context: AdapterContext) -> RAGResult:
        return RAGResult(
            documents=[RetrievedDocument(title="Mock", content="Mock content", source="mock")],
            retrieval_confidence=0.9,
        )


class _FakeStudentModelAdapter:
    def __init__(self, recommended_entry_phase: str | None = None) -> None:
        self.events: list[StudentModelEvent] = []
        self.recommended_entry_phase = recommended_entry_phase

    async def assess(self, context: AdapterContext) -> StudentModelResult:
        return StudentModelResult(
            student_state="READY",
            confidence=0.9,
            mastery_level="DEVELOPING",
            recommended_support="LOW_HINT",
            recommended_entry_phase=self.recommended_entry_phase,
        )

    async def update_from_event(self, event: StudentModelEvent) -> StudentModelResult:
        self.events.append(event)
        return StudentModelResult(
            student_state="READY",
            confidence=0.9,
            mastery_level="DEVELOPING",
            recommended_support="LOW_HINT",
        )


class _FakeTutorAdapter:
    def __init__(self, next_phase_recommendation: str | None = "GUIDED_PRACTICE") -> None:
        self.next_phase_recommendation = next_phase_recommendation

    async def evaluate(
        self,
        context: AdapterContext,
        rag: RAGResult,
        student: StudentModelResult,
    ) -> TutorResult:
        return TutorResult(
            evaluation="PARTIALLY_CORRECT",
            error_type="ARITHMETIC_ERROR",
            intent="SUBMITTING_ANSWER",
            response_strategy="SCAFFOLD",
            tutor_message="Your setup is right. Check the final division.",
            tutor_message_voice="Your setup is right. Check the final division.",
            voice_optimised=True,
            hint_level=1,
            scaffold_steps_delivered=["Divide both sides by 2."],
            visual_cue=VisualCue(show=True, cue_type="EQUATION_BALANCE", description="Show both sides."),
            canvas_feedback=CanvasFeedback(),
            next_phase_recommendation=self.next_phase_recommendation,
            answer_reveal_allowed=False,
            confidence=0.91,
            input_source="TEXT",
            transcript_confidence=None,
            safety_check=SafetyCheckResult(passed=True),
            student_model_events=[
                StudentModelEvent(
                    event_type="PARTIAL_ATTEMPT",
                    evaluation="PARTIALLY_CORRECT",
                    error_type="ARITHMETIC_ERROR",
                    hint_level_used=0,
                    independent_success=False,
                )
            ],
        )


class _FakeSafetyAdapter:
    async def check(self, context: AdapterContext) -> SafetyCheckResult:
        return SafetyCheckResult(passed=True)


class _FakeAdapters:
    def __init__(
        self,
        student_model: _FakeStudentModelAdapter,
        tutor: _FakeTutorAdapter | None = None,
    ) -> None:
        self.rag = _FakeRAGAdapter()
        self.student_model = student_model
        self.tutor = tutor if tutor is not None else _FakeTutorAdapter()
        self.safety = _FakeSafetyAdapter()


def _fake_pipeline(
    monkeypatch,
    student_phase: str | None = None,
    tutor_phase: str | None = None,
) -> _FakeStudentModelAdapter:
    """Patch the adapter bundle so Tamil/tutor phase recommendations are controlled."""

    student_model = _FakeStudentModelAdapter(recommended_entry_phase=student_phase)
    adapters = _FakeAdapters(
        student_model, _FakeTutorAdapter(next_phase_recommendation=tutor_phase)
    )
    monkeypatch.setattr(interaction_service, "get_adapters", lambda: adapters)
    return student_model


def test_interaction_updates_phase_visual_scaffold_and_student_model_events(monkeypatch) -> None:
    # Tamil is silent, so the tutor-fallback recommendation (GUIDED_PRACTICE)
    # drives a valid DIAGNOSTIC -> GUIDED_PRACTICE transition; the tutor's
    # per-turn cue/scaffold outputs must survive the transition UI flags.
    session_id = _start_session("ST004")
    student_model = _fake_pipeline(monkeypatch, tutor_phase="GUIDED_PRACTICE")

    response = client.post("/interaction", json=_interaction_body(session_id, "ST004"))

    assert response.status_code == 200
    body = response.json()
    assert body["phase_changed"] is True
    assert body["current_phase"] == "GUIDED_PRACTICE"
    assert body["ui_state"] == "GUIDED_PRACTICE"
    assert body["show_visual_cue"] is True
    assert body["visual_cue"]["cue_type"] == "EQUATION_BALANCE"
    assert body["show_scaffold_panel"] is True
    assert body["scaffold_steps"] == ["Divide both sides by 2."]
    assert len(student_model.events) == 1
    assert student_model.events[0].event_type == "PARTIAL_ATTEMPT"


def test_transition_normal_advance(monkeypatch) -> None:
    # Spec case: Tamil recommends a valid next phase -> full transition response.
    session_id = _start_session("ST020")
    _fake_pipeline(monkeypatch, student_phase="GUIDED_PRACTICE")

    response = client.post("/interaction", json=_interaction_body(session_id, "ST020"))

    assert response.status_code == 200
    body = response.json()
    assert body["phase_changed"] is True
    assert body["previous_phase"] == "DIAGNOSTIC"
    assert body["current_phase"] == "GUIDED_PRACTICE"
    assert body["phase_transition_message"] == (
        "You are solid on the basics. Let us go straight into some practice problems."
    )
    assert body["phase_transition_voice"] == body["phase_transition_message"]
    assert body["question_id"] == "ALG_EQ_GP_001"
    assert body["current_question"] == "Solve for x: x + 6 = 10"
    assert body["show_hint_button"] is True
    assert body["attempt_count"] == 0


def test_transition_not_fired_when_phase_matches(monkeypatch) -> None:
    # Spec cases "no transition" and "first session start": recommending the
    # phase the session is already in changes nothing.
    session_id = _start_session("ST021")
    _fake_pipeline(monkeypatch, student_phase="DIAGNOSTIC")

    response = client.post("/interaction", json=_interaction_body(session_id, "ST021"))

    assert response.status_code == 200
    body = response.json()
    assert body["phase_changed"] is False
    assert body["previous_phase"] is None
    assert body["phase_transition_message"] is None
    assert body["current_phase"] == "DIAGNOSTIC"
    assert body["question_id"] == "ALG_EQ_DIAG_001"


def test_transition_step_back_resets_guided_counters(monkeypatch) -> None:
    # Spec case: INDEPENDENT_PRACTICE -> GUIDED_PRACTICE is a valid step back.
    session_id = _start_session("ST022", initial_phase="INDEPENDENT_PRACTICE")
    _fake_pipeline(monkeypatch, student_phase="GUIDED_PRACTICE")

    response = client.post("/interaction", json=_interaction_body(session_id, "ST022"))

    assert response.status_code == 200
    body = response.json()
    assert body["phase_changed"] is True
    assert body["previous_phase"] == "INDEPENDENT_PRACTICE"
    assert body["phase_transition_message"] == "Let us work through this part together."
    assert body["attempt_count"] == 0


def test_transition_blocked_when_invalid_or_unknown(monkeypatch) -> None:
    # Spec cases: invalid transitions and unrecognised phases are logged and
    # ignored, never executed.
    for recommended in ("INDEPENDENT_PRACTICE", "MASTERY"):
        session_id = _start_session("ST023")
        _fake_pipeline(monkeypatch, student_phase=recommended)

        response = client.post("/interaction", json=_interaction_body(session_id, "ST023"))

        assert response.status_code == 200
        body = response.json()
        assert body["phase_changed"] is False
        assert body["current_phase"] == "DIAGNOSTIC"


def test_transition_skipped_on_null_recommendation(monkeypatch) -> None:
    # Spec case: Tamil returns null (and no tutor fallback) -> stay put.
    session_id = _start_session("ST024")
    _fake_pipeline(monkeypatch)

    response = client.post("/interaction", json=_interaction_body(session_id, "ST024"))

    assert response.status_code == 200
    body = response.json()
    assert body["phase_changed"] is False
    assert body["current_phase"] == "DIAGNOSTIC"


def test_transition_rolls_back_when_question_fetch_fails(monkeypatch) -> None:
    # Spec case: Aditya has no question for the concept -> error response and
    # the session phase is left untouched.
    session_id = _start_session("ST025", concept_id="UNKNOWN_CONCEPT")
    _fake_pipeline(monkeypatch, student_phase="GUIDED_PRACTICE")

    response = client.post(
        "/interaction",
        json=_interaction_body(session_id, "ST025", concept_id="UNKNOWN_CONCEPT"),
    )

    assert response.status_code == 503
    body = response.json()
    assert body["error_code"] == "QUESTION_FETCH_FAILED"
    assert body["message"] == "Could not load the next question. Please try again."

    stored = client.get(f"/session/{session_id}").json()
    assert stored["current_phase"] == "DIAGNOSTIC"
    assert stored["question_id"] == "ALG_EQ_DIAG_001"


def _hint_ctx(message: str) -> AdapterContext:
    return AdapterContext(
        session_id="SESSION001",
        student_id="ST001",
        message=message,
        question="Solve for x: x + 4 = 9",
        correct_answer="x = 5",
        current_phase="GUIDED_PRACTICE",
        input_source="TEXT",
        concept_id="ALG_LINEAR_ONE_STEP",
        attempt_count=1,
        current_hint_level=None,
    )


def test_retrieval_gated_on_guided_hint() -> None:
    # RAG only runs after classification, and only for GUIDED_HINT: documents are
    # present iff that's the chosen strategy.
    for message in ("x = 5", "x = 6", "banana"):
        rag, _, tutor = asyncio.run(interaction_service.run_tutor_pipeline(_hint_ctx(message)))
        assert bool(rag.documents) == (tutor.response_strategy == "GUIDED_HINT")


def test_build_retrieve_payload_uses_classified_fields() -> None:
    payload = MockRAGServiceAdapter()._build_retrieve_payload(
        _hint_ctx("x = 6"), error_type="ARITHMETIC_ERROR", hint_level=2
    )
    assert payload["content_type"] == "HINT"
    assert payload["error_type"] == "ARITHMETIC_ERROR"
    assert payload["hint_level"] == 2
    assert payload["input_source"] == "TEXT"
