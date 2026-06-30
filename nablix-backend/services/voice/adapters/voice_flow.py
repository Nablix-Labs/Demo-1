import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from voice_flow import (
    process_voice_input,
    get_or_create_session,
    mock_tutor_evaluate,
    mock_math_normalize,
)

from contracts import (
    VoiceTranscriptRequest,
    VoiceTranscriptResponse,
    VoiceStatus,
    FallbackMode,
)

import config

if config.OPENAI_API_KEY:
    import openai_stt_adapter
    import openai_tts_adapter

if config.DEEPGRAM_API_KEY:
    import deepgram_stt_adapter
    import deepgram_tts_adapter

def print_adapter_status():
    from adapter import _stt_adapters, _tts_adapters

    print("\n--- Adapter Status ---")
    print(f"  STT adapters registered: {list(_stt_adapters.keys())}")
    print(f"  TTS adapters registered: {list(_tts_adapters.keys())}")
    print(f"  Active STT provider:     {config.DEFAULT_STT_PROVIDER}")
    print(f"  Active TTS provider:     {config.DEFAULT_TTS_PROVIDER}")
    print(f"  OpenAI API key set:      {'Yes' if config.OPENAI_API_KEY else 'No'}")
    print(f"  Deepgram API key set:    {'Yes' if config.DEEPGRAM_API_KEY else 'No'}")
    print("----------------------\n")

if __name__ == "__main__":
    print_adapter_status()
