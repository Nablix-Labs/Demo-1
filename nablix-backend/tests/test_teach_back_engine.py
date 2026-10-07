import asyncio
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.adapters.tutor_engine import TutorEngineServiceAdapter
from app.ai_engine import teach_back
from app.core.config import Settings
from app.core.exceptions import AdapterError
from app.main import app
from app.models.adapters import ConversationMessage
from app.models.teach_back import TeachBackEvaluation, TeachBackPayload, TeachBackReply


def teach_back_content() -> dict[str, object]:
    return {
        "teach_back_id": "TB-CHECK", "topic_id": "ALG-ORI-02",
        "targets": [{
            "micro_skill_id": s, "source_diagnostic_questions": [{"question_id": f"Q-{s}", "question_usage_id": f"U-{s}"}],
            "micro_skill_definition": "A letter represents a quantity.",
            "expected_concept": "A letter stands for an unknown number.",
            "known_misconceptions": [{"error_code": "ERR-LETTER", "description": "Treating a letter as an object."}],
        } for s in ["T02.M1", "T02.M2"]],
        "phase1_context": {
            "taught_micro_skill_ids": ["T02.M1", "T02.M2"],
            "completed_content_ids": {"orientation_video_id": "V1", "worked_example_ids": ["WE1"]},
            "teaching_summary": [{"micro_skill_id": s, "skill_name": "Unknown numbers", "summary": "Letters stand for numbers."} for s in ["T02.M1", "T02.M2"]],
        },
        "worked_example_context": {"worked_examples": [{
            "worked_example_id": "WE1", "title": "Letters and quantities", "covered_micro_skill_ids": ["T02.M1", "T02.M2"],
            "final_answer": "x = 3", "student_answer_required": False,
            "steps": [{"step_id": "S1", "sequence_no": 1, "screen_content": "x + 2 = 5", "narration_text": "The letter stands for a number.", "must_show": None, "must_not_show": None}],
        }]},
        "state": {"teach_back_id": "TB-CHECK", "status": "NOT_STARTED", "target_micro_skill_ids": ["T02.M1", "T02.M2"], "completed_micro_skill_ids": [], "current_micro_skill_id": "T02.M1", "conversation_mode": "ASK_TEACH_BACK", "failed_explanation_count": 0, "last_tutor_response": None},
    }


@pytest.fixture
def conceptual_ai(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict[str, object]] = []

    class ConceptClient:
        def generate_teach_back(self, context: dict[str, object], schema: dict[str, object], history: list[ConversationMessage]) -> dict[str, object]:
            calls.append(context)
            message = context["student_input"]
            verdict = None if message in {"Why?", "Help me understand", "Football"} else "UNDERSTOOD" if message == "A letter stands for a number" else "MISCONCEPTION"
            action = "DISCUSS_AND_CLARIFY" if verdict is None else context["required_actions"][verdict]
            return {
                "evaluation": {"understanding_status": verdict, "misconception_detected": verdict == "MISCONCEPTION", "error_code": "ERR-LETTER" if verdict == "MISCONCEPTION" else None, "unmapped_misconception_description": None},
                "tutor_message": "The letter represents a number.", "tutor_message_voice": "The letter represents a number.",
                "next_action": action,
            }

    monkeypatch.setattr(teach_back, "build_openai_ai_engine_client", lambda settings: ConceptClient())
    return calls


@pytest.mark.parametrize("message,failures,completed,verdict,action", [
    ("A letter stands for a number", 0, [], "UNDERSTOOD", "NEXT_MICRO_SKILL"),
    ("A letter stands for a number", 1, [], "UNDERSTOOD", "NEXT_MICRO_SKILL"),
    ("A letter stands for a number", 0, ["T02.M2"], "UNDERSTOOD", "MOVE_TO_PHASE_2"),
    ("It is an object", 0, [], "MISCONCEPTION", "ASK_REEXPLANATION"),
    ("It is an object", 1, [], "MISCONCEPTION", "RETURN_TO_ORIENTATION"),
    ("Why?", 1, [], None, "DISCUSS_AND_CLARIFY"),
    ("Help me understand", 1, [], None, "DISCUSS_AND_CLARIFY"),
    ("Football", 1, [], None, "DISCUSS_AND_CLARIFY"),
])
def test_conceptual_ai_endpoint_does_not_mutate_progress(conceptual_ai, message, failures, completed, verdict, action):
    content = teach_back_content()
    content["state"]["failed_explanation_count"] = failures
    content["state"]["completed_micro_skill_ids"] = completed
    before = deepcopy(content)
    response = TestClient(app).post("/ai-engine/teach-back/respond", json={
        "content": content, "student_input": message, "input_source": "TEXT",
        "transcript_confidence": None, "conversation_history": [],
    })
    assert response.status_code == 200, response.text
    assert response.json()["evaluation"]["understanding_status"] == verdict
    assert response.json()["next_action"] == action
    assert len(conceptual_ai) == 1
    assert content == before


@pytest.mark.parametrize("message,source,confidence", [("okay", "TEXT", None), ("", "TEXT", None), ("unclear", "VOICE", 0.1)])
def test_acknowledgements_and_unclear_voice_do_not_fail(conceptual_ai, message, source, confidence):
    reply = teach_back.generate_teach_back_reply(TeachBackPayload.model_validate(teach_back_content()), message, source, confidence, [])
    assert reply.evaluation.understanding_status is None
    assert reply.next_action == "ASK_TEACH_BACK"
    assert not conceptual_ai


def test_tutor_engine_has_a_dedicated_conceptual_path(conceptual_ai):
    adapter = TutorEngineServiceAdapter(Settings())
    reply = asyncio.run(adapter.respond_to_teach_back(
        TeachBackPayload.model_validate(teach_back_content()), "A letter stands for a number", "TEXT", None, [],
    ))
    assert reply.evaluation.understanding_status == "UNDERSTOOD"
    assert len(conceptual_ai) == 1


@pytest.mark.parametrize("code,message,action", [
    ("INVENTED", "Letters stand for numbers.", "ASK_REEXPLANATION"),
    ("ERR-LETTER", "Your error is ERR-LETTER.", "ASK_REEXPLANATION"),
    ("ERR-LETTER", "Letters stand for numbers.", "MOVE_TO_PHASE_2"),
])
def test_invalid_error_codes_leaked_ids_and_progression_are_rejected(code, message, action):
    reply = TeachBackReply(
        evaluation=TeachBackEvaluation(understanding_status="MISCONCEPTION", misconception_detected=True, error_code=code, unmapped_misconception_description=None),
        tutor_message=message, tutor_message_voice=message, next_action=action,
    )
    with pytest.raises(ValueError):
        teach_back.validate_teach_back_reply(TeachBackPayload.model_validate(teach_back_content()), reply)


def test_missing_teaching_content_is_an_explicit_error(conceptual_ai):
    content = teach_back_content()
    content["phase1_context"]["completed_content_ids"]["worked_example_ids"] = []
    with pytest.raises(AdapterError, match="completed worked example"):
        teach_back.generate_teach_back_reply(TeachBackPayload.model_validate(content), "Explain", "TEXT", None, [])
    assert not conceptual_ai


def test_service_failure_is_not_converted_to_progress(monkeypatch):
    monkeypatch.setattr(teach_back, "build_openai_ai_engine_client", lambda settings: None)
    with pytest.raises(AdapterError, match="API key"):
        teach_back.generate_teach_back_reply(TeachBackPayload.model_validate(teach_back_content()), "Explain", "TEXT", None, [])
