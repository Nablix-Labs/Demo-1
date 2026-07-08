"""Mock-only tests for vision provider selection and the OpenAI adapter mapping.

No network is touched: provider selection is pure, and the OpenAI adapter's HTTP
call is monkeypatched so these never spend OpenAI credits.
"""

import asyncio

import pytest

from app.adapters import mathpix_vision, openai_vision
from app.adapters.mathpix_vision import MathpixVisionOCRAdapter
from app.adapters.openai_vision import OpenAIVisionOCRAdapter
from app.adapters.provider import _build_vision_adapter
from app.adapters.vision_ocr import MockVisionOCRAdapter
from app.core.config import Settings
from app.core.exceptions import AdapterError

DATA_URL = "data:image/png;base64,aGVsbG8="


def _settings(**overrides) -> Settings:
    base = {
        "use_mock_vision": False,
        "ocr_provider": "openai",
        "openai_api_key": "sk-test",
        "mathpix_app_id": "",
        "mathpix_app_key": "",
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


def _patch_mathpix_post(monkeypatch, response: _FakeResponse) -> None:
    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *exc) -> bool:
            return False

        async def post(self, *args, **kwargs) -> _FakeResponse:
            return response

    monkeypatch.setattr(mathpix_vision.httpx, "AsyncClient", _FakeAsyncClient)


def _adapter() -> OpenAIVisionOCRAdapter:
    return OpenAIVisionOCRAdapter(
        api_key="sk-test", model="gpt-5.4-nano", timeout_seconds=5, min_confidence=0.75
    )


def _mathpix_adapter() -> MathpixVisionOCRAdapter:
    return MathpixVisionOCRAdapter(
        app_id="app-test", app_key="key-test", timeout_seconds=5, min_confidence=0.75
    )


def test_build_vision_adapter_returns_mock_when_flag_set() -> None:
    adapter = _build_vision_adapter(_settings(use_mock_vision=True))
    assert isinstance(adapter, MockVisionOCRAdapter)


def test_build_vision_adapter_returns_openai_when_live() -> None:
    adapter = _build_vision_adapter(_settings())
    assert isinstance(adapter, OpenAIVisionOCRAdapter)


def test_build_vision_adapter_returns_mathpix_when_selected() -> None:
    adapter = _build_vision_adapter(
        _settings(ocr_provider="mathpix", mathpix_app_id="app-test", mathpix_app_key="key-test")
    )
    assert isinstance(adapter, MathpixVisionOCRAdapter)


def test_build_vision_adapter_requires_api_key_when_live() -> None:
    with pytest.raises(RuntimeError):
        _build_vision_adapter(_settings(openai_api_key=""))


def test_build_vision_adapter_requires_mathpix_credentials_when_selected() -> None:
    with pytest.raises(RuntimeError):
        _build_vision_adapter(_settings(ocr_provider="mathpix"))


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


def test_mathpix_adapter_maps_line_data_regions(monkeypatch) -> None:
    response = _FakeResponse(
        200,
        {
            "text": "x + 4 = 9\nx = 5",
            "latex_styled": "x + 4 = 9\\\\x = 5",
            "confidence": 0.91,
            "image_width": 1000,
            "image_height": 500,
            "line_data": [
                {
                    "text": "unsupported diagram",
                    "cnt": [[10, 10], [30, 10], [30, 30], [10, 30]],
                    "confidence": 0.99,
                    "conversion_output": False,
                },
                {
                    "text": "x + 4 = 9",
                    "cnt": [[100, 50], [500, 50], [500, 100], [100, 100]],
                    "confidence": 0.93,
                    "conversion_output": True,
                },
                {
                    "text": "x = 5",
                    "cnt": [[120, 150], [350, 150], [350, 190], [120, 190]],
                    "confidence": 0.88,
                    "conversion_output": True,
                },
            ],
        },
    )
    _patch_mathpix_post(monkeypatch, response)

    result = asyncio.run(_mathpix_adapter().recognize(DATA_URL))

    assert result.provider == "mathpix"
    assert result.confidence_source == "ocr_native"
    assert result.detected_steps == ["x + 4 = 9", "x = 5"]
    assert result.detected_equation == "x + 4 = 9"
    assert result.final_answer == "x = 5"
    assert result.latex == "x + 4 = 9\\\\x = 5"
    assert result.detected_regions[0].x == 0.1
    assert result.detected_regions[0].y == 0.1
    assert result.detected_regions[0].w == 0.4
    assert result.detected_regions[0].h == 0.1
    assert result.detected_regions[0].confidence == 0.93


