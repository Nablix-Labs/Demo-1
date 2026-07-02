"""Mock-only tests for vision provider selection and the OpenAI adapter mapping.

No network is touched: provider selection is pure, and the OpenAI adapter's HTTP
call is monkeypatched so these never spend OpenAI credits.
"""

import asyncio

import pytest

from app.adapters import openai_vision
from app.adapters.openai_vision import OpenAIVisionOCRAdapter
from app.adapters.provider import _build_vision_adapter
from app.adapters.vision_ocr import MockVisionOCRAdapter
from app.core.config import Settings
from app.core.exceptions import AdapterError

DATA_URL = "data:image/png;base64,aGVsbG8="


def _settings(**overrides) -> Settings:
    base = {
        "use_mock_vision": False,
        "openai_api_key": "sk-test",
        "min_ocr_confidence_threshold": 0.75,
    }
    base.update(overrides)
    return Settings(**base)


class _FakeResponse:
    def __init__(self, status_code: int, payload: object = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> object:
        return self._payload


def _patch_openai_post(monkeypatch, response: _FakeResponse) -> None:
    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *exc) -> bool:
            return False

        async def post(self, *args, **kwargs) -> _FakeResponse:
            return response

    monkeypatch.setattr(openai_vision.httpx, "AsyncClient", _FakeAsyncClient)


def _adapter() -> OpenAIVisionOCRAdapter:
    return OpenAIVisionOCRAdapter(
        api_key="sk-test", model="gpt-5.4-nano", timeout_seconds=5, min_confidence=0.75
    )


def test_build_vision_adapter_returns_mock_when_flag_set() -> None:
    adapter = _build_vision_adapter(_settings(use_mock_vision=True))
    assert isinstance(adapter, MockVisionOCRAdapter)


def test_build_vision_adapter_returns_openai_when_live() -> None:
    adapter = _build_vision_adapter(_settings())
    assert isinstance(adapter, OpenAIVisionOCRAdapter)


def test_build_vision_adapter_requires_api_key_when_live() -> None:
    with pytest.raises(RuntimeError):
        _build_vision_adapter(_settings(openai_api_key=""))


def _ocr_response(confidence: float) -> _FakeResponse:
    content = '{"raw_ocr_text": "x = 2", "detected_equation": "x = 2", "confidence": %s}' % confidence
    return _FakeResponse(200, {"choices": [{"message": {"content": content}}]})


def test_openai_adapter_marks_low_confidence_for_review(monkeypatch) -> None:
    _patch_openai_post(monkeypatch, _ocr_response(0.4))

    result = asyncio.run(_adapter().recognize(DATA_URL))

    assert result.needs_clarification is True
    assert result.provider == "openai"
    assert result.confidence_source == "model_estimated"


def test_openai_adapter_accepts_confident_result(monkeypatch) -> None:
    _patch_openai_post(monkeypatch, _ocr_response(0.9))

    result = asyncio.run(_adapter().recognize(DATA_URL))

    assert result.needs_clarification is False
    assert result.raw_ocr_text == "x = 2"
    assert result.detected_equation == "x = 2"


def test_openai_adapter_falls_back_to_joined_steps_for_raw_text(monkeypatch) -> None:
    # No raw_ocr_text returned -> raw_ocr_text falls back to the joined steps.
    content = '{"confidence": 0.9, "detected_steps": ["2x + 5 = 13", "2x = 8", "x = 4"]}'
    _patch_openai_post(monkeypatch, _FakeResponse(200, {"choices": [{"message": {"content": content}}]}))

    result = asyncio.run(_adapter().recognize(DATA_URL))

    assert result.raw_ocr_text == "2x + 5 = 13\n2x = 8\nx = 4"
    assert result.detected_steps == ["2x + 5 = 13", "2x = 8", "x = 4"]


def test_openai_adapter_maps_detected_regions(monkeypatch) -> None:
    content = (
        '{"confidence": 0.9, "detected_steps": ["x + 4 = 9"], '
        '"detected_regions": [{"text": "x + 4 = 9", "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.08, "confidence": 0.91}]}'
    )
    _patch_openai_post(monkeypatch, _FakeResponse(200, {"choices": [{"message": {"content": content}}]}))

    result = asyncio.run(_adapter().recognize(DATA_URL))

    assert result.detected_regions[0].text == "x + 4 = 9"
    assert result.detected_regions[0].x == 0.1


def test_openai_adapter_marks_unsupported_final_answer_for_clarification(monkeypatch) -> None:
    content = (
        '{"confidence": 0.95, "detected_steps": ["x + 4 = 9", "x = 5"], '
        '"final_answer": "x = 5"}'
    )
    _patch_openai_post(monkeypatch, _FakeResponse(200, {"choices": [{"message": {"content": content}}]}))

    result = asyncio.run(_adapter().recognize(DATA_URL))

    assert result.needs_clarification is True


def test_openai_adapter_accepts_final_answer_with_visible_steps(monkeypatch) -> None:
    content = (
        '{"confidence": 0.95, "detected_steps": ["x + 4 = 9", "x = 9 - 4", "x = 5"], '
        '"final_answer": "x = 5"}'
    )
    _patch_openai_post(monkeypatch, _FakeResponse(200, {"choices": [{"message": {"content": content}}]}))

    result = asyncio.run(_adapter().recognize(DATA_URL))

    assert result.needs_clarification is False


def _shape_response(text_confidence: float, shape_confidence: float, raw_ocr_text: str = "") -> _FakeResponse:
    content = (
        '{"raw_ocr_text": "%s", "confidence": %s, "detected_shapes": '
        '[{"shape_type": "triangle", "description": "a hand-drawn triangle", "confidence": %s}]}'
        % (raw_ocr_text, text_confidence, shape_confidence)
    )
    return _FakeResponse(200, {"choices": [{"message": {"content": content}}]})


def test_openai_adapter_returns_shapes_with_empty_text(monkeypatch) -> None:
    _patch_openai_post(monkeypatch, _shape_response(text_confidence=0.92, shape_confidence=0.9))

    result = asyncio.run(_adapter().recognize(DATA_URL))

    assert result.raw_ocr_text == ""
    assert len(result.detected_shapes) == 1
    assert result.detected_shapes[0].shape_type == "triangle"
    assert result.needs_clarification is False


def test_openai_adapter_low_shape_confidence_triggers_review(monkeypatch) -> None:
    # Text is confident, but the shape is below threshold.
    _patch_openai_post(monkeypatch, _shape_response(text_confidence=0.95, shape_confidence=0.4))

    result = asyncio.run(_adapter().recognize(DATA_URL))

    assert result.needs_clarification is True


def test_openai_adapter_confident_text_and_shapes_no_review(monkeypatch) -> None:
    _patch_openai_post(
        monkeypatch,
        _shape_response(text_confidence=0.95, shape_confidence=0.9, raw_ocr_text="x = 2"),
    )

    result = asyncio.run(_adapter().recognize(DATA_URL))

    assert result.needs_clarification is False
    assert result.raw_ocr_text == "x = 2"
    assert result.detected_shapes[0].confidence == 0.9


def test_openai_adapter_raises_adapter_error_on_http_error(monkeypatch) -> None:
    _patch_openai_post(monkeypatch, _FakeResponse(500, text="boom"))

    with pytest.raises(AdapterError):
        asyncio.run(_adapter().recognize(DATA_URL))
