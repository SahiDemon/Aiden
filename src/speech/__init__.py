"""Speech module - STT, TTS, and Wake Word Detection"""
from src.speech.stt import get_stt_engine, STTEngine
from src.speech.tts import get_tts_engine, TTSEngine

__all__ = [
    'get_stt_engine',
    'get_tts_engine',
    'STTEngine',
    'TTSEngine',
]










