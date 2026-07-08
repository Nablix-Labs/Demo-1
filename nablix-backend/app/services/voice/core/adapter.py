from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache

@dataclass
class TranscriptionResult:
    transcript: str
    confidence: float
    language: str
    latency_ms: int
    provider: str

@dataclass
class SpeechResult:
    audio_data: bytes | str
    audio_format: str
    duration_seconds: float
    latency_ms: int
    provider: str

class STTAdapter(ABC):

    @abstractmethod
    async def transcribe_audio(
        self,
        audio_data: bytes | str,
        language: str = "en",
        audio_format: str = "wav",
        sample_rate: int = 16000,
    ) -> TranscriptionResult:
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        pass

class TTSAdapter(ABC):

    @abstractmethod
    async def generate_speech(
        self,
        text: str,
        voice: str | None = None,
        audio_format: str = "mp3",
    ) -> SpeechResult:
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        pass

_stt_adapters: dict[str, type[STTAdapter]] = {}
_tts_adapters: dict[str, type[TTSAdapter]] = {}

def register_stt_adapter(name: str, adapter_class: type[STTAdapter]):
    _stt_adapters[name] = adapter_class

def register_tts_adapter(name: str, adapter_class: type[TTSAdapter]):
    _tts_adapters[name] = adapter_class

# Adapters (and their HTTP clients) are reused across requests; building one
# per call costs a fresh TCP+TLS handshake and defeats startup pre-warming.
@lru_cache(maxsize=None)
def get_stt_adapter(name: str) -> STTAdapter:
    if name not in _stt_adapters:
        available = list(_stt_adapters.keys())
        raise KeyError(
            f"STT adapter '{name}' not found. Available: {available}"
        )
    return _stt_adapters[name]()

@lru_cache(maxsize=None)
def get_tts_adapter(name: str) -> TTSAdapter:
    if name not in _tts_adapters:
        available = list(_tts_adapters.keys())
        raise KeyError(
            f"TTS adapter '{name}' not found. Available: {available}"
        )
    return _tts_adapters[name]()
