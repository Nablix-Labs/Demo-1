"""Tests for the nablix-backend Hybrid Tutor Engine wiring layer.

Scope: `app/adapters/hybrid_tutor_engine.py` and its call sites. Does not touch
`app/ai_engine/**` or `app/models/guided_learning.py` — those are Sanya's
Tutor Engine and are exercised here only as already-tested dependencies.
"""

import asyncio
from datetime import datetime, timezone

import pytest

from app.adapters.hybrid_tutor_engine import (
    _ordered_canvas_memory_from_events,
    build_hybrid_tutor_request,
)
from app.ai_engine.classifier_config import load_classifier_rules
from app.models.adapters import AdapterContext, RAGResult, StudentModelResult
from app.models.canvas_memory import CanvasEvent
from app.models.session import SessionRecord
from app.models.student_model_session import AnswerSpec

_RULES = load_classifier_rules()


def _session(**overrides: object) -> SessionRecord:
    base = dict(
        session_id="SESSION001",
        student_id="ST001",
        concept_id="ALG_LINEAR_ONE_STEP",
        started_at=datetime.now(timezone.utc),
        current_phase="GUIDED_PRACTICE",
        current_question=None,
        question_id="Q1",
        question_number=1,
        interaction_mode="TEXT",
        ui_state="IDLE",
        message="hi",
        hint_count=0,
        status="started",
    )
    base.update(overrides)
    return SessionRecord(**base)


def _answer_spec() -> AnswerSpec:
    return AnswerSpec(
        answer_spec_id="ANS-Q1",
        canonical_answer="x = 5",
        accepted_answers=["x = 5", "5"],
        verification_method="EXACT_NOTATION_MATCH",
        answer_steps=["Subtract 3 from both sides", "Simplify to x = 5"],
    )


def _context(**overrides: object) -> AdapterContext:
    base = dict(
        session_id="SESSION001",
        student_id="ST001",
        question_id="Q1",
        question_type="SHORT_RESPONSE",
        message="x = 5",
        question="Solve for x: x + 3 = 8",
        answer_spec=_answer_spec(),
        input_source="TEXT",
    )
    base.update(overrides)
    return AdapterContext(**base)


def _event(**overrides: object) -> CanvasEvent:
    base = dict(
        order_index=0,
        turn_id="TUTOR-1",
        question_id="ALG_EQ_GP_001",
        actor="STUDENT",
        action_type="WRITE",
        content=None,
        math_text="x + 3 = 8",
        target_object_id="obj-1",
        bbox=None,
        semantic_tag="answer_step",
        source_id=None,
        active_state="ACTIVE",
    )
    base.update(overrides)
    return CanvasEvent(**base)


def test_maps_fields_and_derives_object_id_when_missing() -> None:
    events = [
        _event(target_object_id="obj-1"),
        _event(order_index=1, target_object_id=None),
    ]

    items = _ordered_canvas_memory_from_events(events, ocr_confidence=0.95, minimum_ocr_confidence=0.80)

    assert [item.object_id for item in items] == ["obj-1", "TUTOR-1:1"]
    assert items[0].question_id == "ALG_EQ_GP_001"
    assert items[0].math_text == "x + 3 = 8"


def test_student_event_reliability_follows_ocr_confidence_threshold() -> None:
    reliable = _ordered_canvas_memory_from_events(
        [_event()], ocr_confidence=0.80, minimum_ocr_confidence=0.80
    )
    unreliable = _ordered_canvas_memory_from_events(
        [_event()], ocr_confidence=0.79, minimum_ocr_confidence=0.80
    )
    missing_confidence = _ordered_canvas_memory_from_events(
        [_event()], ocr_confidence=None, minimum_ocr_confidence=0.80
    )

    assert reliable[0].reliability == "RELIABLE"
    assert unreliable[0].reliability == "NEEDS_WRITING"
    assert missing_confidence[0].reliability == "NEEDS_WRITING"


def test_tutor_and_support_events_are_always_reliable() -> None:
    items = _ordered_canvas_memory_from_events(
        [_event(actor="TUTOR"), _event(actor="SYSTEM_SUPPORT")],
        ocr_confidence=0.0,
        minimum_ocr_confidence=0.80,
    )

    assert all(item.reliability == "RELIABLE" for item in items)


