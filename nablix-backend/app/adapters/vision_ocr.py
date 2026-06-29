"""Mock vision OCR adapter.

Canvas tests and local development use this deterministic adapter when
`NABLIX_USE_MOCK_VISION=true`. The response mirrors the normalized
`VisionOCRResult` contract that live OCR providers must return.
"""

from app.models.adapters import VisionOCRResult


class MockVisionOCRAdapter:
    """Return a stable handwriting-recognition result without external calls."""

    async def recognize(self, snapshot_data_url: str) -> VisionOCRResult:
        """Recognize a snapshot using fixed sample math work."""

        return VisionOCRResult(
            raw_ocr_text="x + 4 = 9, x = 9 - 4, x = 5",
            detected_equation="x + 4 = 9",
            detected_steps=["x + 4 = 9", "x = 9 - 4", "x = 5"],
            final_answer="x = 5",
            confidence=0.95,
            needs_clarification=False,
            latex="x + 4 = 9",
            detected_shapes=[],
            confidence_source="mock",
            provider="mock",
        )