def test_mathpix_adapter_splits_array_output_into_step_regions(monkeypatch) -> None:
    response = _FakeResponse(
        200,
        {
            "text": "\\( \\begin{array}{l}x=9-5 \\\\ x=4\\end{array} \\)",
            "latex_styled": "\\begin{array}{l}\nx=9-5 \\\\\nx=4\n\\end{array}",
            "confidence": 1.0,
            "image_width": 1000,
            "image_height": 500,
            "line_data": [
                {
                    "text": "\\( \\begin{array}{l}x=9-5 \\\\ x=4\\end{array} \\)",
                    "cnt": [[100, 50], [500, 50], [500, 250], [100, 250]],
                    "confidence": 1.0,
                    "conversion_output": True,
                },
            ],
        },
    )
    _patch_mathpix_post(monkeypatch, response)

    result = asyncio.run(_mathpix_adapter().recognize(DATA_URL))

    assert result.raw_ocr_text == "x=9-5\nx=4"
    assert result.detected_steps == ["x=9-5", "x=4"]
    assert result.detected_equation == "x=9-5"
    assert result.final_answer == "x=4"
    assert len(result.detected_regions) == 2
    assert result.detected_regions[0].text == "x=9-5"
    assert result.detected_regions[0].y == 0.1
    assert result.detected_regions[0].h == 0.2
    assert result.detected_regions[1].text == "x=4"
    assert result.detected_regions[1].y == pytest.approx(0.3)
    assert result.detected_regions[1].h == 0.2


def test_mathpix_adapter_marks_missing_confidence_for_review(monkeypatch) -> None:
    _patch_mathpix_post(
        monkeypatch,
        _FakeResponse(200, {"text": "x = 5", "image_width": 1000, "image_height": 500}),
    )

    result = asyncio.run(_mathpix_adapter().recognize(DATA_URL))

    assert result.confidence == 0.0
    assert result.needs_clarification is True


def test_mathpix_adapter_uses_confidence_rate_when_confidence_is_missing(monkeypatch) -> None:
    _patch_mathpix_post(
        monkeypatch,
        _FakeResponse(200, {"text": "x = 5", "confidence_rate": 0.87}),
    )

    result = asyncio.run(_mathpix_adapter().recognize(DATA_URL))

    assert result.confidence == 0.87
    assert result.needs_clarification is False


def test_mathpix_adapter_raises_when_line_data_has_no_image_size(monkeypatch) -> None:
    _patch_mathpix_post(
        monkeypatch,
        _FakeResponse(
            200,
            {
                "text": "x = 5",
                "confidence": 0.9,
                "line_data": [{"text": "x = 5", "cnt": [[10, 10], [50, 10], [50, 30], [10, 30]]}],
            },
        ),
    )

    with pytest.raises(AdapterError):
        asyncio.run(_mathpix_adapter().recognize(DATA_URL))


def test_mathpix_adapter_raises_when_image_size_is_zero(monkeypatch) -> None:
    _patch_mathpix_post(
        monkeypatch,
        _FakeResponse(
            200,
            {
                "text": "x = 5",
                "confidence": 0.9,
                "image_width": 0,
                "image_height": 500,
                "line_data": [{"text": "x = 5", "cnt": [[10, 10], [50, 10], [50, 30], [10, 30]]}],
            },
        ),
    )

    with pytest.raises(AdapterError):
        asyncio.run(_mathpix_adapter().recognize(DATA_URL))


def test_mathpix_adapter_raises_adapter_error_on_http_error(monkeypatch) -> None:
    _patch_mathpix_post(monkeypatch, _FakeResponse(500, text="boom"))

    with pytest.raises(AdapterError):
        asyncio.run(_mathpix_adapter().recognize(DATA_URL))


def test_mathpix_adapter_raises_adapter_error_on_mathpix_error(monkeypatch) -> None:
    _patch_mathpix_post(monkeypatch, _FakeResponse(200, {"error": "image_no_content"}))

    with pytest.raises(AdapterError):
        asyncio.run(_mathpix_adapter().recognize(DATA_URL))
