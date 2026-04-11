from __future__ import annotations

from src.ai.gemini_client import close_gemini_client
from src.ai.groq_client import close_groq_client
from src.ai.ollama_client import close_ollama_client
from src.core.assistant import reset_assistant
from src.speech.stt import reset_stt_engine
from src.speech.tts import reset_tts_engine


async def refresh_runtime_components() -> None:
    await close_gemini_client()
    await close_groq_client()
    await close_ollama_client()
    reset_tts_engine()
    reset_stt_engine()
    reset_assistant()
