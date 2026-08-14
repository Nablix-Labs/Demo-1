import asyncio
import json
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app import main
from app.adapters import student_model
from app.adapters.student_model import StudentModelServiceAdapter
from app.core.config import Settings
from app.core.exceptions import AdapterError, AdapterRequestRejected
from app.models.student_model_session import SessionOpenedEvent
from app.models.student_model_session import (
    StudentModelSessionEvent,
    StudentModelSessionEventResponse,
)
from app.adapters import provider
from app.services import (
    canvas_service,
    interaction_service,
    session_service,
    student_model_debug,
)
from tests.test_canvas import VALID_SNAPSHOT_DATA_URL, _start_session, client
from tests.test_session_events import _session_opened_response


def _event(request_id: str) -> SessionOpenedEvent:
    return SessionOpenedEvent(
        request_id=request_id,
        event_type="SESSION_OPENED",
        topic_id="ALG-ORI-02",
        student_id="ST001",
        timestamp="2026-08-12T00:00:00Z",
    )


def _adapter() -> StudentModelServiceAdapter:
    return StudentModelServiceAdapter(
        Settings(
            student_model_url="https://student-model.test",
            use_mock_student_model=False,
        )
    )


def test_debug_capture_is_disabled_by_default() -> None:
    student_model_debug.begin(False)
    student_model_debug.record_request({"event_type": "SESSION_OPENED"})
    assert student_model_debug.payload() is None


def test_debug_capture_pairs_multiple_student_model_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, url, headers, timeout_seconds, retry_count
        body = _session_opened_response("PHASE_2_GUIDED_LEARNING")
        body["request_id"] = payload["request_id"]
        return body

    monkeypatch.setattr(student_model, "post_json", fake_post_json)
    student_model_debug.begin(True)
    adapter = _adapter()
    asyncio.run(adapter.send_session_event(_event("REQ-1"), "token"))
    asyncio.run(adapter.send_session_event(_event("REQ-2"), "token"))

    debug = student_model_debug.payload()
    assert debug is not None
    requests = debug["student_model_request"]
    responses = debug["student_model_response"]
    assert [body["request_id"] for body in requests] == ["REQ-1", "REQ-2"]
    assert [body["request_id"] for body in responses] == ["REQ-1", "REQ-2"]


def test_debug_capture_records_downstream_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, headers, timeout_seconds, retry_count
        raise AdapterRequestRejected(
            "student_model",
            url,
            401,
            '{"error_code":"INVALID_TOKEN"}',
            payload,
        )

    monkeypatch.setattr(student_model, "post_json", fake_post_json)
    student_model_debug.begin(True)

    with pytest.raises(AdapterRequestRejected):
        asyncio.run(_adapter().send_session_event(_event("REQ-401"), "token"))

    debug = student_model_debug.payload()
    assert debug is not None
    assert debug["student_model_request"][0]["request_id"] == "REQ-401"
    assert debug["student_model_response"] == [
        {
            "status_code": 401,
            "response_body": '{"error_code":"INVALID_TOKEN"}',
        }
    ]


@pytest.mark.parametrize("enabled", [False, True])
def test_interaction_response_includes_debug_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
) -> None:
    async def fake_process(request: object, access_token: str) -> object:
        del request, access_token
        student_model_debug.record_request({"request_id": "REQ-1"})
        student_model_debug.record_response({"request_id": "REQ-1"})
        return interaction_service.InteractionResponse.model_construct(
            status=None,
            interaction_state_version=0,
        )

    monkeypatch.setattr(interaction_service, "_process_interaction", fake_process)
    monkeypatch.setattr(
        interaction_service,
        "get_settings",
        lambda: Settings(debug_json_view=enabled),
    )

    response = asyncio.run(
        interaction_service.process_interaction(
            SimpleNamespace(
                session_id="SESSION-DEBUG",
                turn_id="TURN-DEBUG",
                input_source="TEXT",
                interaction_type="ANSWER_SUBMISSION",
            ),
            "token",
        )
    )

    assert isinstance(response, interaction_service.InteractionResponse)
    assert (response.debug is not None) is enabled


