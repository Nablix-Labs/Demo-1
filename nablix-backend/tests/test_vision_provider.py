"""Mock-only tests for vision provider selection and the Mathpix adapter mapping.

No network is touched: provider selection is pure, and the Mathpix adapter's HTTP
call is monkeypatched so these never spend Mathpix credits.
"""

import asyncio

import pytest

from app.adapters import mathpix_vision
from app.adapters.mathpix_vision import MathpixVisionOCRAdapter
from app.adapters.provider import _build_vision_adapter
from app.adapters.vision_ocr import MockVisionOCRAdapter
from app.core.config import Settings
from app.core.exceptions import AdapterError

DATA_URL = "data:image/png;base64,aGVsbG8="


def _settings(**overrides) -> Settings:
    base = {
        "use_mock_vision": False,
        "mathpix_app_id": "app-test",
        "mathpix_app_key": "key-test",
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


def _patch_mathpix_post(
    monkeypatch,
    response: _FakeResponse,
    sent: list[dict] | None = None,
) -> None:
    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, *exc) -> bool:
            return False

        async def post(self, *args, **kwargs) -> _FakeResponse:
            if sent is not None:
                sent.append(kwargs.get("json", {}))
            return response

    monkeypatch.setattr(mathpix_vision.httpx, "AsyncClient", _FakeAsyncClient)


def _mathpix_adapter() -> MathpixVisionOCRAdapter:
    return MathpixVisionOCRAdapter(
        app_id="app-test", app_key="key-test", timeout_seconds=5, min_confidence=0.75
    )


def test_build_vision_adapter_returns_mock_when_flag_set() -> None:
    adapter = _build_vision_adapter(_settings(use_mock_vision=True))
    assert isinstance(adapter, MockVisionOCRAdapter)


def test_build_vision_adapter_returns_mathpix_when_live() -> None:
    adapter = _build_vision_adapter(_settings())
    assert isinstance(adapter, MathpixVisionOCRAdapter)


def test_build_vision_adapter_requires_mathpix_credentials_when_live() -> None:
    with pytest.raises(RuntimeError):
        _build_vision_adapter(_settings(mathpix_app_id="", mathpix_app_key=""))


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


def test_mathpix_adapter_preserves_mathml_data_blocks(monkeypatch) -> None:
    response = _FakeResponse(
        200,
        {
            "text": "x = 5",
            "confidence": 0.99,
            "data": [
                {"type": "mathml", "value": "<math><mi>x</mi><mo>=</mo><mn>5</mn></math>"},
                {"type": "latex", "value": "x=5"},
            ],
        },
    )
    _patch_mathpix_post(monkeypatch, response)

    result = asyncio.run(_mathpix_adapter().recognize(DATA_URL))

    assert result.mathml_blocks == ["<math><mi>x</mi><mo>=</mo><mn>5</mn></math>"]


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


def test_mathpix_adapter_splits_centered_array_and_flags_incomplete_step(monkeypatch) -> None:
    array_text = "\\begin{array}{c}x+4-4= \\\\ x+0=13 \\\\ x=13\\end{array}"
    response = _FakeResponse(
        200,
        {
            "text": array_text,
            "latex_styled": array_text,
            "confidence": 0.998,
            "image_width": 1000,
            "image_height": 500,
            "line_data": [
                {
                    "text": array_text,
                    "cnt": [[100, 50], [800, 50], [800, 350], [100, 350]],
                    "confidence": 0.998,
                    "conversion_output": True,
                },
            ],
        },
    )
    _patch_mathpix_post(monkeypatch, response)

    result = asyncio.run(_mathpix_adapter().recognize(DATA_URL))

    assert result.detected_steps == ["x+4-4=", "x+0=13", "x=13"]
    assert result.final_answer == "x=13"
    assert len(result.detected_regions) == 3
    assert [region.text for region in result.detected_regions] == result.detected_steps
    assert result.needs_clarification is True


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
    # Retargeted from image_no_content, which is no longer an adapter failure:
    # see test_mathpix_adapter_reads_nothing_when_the_image_has_no_content.
    _patch_mathpix_post(
        monkeypatch,
        _FakeResponse(
            200,
            {
                "error": "Invalid credentials",
                "error_info": {"id": "http_unauthorized", "message": "Invalid credentials"},
            },
        ),
    )

    with pytest.raises(AdapterError):
        asyncio.run(_mathpix_adapter().recognize(DATA_URL))


def test_mathpix_adapter_reads_nothing_when_the_image_has_no_content(monkeypatch) -> None:
    """A canvas OCR cannot read is a tutoring outcome, not an adapter outage.

    Mathpix answers HTTP 200 with this body for a doodle, a stray mark, or a
    blank page. Raising here turned every one of those into a 503 that failed
    the student's turn (Manav, 26 Aug: ten-image control matrix — size,
    transparency and encoding all ruled out, legibility the only variable).
    """

    _patch_mathpix_post(
        monkeypatch,
        _FakeResponse(
            200,
            {
                "error": "Content not found",
                "error_info": {"id": "image_no_content", "message": "Content not found"},
            },
        ),
    )

    result = asyncio.run(_mathpix_adapter().recognize(DATA_URL))

    assert result.needs_clarification is True
    assert result.confidence == 0.0
    assert result.raw_ocr_text == ""
    assert result.detected_steps == []
    assert result.detected_regions == []
    assert result.final_answer is None
    assert result.provider == "mathpix"


def test_mathpix_adapter_requests_and_maps_per_symbol_word_boxes(monkeypatch) -> None:
    """Symbol geometry has to come from OCR.

    Deriving it from student ink alone cannot localize anything on a
    snapshot-only submission, and mis-localizes whenever the stroke count does
    not match the symbol count.
    """

    sent: list[dict] = []
    response = _FakeResponse(
        200,
        {
            "text": "c-4",
            "confidence": 0.95,
            "image_width": 1000,
            "image_height": 500,
            "line_data": [
                {
                    "text": "c-4",
                    "cnt": [[100, 150], [500, 150], [500, 190], [100, 190]],
                    "confidence": 0.95,
                    "conversion_output": True,
                }
            ],
            "word_data": [
                {"text": "c", "cnt": [[100, 150], [150, 150], [150, 190], [100, 190]], "confidence": 0.95},
                {"text": "-", "cnt": [[200, 165], [240, 165], [240, 175], [200, 175]], "confidence": 0.94},
                {"text": "4", "cnt": [[300, 150], [350, 150], [350, 190], [300, 190]], "confidence": 0.96},
            ],
        },
    )
    _patch_mathpix_post(monkeypatch, response, sent)

    result = asyncio.run(_mathpix_adapter().recognize(DATA_URL))

    assert "include_word_data" not in sent[0]
    assert [region.text for region in result.word_regions] == ["c", "-", "4"]
    minus = result.word_regions[1]
    assert minus.x == 0.2
    assert minus.w == 0.04
    assert minus.w < result.detected_regions[0].w


def test_mathpix_adapter_returns_no_word_regions_without_word_data(monkeypatch) -> None:
    response = _FakeResponse(200, {"text": "x = 5", "confidence": 0.99})
    _patch_mathpix_post(monkeypatch, response)

    assert asyncio.run(_mathpix_adapter().recognize(DATA_URL)).word_regions == []
