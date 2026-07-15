"""Protocol interfaces for downstream service adapters.

Each adapter exposes a service-facing method named after the domain action
(`retrieve`, `assess`, `evaluate`, `transcribe`, etc.). HTTP services should
call those domain methods, not concrete classes.

Adapters that talk to swappable downstream services also expose the common
`call`, `parse_response`, and `handle_error` shape. `call` decides whether to
return mock data or call a live endpoint, `parse_response` converts raw JSON
into typed DTOs, and `handle_error` keeps adapter failures explicit.

These are Protocols, not abstract base classes. A mock or real implementation
only has to match the method signatures; it does not need to inherit from the
protocol. That keeps the API layer insulated from downstream implementation
changes.
"""

from typing import NoReturn, Protocol

from app.core.exceptions import AdapterError
from app.models.adapters import (
    AdapterContext,
    RAGResult,
    SafetyCheckResult,
    StudentModelEvent,
    StudentModelResult,
    TutorEngineRequest,
    TutorResult,
    VisionOCRResult,
    VoiceResult,
)


class RAGServiceAdapter(Protocol):
    """Retrieves curriculum context relevant to the current student turn."""

    async def call(
        self,
        request: AdapterContext,
        *,
        error_type: str | None,
        hint_level: int | None,
    ) -> RAGResult: ...
    def parse_response(self, response: dict[str, object]) -> RAGResult: ...
    def handle_error(self, error: AdapterError) -> NoReturn: ...
    async def retrieve(
        self,
        context: AdapterContext,
        *,
        error_type: str | None,
        hint_level: int | None,
    ) -> RAGResult: ...


class StudentModelAdapter(Protocol):
    """Reads and updates the learner-state estimate for a session."""

    async def call(self, request: AdapterContext) -> StudentModelResult: ...
    def parse_response(self, response: dict[str, object]) -> StudentModelResult: ...
    def handle_error(self, error: AdapterError) -> NoReturn: ...
    async def assess(self, context: AdapterContext) -> StudentModelResult: ...
    async def update_from_event(
        self,
        event: StudentModelEvent,
        context: AdapterContext,
        access_token: str,
    ) -> StudentModelResult: ...


class TutorEngineAdapter(Protocol):
    """Produces tutoring feedback from context, retrieval, and student state."""

    async def call(self, request: TutorEngineRequest) -> TutorResult: ...
    def parse_response(self, response: dict[str, object]) -> TutorResult: ...
    def handle_error(self, error: AdapterError) -> NoReturn: ...
    async def evaluate(
        self,
        context: AdapterContext,
        rag: RAGResult,
        student: StudentModelResult,
    ) -> TutorResult: ...


class VoiceServiceAdapter(Protocol):
    """Transcribes an audio reference into text plus confidence metadata."""

    async def call(self, request: str) -> VoiceResult: ...
    def parse_response(self, response: dict[str, object]) -> VoiceResult: ...
    def handle_error(self, error: AdapterError) -> NoReturn: ...
    async def transcribe(self, audio_reference: str) -> VoiceResult: ...


class VisionOCRAdapter(Protocol):
    """Recognizes handwritten math and geometry from a canvas snapshot."""

    async def recognize(self, snapshot_data_url: str) -> VisionOCRResult: ...


class SafetyServiceAdapter(Protocol):
    """Checks a student turn before it reaches the tutor pipeline."""

    async def check(self, context: AdapterContext) -> SafetyCheckResult: ...
