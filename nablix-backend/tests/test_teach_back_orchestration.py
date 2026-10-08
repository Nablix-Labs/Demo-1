from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.adapters import provider, student_model
from app.core.config import Settings
from app.main import app
from app.models.session import SessionRecord
from app.services import session_service
from tests.test_session_events import _event_response
from tests.test_teach_back_engine import teach_back_content


client = TestClient(app, headers={"Authorization": "Bearer test-token"})


def teach_event(request_id: str, content: dict[str, object]) -> dict[str, object]:
    event = _event_response("WORKED_EXAMPLE_REQUESTED", request_id)
    event["phase_payload"] = {"phase": "PHASE_1_TEACH_BACK", "payload_type": "TEACH_BACK", "teach_back": deepcopy(content)}
    return event


@pytest.fixture
def teach_session(monkeypatch: pytest.MonkeyPatch) -> tuple[str, list[dict[str, object]]]:
    events: list[dict[str, object]] = []
    settings = Settings(student_model_url="https://student-model.example", use_mock_student_model=False,
                        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"})

    async def post(adapter_name: str, url: str, payload: dict[str, object], headers: dict[str, str], timeout_seconds: int, retry_count: int) -> dict[str, object]:
        events.append(deepcopy(payload))
        return teach_event(str(payload["request_id"]), teach_back_content())

    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(student_model, "post_json", post)
    response = client.post("/session/start", json={"student_id": "ST001", "concept_id": "ALG_LINEAR_ONE_STEP", "interaction_mode": "VOICE"})
    assert response.status_code == 200, response.text
    return response.json()["session_id"], events


def test_open_and_refresh_hide_internal_content(teach_session: tuple[str, list[dict[str, object]]]) -> None:
    session_id, _ = teach_session
    response = client.get(f"/session/{session_id}", params={"student_id": "ST001"})
    assert response.status_code == 200, response.text
    view = response.json()
    assert view["current_phase"] == "TEACH_BACK"
    assert view["question_id"] is None
    assert "Unknown numbers" in view["message"]
    assert view["allow_text_input"] and view["allow_voice_input"]
    assert not any(view[key] for key in ("show_canvas", "show_hint_button", "show_visual_cue", "show_scaffold_panel"))
    assert "teach_back_content" not in view
    assert "teach_back" not in view["student_model_event"]["phase_payload"]
    stored = session_service._sessions[session_id]
    restored = SessionRecord.model_validate(stored.model_dump(mode="json"))
    assert restored.teach_back_content == stored.teach_back_content