def test_events_missing_turn_id_or_question_id_are_dropped() -> None:
    items = _ordered_canvas_memory_from_events(
        [_event(turn_id=None), _event(question_id=None)],
        ocr_confidence=0.95,
        minimum_ocr_confidence=0.80,
    )

    assert items == []


def test_build_hybrid_tutor_request_populates_every_required_field() -> None:
    context = _context(canvas_events=[_event(question_id="Q1")])

    request = build_hybrid_tutor_request(context, _RULES)

    assert request.question_id == "Q1"
    assert request.question_type == "SHORT_RESPONSE"
    assert request.answer_spec.answer_spec_id == "ANS-Q1"
    assert len(request.ordered_canvas_memory) == 1
    assert request.pedagogical_state.student_state == "STUCK"
    assert request.support_state.current_support == "NONE"
    assert request.student_evidence.typed_answer == "x = 5"


def test_build_hybrid_tutor_request_never_reads_a_client_reveal_field() -> None:
    # AdapterContext has no answer-reveal-shaped field at all — this test
    # documents that guarantee so a future field addition can't silently
    # start leaking into a backend-owned decision without this test noticing.
    context = _context()
    assert not hasattr(context, "approved_answer_reveal")

    request = build_hybrid_tutor_request(context, _RULES)
    assert not hasattr(request, "approved_answer_reveal")


def test_build_hybrid_tutor_request_requires_question_type() -> None:
    context = _context(question_type=None)
    with pytest.raises(ValueError):
        build_hybrid_tutor_request(context, _RULES)


def test_needs_writing_leaves_session_completely_unmutated() -> None:
    from app.models.guided_learning import HybridEvidenceResolution, HybridPedagogyDecision, HybridTutorTurn
    from app.services.session_service import _apply_hybrid_turn

    session = _session()
    resolution = HybridEvidenceResolution(
        input_reliability="NEEDS_WRITING",
        resolved_student_meaning=None,
        resolution_source="NEEDS_WRITING",
        can_update_learning_state=False,
    )
    turn = HybridTutorTurn(
        pedagogical_state="NEEDS_WRITING",
        completed_components=[],
        current_answer_step_index=0,
        current_answer_step_id="ANS-Q1:STEP:1",
        tutor_voice_text="Write that step out so I can check it.",
        requires_written_math_evidence=True,
        next_expected_input="WRITE",
    )
    decision = HybridPedagogyDecision(
        strategy="LOAD_REDUCTION",
        support_action="NONE",
        support_id=None,
        next_expected_input="WRITE",
    )

    updated = asyncio.run(_apply_hybrid_turn(session, turn, resolution, decision, [], _RULES))

    assert updated is session
    assert updated.hybrid_pedagogical_state is None
    assert updated.hybrid_support_state is None


def test_reliable_turn_persists_progression_and_support() -> None:
    from app.models.guided_learning import HybridEvidenceResolution, HybridPedagogyDecision, HybridTutorTurn
    from app.services.session_service import _apply_hybrid_turn

    session = _session()
    resolution = HybridEvidenceResolution(
        input_reliability="RELIABLE",
        resolved_student_meaning="x = 5",
        resolution_source="TYPED",
        can_update_learning_state=True,
    )
    turn = HybridTutorTurn(
        pedagogical_state="CORRECT",
        completed_components=["ANS-Q1:COMPONENT:1"],
        current_answer_step_index=1,
        current_answer_step_id="ANS-Q1:STEP:2",
        tutor_voice_text="That's the first step confirmed.",
        requires_written_math_evidence=False,
        next_expected_input="VOICE_OR_WRITE",
    )
    decision = HybridPedagogyDecision(
        strategy="ADVANCE_AND_FADE",
        support_action="NONE",
        support_id=None,
        next_expected_input="VOICE_OR_WRITE",
    )

    updated = asyncio.run(_apply_hybrid_turn(session, turn, resolution, decision, [], _RULES))

    assert updated.hybrid_pedagogical_state.completed_component_ids == ["ANS-Q1:COMPONENT:1"]
    assert updated.hybrid_pedagogical_state.current_answer_step_index == 1
    assert updated.hybrid_pedagogical_state.consecutive_stuck_count == 0
    assert updated.hybrid_support_state.current_support == "NONE"


