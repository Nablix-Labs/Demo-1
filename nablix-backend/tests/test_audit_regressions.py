"""Regression tests covering choice feedback and transition voice fixes.

Fixes tested:
- Issue #324: selected_option_text resolved for wrong choices in classifier.
- Issue #311: _db_error_code matches option ID and option text from choice submissions.
- Issue #308: message_voice is audible across phase transitions.
- InteractionRequest validation preserves selected_option_text.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.ai_engine.classifier import (
    ClassificationRequest,
    selected_option_text,
    selected_option_text_for_choice,
)
from app.models.guided_learning import GuidedTeachingState
from app.models.interaction import InteractionRequest
from app.models.session import CanvasState, SessionRecord, VoiceState
from app.models.student_model_session import AnswerSpec
from app.services.interaction_service import _db_error_code, _response_from


def test_interaction_request_preserves_selected_option_text() -> None:
    req = InteractionRequest(
        session_id="SESSION001",
        student_id="ST001",
        turn_id="TURN-001",
        interaction_type="ANSWER_SUBMISSION",
        input_source="CHOICE",
        selected_option_id="B",
        selected_option_text="p decreases by 2",
        current_phase="INDEPENDENT_PRACTICE",
        concept_id="ALG_LINEAR_ONE_STEP",
        question_id="Q-001",
        hint_count=0,
    )
    assert req.selected_option_id == "B"
    assert req.selected_option_text == "p decreases by 2"


def test_selected_option_text_for_wrong_choice() -> None:
    spec = AnswerSpec(
        answer_spec_id="SPEC-1",
        canonical_answer="A",
        accepted_answers=["A", "p increases by 2"],
        verification_method="EXACT_MATCH",
    )
    # Case 1: text present on guided_teaching_state
    req_with_state = ClassificationRequest(
        question="What happens to p?",
        correct_answer="A",
        answer_spec=spec,
        student_input="Selected B: p decreases by 2",
        current_phase="GUIDED_PRACTICE",
        input_source="CHOICE",
        transcript_confidence=None,
        attempt_count=1,
        current_hint_level=None,
        guided_teaching_state=GuidedTeachingState(
            question_id="Q1",
            objective_component_ids=[],
            confirmed_component_ids=[],
            missing_component_ids=[],
            active_component_id=None,
            last_tutor_question_type="OPTION_COMPARISON",
            selected_option_id="B",
            selected_option_text="p decreases by 2",
            awaiting_response=True,
        ),
    )
    resolved = selected_option_text_for_choice(req_with_state, "B")
    assert resolved == "p decreases by 2"

    # Case 2: extracted from student_input when guided_teaching_state is None
    req_without_state = ClassificationRequest(
        question="What happens to p?",
        correct_answer="A",
        answer_spec=spec,
        student_input="Selected B: p decreases by 2",
        current_phase="INDEPENDENT_PRACTICE",
        input_source="CHOICE",
        transcript_confidence=None,
        attempt_count=1,
        current_hint_level=None,
    )
    resolved_from_input = selected_option_text_for_choice(req_without_state, "B")
    assert resolved_from_input == "p decreases by 2"

def test_selected_option_text_preserves_case() -> None:
    text = selected_option_text("Selected B: p decreases by 2")
    assert text == "p decreases by 2"

    text_upper = selected_option_text("SELECTED B: P DECREASES BY 2")
    assert text_upper == "P DECREASES BY 2"


def test_db_error_code_matches_choice_submission() -> None:
    session = MagicMock()
    session.student_model_event = MagicMock()
    session.student_model_event.phase_payload = None

    question = MagicMock()
    question.tutor_view = MagicMock()
    question.tutor_view.potential_errors = [
        {
            "error_code": "ERR_OPPOSITE_OPERATION",
            "response_patterns": ["B", "Option B", "p decreases by 2"],
        }
    ]
    session.active_student_model_question = question

    # Should match option id "B"
    matched_id = _db_error_code(session, "Selected B: n + 4")
    assert matched_id == "ERR_OPPOSITE_OPERATION"

    # Should match option text "p decreases by 2"
    matched_text = _db_error_code(session, "Selected C: p decreases by 2")
    assert matched_text == "ERR_OPPOSITE_OPERATION"

    # Should not match unrelated choice
    matched_none = _db_error_code(session, "Selected D: 4n")
    assert matched_none is None


def test_response_from_transition_voice_audibility() -> None:
    session = SessionRecord(
        session_id="SESSION001",
        student_id="ST001",
        concept_id="ALG_LINEAR_ONE_STEP",
        started_at=datetime.now(timezone.utc),
        current_phase="GUIDED_PRACTICE",
        previous_phase="INDEPENDENT_PRACTICE",
        current_question="What happens next?",
        question_id="Q1",
        question_number=1,
        interaction_mode="TEXT",
        voice_state=VoiceState(),
        canvas_state=CanvasState(),
        ui_state="{}",
        message="",
        last_processed_turn_id="TURN-001",
        last_tutor_turn_id="TUTOR-001",
        interaction_state_version=1,
        expected_student_response="EXPLANATION",
        show_canvas=False,
        show_hint_button=False,
        allow_text_input=True,
        allow_voice_input=True,
        hint_count=0,
        attempt_count=1,
        wrong_attempt_count=0,
        stuck_count=0,
        question_completed=False,
        answer_value_confirmed=False,
        recommended_entry_phase="GUIDED_PRACTICE", status="started",
    )

    resp = _response_from(
        session_id="SESSION001",
        student_id="ST001",
        turn_id="TURN-001",
        interaction_type="ANSWER_SUBMISSION",
        nudge_id=None,
        session=session,
        message="Let us work through this part together.",
        message_voice="",
        visual_cue=None,
        scaffold_steps=[],
        session_summary=None,
        conversation_action="ASK_QUESTION",
        attempt_increment=1,
        status=None,
        retry_safe=None,
        previous_phase="INDEPENDENT_PRACTICE",
    )

    assert resp.phase_changed is True
    assert resp.previous_phase == "INDEPENDENT_PRACTICE"
    assert resp.current_phase == "GUIDED_PRACTICE"
    assert resp.message_voice != ""
    assert "together" in resp.message_voice
