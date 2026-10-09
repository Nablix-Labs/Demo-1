import json
import os

import pytest

from app.ai_engine.classifier import build_openai_ai_engine_client
from app.ai_engine.teach_back import build_teach_back_context, generate_teach_back_reply, validate_teach_back_reply
from app.core.config import Settings
from app.models.teach_back import TeachBackPayload
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


def test_live_teach_back_advances_between_distinct_concepts(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.getenv("NABLIX_RUN_OPENAI_SMOKE") != "true":
        pytest.skip("Set NABLIX_RUN_OPENAI_SMOKE=true to run the billed AI smoke evaluation.")
    settings = Settings(use_openai_ai_engine=True)
    if not settings.openai_api_key:
        pytest.fail("NABLIX_OPENAI_API_KEY is required for the live AI evaluation.")
    monkeypatch.setattr("app.ai_engine.teach_back.get_settings", lambda: settings)
    raw = teach_back_content()
    raw["targets"][0]["micro_skill_definition"] = "Recognise a fixed operation across changing starting quantities."
    raw["targets"][0]["expected_concept"] = "In 4+4 and 5+4, the starting number changes and adding 4 stays fixed."
    raw["targets"][1]["micro_skill_definition"] = "Use a letter to represent a changing quantity."
    raw["targets"][1]["expected_concept"] = "A letter represents the changing starting quantity in n+4."
    raw["phase1_context"]["teaching_summary"][0].update(skill_name="Recognise repeated structure", summary="The starting number varies but adding four stays fixed.")
    raw["phase1_context"]["teaching_summary"][1].update(skill_name="Represent changing quantities", summary="In n+4, n represents a changing starting number.")
    raw["worked_example_context"]["worked_examples"][0]["steps"][0].update(screen_content="4+4, 5+4, n+4", narration_text="Adding four stays fixed; n represents the changing starting number.")
    first_message = "The starting number changes and plus four stays the same."
    first = generate_teach_back_reply(TeachBackPayload.model_validate(raw), first_message, "TEXT", None, [])
    assert first.evaluation.understanding_status == "UNDERSTOOD", first.model_dump()
    assert first.next_action == "NEXT_MICRO_SKILL"
    assert "letter" in first.tutor_message.lower(), first.model_dump()
    history = [ConversationMessage(role="user", content=first_message),
               ConversationMessage(role="assistant", content=first.tutor_message)]
    raw["state"]["completed_micro_skill_ids"] = ["T02.M1"]
    raw["state"]["current_micro_skill_id"] = "T02.M2"
    raw["state"]["status"] = "IN_PROGRESS"
    content = TeachBackPayload.model_validate(raw)
    navigation = generate_teach_back_reply(content, "next tell me", "TEXT", None, history)
    assert navigation.evaluation.understanding_status is None
    final = generate_teach_back_reply(content, "N represents the starting number that changes, so I write n plus four.", "TEXT", None, history)
    assert final.evaluation.understanding_status == "UNDERSTOOD", final.model_dump()
    assert final.next_action == "MOVE_TO_PHASE_2"
    print(json.dumps({"first": first.model_dump(), "navigation": navigation.model_dump(), "final": final.model_dump()}, ensure_ascii=False))