def test_debug_capture_records_raw_response_before_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A body the Schema 3.0 model rejects is still shown to the tester."""

    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> dict[str, object]:
        del adapter_name, url, payload, headers, timeout_seconds, retry_count
        return {"not": "a valid session event response"}

    monkeypatch.setattr(student_model, "post_json", fake_post_json)
    student_model_debug.begin(True)

    with pytest.raises(AdapterError):
        asyncio.run(_adapter().send_session_event(_event("REQ-BAD"), "token"))

    debug = student_model_debug.payload()
    assert debug is not None
    # Recorded once, by the post-`post_json` line rather than the error path.
    assert debug["student_model_response"] == [{"not": "a valid session event response"}]


def test_error_envelope_carries_the_captured_exchange() -> None:
    """AdapterError/AdapterRequestRejected are HTTPExceptions, so they land here."""

    student_model_debug.begin(True)
    student_model_debug.record_request({"request_id": "REQ-1"})
    student_model_debug.record_response({"status_code": 401, "response_body": "{}"})

    response = main._error_response(
        Request({"type": "http", "headers": [], "method": "POST", "path": "/interaction"}),
        503,
        "ADAPTER_UNAVAILABLE",
        "Service Temporarily Unavailable",
    )

    body = json.loads(response.body)
    assert body["error_code"] == "ADAPTER_UNAVAILABLE"
    assert body["debug"]["student_model_request"] == [{"request_id": "REQ-1"}]


def test_error_envelope_omits_debug_when_nothing_was_captured() -> None:
    student_model_debug.begin(False)

    response = main._error_response(
        Request({"type": "http", "headers": [], "method": "POST", "path": "/interaction"}),
        422,
        "MISSING_FIELD",
        "student_id is required.",
    )

    assert "debug" not in json.loads(response.body)


def test_attaching_debug_leaves_the_cached_response_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cache stores by reference, so a replay must not inherit this exchange."""

    cached = interaction_service.InteractionResponse.model_construct(
        status=None,
        interaction_state_version=0,
    )

    async def fake_process(request: object, access_token: str) -> object:
        del request, access_token
        student_model_debug.record_request({"request_id": "REQ-1"})
        student_model_debug.record_response({"request_id": "REQ-1"})
        return cached

    monkeypatch.setattr(interaction_service, "_process_interaction", fake_process)
    monkeypatch.setattr(
        interaction_service,
        "get_settings",
        lambda: Settings(debug_json_view=True),
    )

    response = asyncio.run(
        interaction_service.process_interaction(
            SimpleNamespace(
                session_id="SESSION-DEBUG",
                turn_id="TURN-DEBUG",
                input_source="TEXT",
                interaction_type="ANSWER_SUBMISSION",
            ),
            "token",
        )
    )

    assert response is not cached
    assert response.debug is not None
    assert cached.debug is None


def test_canvas_submit_returns_the_debug_object(monkeypatch: pytest.MonkeyPatch) -> None:
    """/canvas/submit bypasses process_interaction, so it needs its own boundary.

    The adapter instrumentation is covered by the post_json tests above; this
    drives the recorder deliberately to prove the begin()/attach wiring.
    """

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        body = _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
        body["request_id"] = event.request_id
        student_model_debug.record_request({"request_id": event.request_id})
        student_model_debug.record_response({"request_id": event.request_id})
        return StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send_session_event)
    monkeypatch.setattr(
        canvas_service, "get_settings", lambda: Settings(debug_json_view=True)
    )
    # /session/start refuses a concept with no Student Model topic code, and the
    # test_canvas autouse fixture does not follow the imported _start_session.
    session_settings = Settings(
        student_model_url="https://student-model.test",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        use_mock_student_model=False,
        use_openai_ai_engine=False,
    )
    monkeypatch.setattr(provider, "get_settings", lambda: session_settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: session_settings)

    session_id = _start_session("ST001")
    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST001",
            "turn_id": "TURN-ST001-CANVAS-DEBUG",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
        },
    )

    assert response.status_code == 200
    debug = response.json()["debug"]
    assert debug["student_model_request"]
    assert len(debug["student_model_request"]) == len(debug["student_model_response"])
