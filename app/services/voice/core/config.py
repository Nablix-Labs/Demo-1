import os
from dotenv import load_dotenv

_this_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.join(_this_dir, "..", "..")
_env_path = os.path.join(_project_root, "knowledge-base", "ingestion", ".env")

_loaded = load_dotenv(os.path.abspath(_env_path))
if not _loaded:
    load_dotenv()

DEFAULT_STT_PROVIDER = os.getenv("VOICE_STT_PROVIDER", "mock")
DEFAULT_TTS_PROVIDER = os.getenv("VOICE_TTS_PROVIDER", "mock")

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("NABLIX_OPENAI_API_KEY", "")
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY", "")
INWORLD_API_KEY = os.getenv("INWORLD_API_KEY", "")

STT_LANGUAGE = os.getenv("VOICE_STT_LANGUAGE", "en")
STT_SAMPLE_RATE = int(os.getenv("VOICE_STT_SAMPLE_RATE", "16000"))

TTS_VOICE = os.getenv("VOICE_TTS_VOICE", "nova")
TTS_AUDIO_FORMAT = os.getenv("VOICE_TTS_FORMAT", "mp3")

CONFIDENCE_THRESHOLD = float(os.getenv("VOICE_CONFIDENCE_THRESHOLD", "0.5"))

LATENCY_TARGET_MS = int(os.getenv("VOICE_LATENCY_TARGET_MS", "800"))