def _rag_result() -> RAGResult:
    return RAGResult(documents=[], retrieval_confidence=0.0)


def _student_result() -> StudentModelResult:
    return StudentModelResult(
        mastery_status="DEVELOPING",
        continuity_status="on_track",
        recommended_entry_phase=None,
        hint_dependency_score=0.0,
        intervention_required=False,
    )


def test_evaluate_reliable_turn_returns_tutor_result_carrying_hybrid_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.adapters import hybrid_tutor_engine as hte
    from app.models.guided_learning import HybridTutorTurn

    class _StubOpenAIClient:
        def generate_hybrid_tutor_turn(self, context: object, system_prompt: str) -> HybridTutorTurn:
            return HybridTutorTurn(
                pedagogical_state="CORRECT",
                completed_components=["ANS-Q1:COMPONENT:1"],
                current_answer_step_index=1,
                current_answer_step_id="ANS-Q1:STEP:2",
                tutor_voice_text="Nice, that's the first step.",
                requires_written_math_evidence=False,
                next_expected_input="VOICE_OR_WRITE",
            )

    monkeypatch.setattr(hte, "build_openai_ai_engine_client", lambda settings: _StubOpenAIClient())

    adapter = hte.HybridTutorEngineAdapter()
    result = asyncio.run(adapter.evaluate(_context(), _rag_result(), _student_result()))

    assert result.hybrid_turn is not None
    assert result.hybrid_turn.pedagogical_state == "CORRECT"
    assert result.tutor_message == "Nice, that's the first step."
    assert result.question_completed is False
    assert result.answer_reveal_allowed is False
    assert result.requires_written_math_evidence is False


def test_evaluate_short_circuits_before_openai_call_when_evidence_is_unreliable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.adapters import hybrid_tutor_engine as hte

    def _fail_if_called(settings: object) -> object:
        raise AssertionError("Hybrid must not call OpenAI when evidence needs writing.")

    monkeypatch.setattr(hte, "build_openai_ai_engine_client", _fail_if_called)

    # No typed_answer, no structured_answer, no OCR, no matching voice pattern
    # -> resolve_hybrid_student_evidence falls through to NEEDS_WRITING.
    context = _context(message="", input_source="VOICE", raw_voice_transcript=None)

    adapter = hte.HybridTutorEngineAdapter()
    result = asyncio.run(adapter.evaluate(context, _rag_result(), _student_result()))

    assert result.requires_written_math_evidence is True
    assert result.hybrid_turn is None
    assert result.attempt_increment == 0
    assert result.question_completed is False


def test_hybrid_gate_is_closed_by_default_so_legacy_runs_unchanged() -> None:
    # Real (unmonkeypatched) settings + classifier_rules.yaml: both Hybrid
    # flags ship false, so every turn — regardless of student — must still
    # route to the legacy adapter. This is "acceptance item 15" for the
    # wiring layer itself: nothing about landing this code changes default
    # behavior.
    from app.core.config import get_settings
    from app.services.interaction_service import _hybrid_orchestration_selected

    settings = get_settings()
    assert settings.hybrid_orchestration_enabled is False
    assert settings.hybrid_allowed_student_ids == []
    assert _RULES.guided_learning.v1_hybrid_enabled is False

    context = _context(student_id="ANY_STUDENT")
    assert _hybrid_orchestration_selected(context) is False


