import json
import os

import pytest

from app.ai_engine.teach_back import generate_teach_back_reply
from app.core.config import Settings
from app.models.teach_back import TeachBackPayload
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
