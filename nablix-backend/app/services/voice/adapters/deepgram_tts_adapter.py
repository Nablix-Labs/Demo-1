import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from adapter import TTSAdapter, SpeechResult, register_tts_adapter
import config as voice_config

class DeepgramTTSAdapter(TTSAdapter):

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or voice_config.DEEPGRAM_API_KEY
        if not self.api_key:
            raise ValueError(
                "Deepgram API key not found. "
                "Sign up at console.deepgram.com and set DEEPGRAM_API_KEY in .env"
            )

    async def generate_speech(
        self,
        text: str,
        voice: str | None = None,
        audio_format: str = "mp3",
    ) -> SpeechResult:
        raise NotImplementedError(
            "Deepgram TTS adapter not yet implemented. "
            "Add your Deepgram API key and complete the implementation."
        )

    def get_provider_name(self) -> str:
        return "deepgram_aura2"

if voice_config.DEEPGRAM_API_KEY:
    register_tts_adapter("deepgram", DeepgramTTSAdapter)