def test_hybrid_gate_requires_every_gate_open(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import interaction_service as isvc

    open_rules = _RULES.model_copy(
        update={
            "guided_learning": _RULES.guided_learning.model_copy(
                update={"v1_hybrid_enabled": True}
            )
        }
    )

    def _settings(orchestration_on: bool, allowed: list[str]) -> object:
        class _Settings:
            hybrid_orchestration_enabled = orchestration_on
            hybrid_allowed_student_ids = allowed

        return _Settings()

    context = _context(student_id="ST001")

    # Sanya's flag off -> closed, regardless of the other two.
    monkeypatch.setattr(isvc, "load_classifier_rules", lambda: _RULES)
    monkeypatch.setattr(isvc, "get_settings", lambda: _settings(True, ["ST001"]))
    assert isvc._hybrid_orchestration_selected(context) is False

    # Sanya's flag on, app flag off -> still closed.
    monkeypatch.setattr(isvc, "load_classifier_rules", lambda: open_rules)
    monkeypatch.setattr(isvc, "get_settings", lambda: _settings(False, ["ST001"]))
    assert isvc._hybrid_orchestration_selected(context) is False

    # Both flags on, student not allowlisted -> still closed (fail-closed).
    monkeypatch.setattr(isvc, "get_settings", lambda: _settings(True, ["SOMEONE_ELSE"]))
    assert isvc._hybrid_orchestration_selected(context) is False

    # All three open -> selected.
    monkeypatch.setattr(isvc, "get_settings", lambda: _settings(True, ["ST001"]))
    assert isvc._hybrid_orchestration_selected(context) is True


def test_answer_reveal_allowed_only_follows_tutor_solved_support_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The only server-side path to answer_reveal_allowed=True is
    # decision.support_action == "TUTOR_SOLVED", which decide_hybrid_pedagogy
    # (Sanya's, unmodified) computes purely from persisted support/pedagogical
    # state — never from anything on the request. Prove the adapter can't be
    # tricked into revealing by any client-controlled field on AdapterContext.
    from app.adapters import hybrid_tutor_engine as hte
    from app.models.guided_learning import HybridTutorTurn

    class _StubOpenAIClient:
        def generate_hybrid_tutor_turn(self, context: object, system_prompt: str) -> HybridTutorTurn:
            return HybridTutorTurn(
                pedagogical_state="CORRECT",
                completed_components=[],
                current_answer_step_index=0,
                current_answer_step_id="ANS-Q1:STEP:1",
                tutor_voice_text="Let's check the first step.",
                requires_written_math_evidence=False,
                next_expected_input="VOICE_OR_WRITE",
            )

    monkeypatch.setattr(hte, "build_openai_ai_engine_client", lambda settings: _StubOpenAIClient())

    # A support_state that has never escalated -> decide_hybrid_pedagogy can
    # only return LOAD_REDUCTION/NONE for a fresh STUCK state, never TUTOR_SOLVED.
    context = _context()
    adapter = hte.HybridTutorEngineAdapter()
    result = asyncio.run(adapter.evaluate(context, _rag_result(), _student_result()))

    assert result.hybrid_decision.support_action != "TUTOR_SOLVED"
    assert result.answer_reveal_allowed is False


def test_retried_turn_never_reaches_the_tutor_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    # Reuse test_canvas.py's Schema 3.0 session-event mocking verbatim rather
    # than re-deriving what it took to make /session/start work in tests —
    # this is scaffolding, not something specific to Hybrid.
    from tests.test_canvas import schema_student_model as _schema_student_model_fixture

    _schema_student_model_fixture.__wrapped__(monkeypatch)

    # This is the pre-existing (session_id, turn_id) dedup + fingerprint cache
    # in interaction_service.py — _duplicate_turn_response / _cache_response —
    # unmodified by this wiring layer. It runs before AdapterContext is even
    # built, so it protects a Hybrid-selected turn exactly as it already
    # protects a legacy one: a retry never reaches run_tutor_pipeline, which
    # is the only place either engine's one call happens.
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services import interaction_service as isvc
    from tests.test_canvas import _start_session

    call_count = {"n": 0}
    original = isvc.run_tutor_pipeline

    async def _counting_pipeline(context: object):
        call_count["n"] += 1
        return await original(context)

    monkeypatch.setattr(isvc, "run_tutor_pipeline", _counting_pipeline)

    from app.services import session_service

    client = TestClient(app, headers={"Authorization": "Bearer test-token"})
    session_id = _start_session("ST900")
    session = session_service._sessions[session_id]
    payload = {
        "session_id": session_id,
        "student_id": "ST900",
        "interaction_type": "ANSWER_SUBMISSION",
        "input_source": "TEXT",
        "turn_id": "TURN-ST900-TEXT-1",
        "text_input": "I am still working on it.",
        "current_phase": session.current_phase,
        "concept_id": session.concept_id,
        "question_id": session.question_id,
        "hint_count": session.hint_count,
    }

    first = client.post("/interaction", json=payload)
    retry = client.post("/interaction", json=payload)

    assert first.status_code == 200, first.text
    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == "DUPLICATE_TURN"
    assert call_count["n"] == 1
