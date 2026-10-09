import json
import os
import re

import pytest

from app.ai_engine.classifier import build_openai_ai_engine_client
from app.ai_engine.teach_back import build_teach_back_context, generate_teach_back_reply, validate_teach_back_reply
from app.core.config import Settings
from app.models.teach_back import TeachBackPayload, TeachBackReply
from app.models.adapters import ConversationMessage
from tests.test_teach_back_engine import teach_back_content


def test_live_teach_back_conversation(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.getenv("NABLIX_RUN_OPENAI_SMOKE") != "true":
        pytest.skip("Set NABLIX_RUN_OPENAI_SMOKE=true to run the billed AI smoke evaluation.")
    settings = Settings(use_openai_ai_engine=True)
    if not settings.openai_api_key:
        pytest.skip("Set NABLIX_OPENAI_API_KEY to run the live AI evaluation.")
    monkeypatch.setattr("app.ai_engine.teach_back.get_settings", lambda: settings)
    cases: list[tuple[str, str | None, int]] = [
        ("It's a number we don't know yet, so we use a letter for it.", "UNDERSTOOD", 0),
        ("The letter is the name of an object, like apples.", "MISCONCEPTION", 0),
        ("Why do we use a letter instead of a number?", None, 0),
        ("I want to talk about football.", None, 0),
        ("I still think the letter is an object.", "MISCONCEPTION", 1),
    ]
    for message, expected, failures in cases:
        raw = teach_back_content()
        raw["state"]["failed_explanation_count"] = failures
        reply = generate_teach_back_reply(TeachBackPayload.model_validate(raw), message, "TEXT", None, [])
        assert reply.evaluation.understanding_status == expected
        assert len(reply.tutor_message.split()) <= 100
        if failures == 1:
            assert reply.next_action == "RETURN_TO_ORIENTATION"
            assert "?" not in reply.tutor_message
        print(json.dumps({"student": message, "reply": reply.model_dump()}, ensure_ascii=False))
    raw = teach_back_content()
    raw["state"]["completed_micro_skill_ids"] = ["T02.M1"]
    raw["state"]["current_micro_skill_id"] = "T02.M2"
    final = generate_teach_back_reply(
        TeachBackPayload.model_validate(raw), "A letter stands for a number we don't know yet.", "TEXT", None, [],
    )
    assert final.evaluation.understanding_status == "UNDERSTOOD"
    assert final.next_action == "MOVE_TO_PHASE_2"
    assert "?" not in final.tutor_message
    print(json.dumps({"final_reply": final.model_dump()}, ensure_ascii=False))


@pytest.mark.parametrize("message", ["next tell me", "I'm ready for the next one", "okay next please"])
def test_live_teach_back_navigation_is_not_evidence(message: str, monkeypatch: pytest.MonkeyPatch) -> None:
    if os.getenv("NABLIX_RUN_OPENAI_SMOKE") != "true":
        pytest.skip("Set NABLIX_RUN_OPENAI_SMOKE=true to run the billed AI smoke evaluation.")
    settings = Settings(use_openai_ai_engine=True)
    if not settings.openai_api_key:
        pytest.fail("NABLIX_OPENAI_API_KEY is required for the live AI evaluation.")
    monkeypatch.setattr("app.ai_engine.teach_back.get_settings", lambda: settings)
    content = TeachBackPayload.model_validate(teach_back_content())
    history = [ConversationMessage(role="user", content="A letter stands for a number we do not know yet."),
               ConversationMessage(role="assistant", content="You explained that a letter represents the changing quantity.")]
    engine = build_openai_ai_engine_client(settings)
    assert engine is not None
    reply = generate_teach_back_reply(content, message, "VOICE", 0.95, history)
    assert reply.evaluation.understanding_status is None, reply.model_dump()
    context = build_teach_back_context(content, message, "VOICE", 0.95)
    model_reply = engine.generate_teach_back(context, reply.model_json_schema(), history)
    parsed = type(reply).model_validate(model_reply)
    validate_teach_back_reply(content, parsed)
    assert parsed.evaluation.understanding_status is None, parsed.model_dump()
    print(json.dumps({"student": message, "reply": parsed.model_dump()}, ensure_ascii=False))


CURIOUS_STUDENT_TURNS: tuple[tuple[str, str | None, str], ...] = (
    ("Why are we comparing the starting numbers?", None, "T02.M1"),
    ("So then, um, I lost my words.", None, "T02.M1"),
    ("The starting number always stays fixed, and the operation changes each time.", "MISCONCEPTION", "T02.M1"),
    ("The starting number changes and plus four stays the same.", "UNDERSTOOD", "T02.M1"),
    ("What do you mean by a letter here?", None, "T02.M2"),
    ("N is, um, I haven't finished explaining yet.", None, "T02.M2"),
    ("N is the name of an object, like apples, rather than a number.", "MISCONCEPTION", "T02.M2"),
    ("N represents the starting number that changes, so I write n plus four.", "UNDERSTOOD", "T02.M2"),
)


def repeated_structure_content() -> TeachBackPayload:
    raw = teach_back_content()
    raw["targets"][0].update(
        micro_skill_definition="Recognise a fixed operation across changing starting quantities.",
        expected_concept="In 4+4 and 5+4, the starting number changes and adding 4 stays fixed.",
        known_misconceptions=[{"error_code": "ERR-FIXED", "description": "Treating the starting number as fixed and the operation as changing."}],
    )
    raw["targets"][1].update(
        micro_skill_definition="Use a letter to represent a changing quantity.",
        expected_concept="A letter represents the changing starting quantity in n+4.",
    )
    raw["phase1_context"]["teaching_summary"][0].update(skill_name="Recognise repeated structure", summary="The starting number varies but adding four stays fixed.")
    raw["phase1_context"]["teaching_summary"][1].update(skill_name="Represent changing quantities", summary="In n+4, n represents a changing starting number.")
    raw["worked_example_context"]["worked_examples"][0]["steps"][0].update(screen_content="4+4, 5+4, n+4", narration_text="Adding four stays fixed; n represents the changing starting number.")
    return TeachBackPayload.model_validate(raw)


def assert_curiosity_without_grading(reply: TeachBackReply) -> None:
    for message in (reply.tutor_message, reply.tutor_message_voice):
        assert re.search(r"\b(?:i|me|my)\b", message, flags=re.IGNORECASE), reply.model_dump()
        assert not any(phrase in message.lower() for phrase in (
            "great job", "well done", "you've got the idea", "you’ve got the idea", "that's correct",
            "that’s correct", "now let's explore", "now let’s explore", "remember,",
        )), reply.model_dump()


def assert_question_answered(message: str, reply: TeachBackReply) -> None:
    required_words = {
        CURIOUS_STUDENT_TURNS[0][0]: ("fixed", "same"),
        CURIOUS_STUDENT_TURNS[4][0]: ("number", "quantity"),
    }.get(message)
    if required_words is not None:
        for wording in (reply.tutor_message, reply.tutor_message_voice):
            answer = " ".join(sentence for sentence in re.findall(r"[^.!?]+[.!?]", wording.lower()) if not sentence.endswith("?"))
            assert any(word in answer for word in required_words), reply.model_dump()
            assert "couldn't follow" not in answer and "couldn’t follow" not in answer, reply.model_dump()


def test_standard_curiosity_through_complete_conversation(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.getenv("NABLIX_RUN_OPENAI_SMOKE") != "true":
        pytest.skip("Set NABLIX_RUN_OPENAI_SMOKE=true to run the billed AI smoke evaluation.")
    settings = Settings(use_openai_ai_engine=True)
    if not settings.openai_api_key:
        pytest.fail("NABLIX_OPENAI_API_KEY is required for the live AI evaluation.")
    monkeypatch.setattr("app.ai_engine.teach_back.get_settings", lambda: settings)
    content = repeated_structure_content()
    history: list[ConversationMessage] = []
    for message, verdict, current in CURIOUS_STUDENT_TURNS:
        assert content.state.current_micro_skill_id == current
        reply = generate_teach_back_reply(content, message, "TEXT", None, history)
        assert reply.evaluation.understanding_status == verdict, reply.model_dump()
        assert_curiosity_without_grading(reply)
        assert_question_answered(message, reply)
        history = [*history, ConversationMessage(role="user", content=message),
                   ConversationMessage(role="assistant", content=reply.tutor_message)]
        print(json.dumps({"skill": current, "student": message, "reply": reply.model_dump()}, ensure_ascii=False))
        if verdict == "UNDERSTOOD":
            completed = [*content.state.completed_micro_skill_ids, current]
            remaining = [skill for skill in content.state.target_micro_skill_ids if skill not in completed]
            assert reply.next_action == ("NEXT_MICRO_SKILL" if remaining else "MOVE_TO_PHASE_2")
            if remaining:
                assert "letter" in reply.tutor_message.lower(), reply.model_dump()
            content = content.model_copy(update={"state": content.state.model_copy(update={
                "completed_micro_skill_ids": completed, "current_micro_skill_id": remaining[0] if remaining else None,
                "failed_explanation_count": 0, "status": "IN_PROGRESS" if remaining else "COMPLETED",
            })})
        elif verdict == "MISCONCEPTION":
            assert reply.next_action == "ASK_REEXPLANATION"
            content = content.model_copy(update={"state": content.state.model_copy(update={
                "failed_explanation_count": content.state.failed_explanation_count + 1,
            })})
    assert content.state.completed_micro_skill_ids == content.state.target_micro_skill_ids
