from __future__ import annotations

from typing import Any, Dict

from dotenv import set_key

from src.utils.config import Settings


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _string(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _settings_to_env(settings: Settings) -> Dict[str, str]:
    return {
        "APP_NAME": _string(settings.app.name),
        "USER_NAME": _string(settings.app.user_name),
        "WAKE_WORD": _string(settings.app.wake_word),
        "HOTKEY": _string(settings.app.hotkey),
        "TOGGLE_HOTKEY": _string(settings.app.toggle_hotkey),
        "STOP_LISTENING_HOTKEY": _string(settings.app.stop_listening_hotkey),
        "DEBUG": _bool(settings.app.debug),
        "APP_TRAY_SHOW_RESTART": _bool(settings.app.tray_show_restart),
        "APP_ENABLE_ENHANCED_RESPONSES": _bool(settings.app.enable_enhanced_responses),
        "LLM_PROVIDER": _string(settings.app.llm_provider),
        "GEMINI_API_KEY": _string(settings.gemini.api_key),
        "GEMINI_API_KEY_1": _string(settings.gemini.api_key_1),
        "GEMINI_API_KEY_2": _string(settings.gemini.api_key_2),
        "GEMINI_API_KEY_3": _string(settings.gemini.api_key_3),
        "GEMINI_MODEL": _string(settings.gemini.model),
        "GEMINI_MAX_TOKENS": _string(settings.gemini.max_tokens),
        "GEMINI_TEMPERATURE": _string(settings.gemini.temperature),
        "GEMINI_AUTO_KEY_ROTATION": _bool(settings.gemini.auto_key_rotation),
        "GROQ_API_KEY": _string(settings.groq.api_key),
        "GROQ_BASE_URL": _string(settings.groq.base_url),
        "GROQ_MODEL": _string(settings.groq.model),
        "GROQ_MAX_TOKENS": _string(settings.groq.max_tokens),
        "GROQ_TEMPERATURE": _string(settings.groq.temperature),
        "OLLAMA_BASE_URL": _string(settings.ollama.base_url),
        "OLLAMA_MODEL": _string(settings.ollama.model),
        "OLLAMA_MAX_TOKENS": _string(settings.ollama.max_tokens),
        "OLLAMA_TEMPERATURE": _string(settings.ollama.temperature),
        "OLLAMA_TIMEOUT": _string(settings.ollama.timeout),
        "API_HOST": _string(settings.api.host),
        "API_PORT": _string(settings.api.port),
        "API_RELOAD": _bool(settings.api.reload),
        "NEON_DATABASE_URL": _string(settings.database.database_url),
        "NEON_POOL_SIZE": _string(settings.database.pool_size),
        "NEON_MAX_OVERFLOW": _string(settings.database.max_overflow),
        "NEON_POOL_TIMEOUT": _string(settings.database.pool_timeout),
        "REDIS_URL": _string(settings.redis.url),
        "REDIS_DECODE_RESPONSES": _bool(settings.redis.decode_responses),
        "REDIS_SOCKET_TIMEOUT": _string(settings.redis.socket_timeout),
        "REDIS_SOCKET_CONNECT_TIMEOUT": _string(settings.redis.socket_connect_timeout),
        "SPEECH_TTS_PROVIDER": _string(settings.speech.tts_provider),
        "SPEECH_TTS_VOICE": _string(settings.speech.tts_voice),
        "SPEECH_TTS_RATE": _string(settings.speech.tts_rate),
        "SPEECH_GOOGLE_TTS_CREDENTIALS_PATH": _string(settings.speech.google_tts_credentials_path),
        "SPEECH_GOOGLE_TTS_VOICE": _string(settings.speech.google_tts_voice),
        "SPEECH_GOOGLE_TTS_PITCH": _string(settings.speech.google_tts_pitch),
        "SPEECH_GOOGLE_TTS_SPEAKING_RATE": _string(settings.speech.google_tts_speaking_rate),
        "SPEECH_STT_LANGUAGE": _string(settings.speech.stt_language),
        "SPEECH_STT_TIMEOUT": _string(settings.speech.stt_timeout),
        "SPEECH_STT_PAUSE_THRESHOLD": _string(settings.speech.stt_pause_threshold),
        "SPEECH_STT_NON_SPEAKING_DURATION": _string(settings.speech.stt_non_speaking_duration),
        "SPEECH_STT_DEVICE_INDEX": _string(settings.speech.stt_device_index),
        "SPEECH_STT_ENERGY_THRESHOLD": _string(settings.speech.stt_energy_threshold),
        "SPEECH_PENDING_CLARIFICATION_GRACE_SECONDS": _string(settings.speech.pending_clarification_grace_seconds),
        "SPEECH_VOSK_MODEL_PATH": _string(settings.speech.vosk_model_path),
        "SPEECH_PORCUPINE_ACCESS_KEY": _string(settings.speech.porcupine_access_key),
        "SPEECH_PORCUPINE_MODEL_PATH": _string(settings.speech.porcupine_model_path),
        "SPEECH_PORCUPINE_SENSITIVITY": _string(settings.speech.porcupine_sensitivity),
        "SPEECH_PORCUPINE_MIN_ENERGY": _string(settings.speech.porcupine_min_energy),
        "SPEECH_PORCUPINE_DEBOUNCE_SECONDS": _string(settings.speech.porcupine_debounce_seconds),
        "SPEECH_PORCUPINE_CONFIRMATION_WINDOW": _string(settings.speech.porcupine_confirmation_window),
        "SPEECH_USE_PORCUPINE": _bool(settings.speech.use_porcupine),
        "ESP32_ENABLED": _bool(settings.esp32.enabled),
        "ESP32_IP_ADDRESS": _string(settings.esp32.ip_address),
        "ESP32_TIMEOUT": _string(settings.esp32.timeout),
        "ESP32_RETRY_ATTEMPTS": _string(settings.esp32.retry_attempts),
        "SPOTIFY_ENABLED": _bool(settings.spotify.enabled),
        "SPOTIFY_CLIENT_ID": _string(settings.spotify.client_id),
        "SPOTIFY_CLIENT_SECRET": _string(settings.spotify.client_secret),
        "SPOTIFY_REFRESH_TOKEN": _string(settings.spotify.refresh_token),
        "SPOTIFY_DEFAULT_DEVICE_NAME": _string(settings.spotify.default_device_name),
        "ENABLE_CACHING": _bool(settings.cache.enable_caching),
        "CACHE_TTL_CONTEXT": _string(settings.cache.ttl_context),
        "CACHE_TTL_APP_PATHS": _string(settings.cache.ttl_app_paths),
        "CACHE_TTL_LLM_RESPONSE": _string(settings.cache.ttl_llm_response),
        "CACHE_TTL_TTS_AUDIO": _string(settings.cache.ttl_tts_audio),
        "UPS_ENABLED": _bool(settings.ups.enabled),
        "UPS_INFO_LOG_PATH": _string(settings.ups.info_log_path),
        "UPS_ALERT_THRESHOLD": _string(settings.ups.alert_threshold),
        "UPS_CRITICAL_THRESHOLD": _string(settings.ups.critical_threshold),
        "UPS_SHUTDOWN_THRESHOLD": _string(settings.ups.shutdown_threshold),
        "UPS_POLLING_INTERVAL": _string(settings.ups.polling_interval),
        "UPS_SHUTDOWN_TIMEOUT": _string(settings.ups.shutdown_timeout),
    }


def sync_settings_to_env(settings: Settings, env_path: str = ".env") -> None:
    for key, value in _settings_to_env(settings).items():
        set_key(env_path, key, value, quote_mode="never")
