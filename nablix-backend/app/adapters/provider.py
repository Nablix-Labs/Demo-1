"""Factory for the adapter set used by application services.

Services ask `get_adapters()` for an `AdapterSet` and depend only on the
protocol types in `app.adapters.base` - never on a concrete class. Each concrete
service adapter reads its matching `use_mock_*` flag and decides whether to
return mock data or call the configured downstream service URL.

This module should stay boring: it wires settings into adapters. Request
orchestration belongs in `app.services`, and HTTP/provider-specific behavior
belongs in the concrete adapter modules.
"""

from dataclasses import dataclass

from app.adapters.base import (
    RAGServiceAdapter,
    SafetyServiceAdapter,
    StudentModelAdapter,
    TutorEngineAdapter,
    VisionOCRAdapter,
    VoiceServiceAdapter,
)
from app.adapters.mathpix_vision import MathpixVisionOCRAdapter
from app.adapters.openai_vision import OpenAIVisionOCRAdapter
from app.adapters.rag_service import RAGServiceAdapterClient
from app.adapters.safety_service import MockSafetyServiceAdapter
from app.adapters.student_model import StudentModelServiceAdapter
from app.adapters.tutor_engine import TutorEngineServiceAdapter
from app.adapters.vision_ocr import MockVisionOCRAdapter
from app.adapters.voice_service import VoiceServiceAdapterClient
from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class AdapterSet:
    """The active set of adapters, typed by interface rather than implementation."""

    tutor: TutorEngineAdapter
    rag: RAGServiceAdapter
    student_model: StudentModelAdapter
    voice: VoiceServiceAdapter
    vision: VisionOCRAdapter
    safety: SafetyServiceAdapter


def _build_vision_adapter(settings: Settings) -> VisionOCRAdapter:
    """Build the configured OCR adapter."""

    if settings.use_mock_vision:
        return MockVisionOCRAdapter()

    if settings.ocr_provider == "mathpix":
        if not settings.mathpix_app_id or not settings.mathpix_app_key:
            raise RuntimeError(
                "Vision OCR is live with Mathpix but "
                "NABLIX_MATHPIX_APP_ID and NABLIX_MATHPIX_APP_KEY are not set."
            )
        return MathpixVisionOCRAdapter(
            app_id=settings.mathpix_app_id,
            app_key=settings.mathpix_app_key,
            timeout_seconds=settings.adapter_request_timeout_seconds,
            min_confidence=settings.min_ocr_confidence_threshold,
        )

    if not settings.openai_api_key:
        raise RuntimeError(
            "Vision OCR is live (NABLIX_USE_MOCK_VISION=false) but "
            "NABLIX_OPENAI_API_KEY is not set."
        )

    return OpenAIVisionOCRAdapter(
        api_key=settings.openai_api_key,
        model=settings.openai_vision_model,
        timeout_seconds=settings.openai_request_timeout_seconds,
        min_confidence=settings.min_ocr_confidence_threshold,
    )


def get_adapters() -> AdapterSet:
    """Return adapters for the current request using the active settings."""

    settings = get_settings()
    return AdapterSet(
        tutor=TutorEngineServiceAdapter(settings),
        rag=RAGServiceAdapterClient(settings),
        student_model=StudentModelServiceAdapter(settings),
        voice=VoiceServiceAdapterClient(settings),
        vision=_build_vision_adapter(settings),
        safety=MockSafetyServiceAdapter(),
    )
