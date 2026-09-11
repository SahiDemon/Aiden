"""
Configuration management for Aiden.

This module loads defaults from `.env`, then applies optional in-memory
overrides managed by the settings service. Runtime components can call
`reload_settings()` after overrides change to rebuild their cached config.
"""
from __future__ import annotations

import sys
import os
from pathlib import Path
from copy import deepcopy
from typing import Any, Dict, Optional

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_env_file() -> str:
    """Return the absolute path to the .env file.

    When running as a PyInstaller frozen EXE the CWD is wherever the user
    launched the process from (e.g. Desktop, Start Menu shortcut).  We
    therefore resolve .env relative to the EXE's own directory so that
    the correct .env is always loaded regardless of the CWD.

    When running from source the .env sits in the project root, which is
    two levels above this file (src/utils/config.py → src/ → project root).
    """
    if getattr(sys, "frozen", False):
        # PyInstaller EXE: .env is next to the EXE
        return str(Path(sys.executable).parent / ".env")
    # Development: project root
    return str(Path(__file__).resolve().parents[2] / ".env")


_ENV_FILE = _resolve_env_file()


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class GeminiConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GEMINI_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str = Field(default="")
    api_key_1: str = Field(default="")
    api_key_2: str = Field(default="")
    api_key_3: str = Field(default="")
    model: str = Field(default="gemini-2.5-flash-lite")
    max_tokens: int = Field(default=2000)
    temperature: float = Field(default=0.3)
    auto_key_rotation: bool = Field(default=True)


class GroqConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GROQ_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str = Field(default="")
    base_url: str = Field(default="https://api.groq.com/openai/v1/chat/completions")
    model: str = Field(default="llama-3.1-8b-instant")
    max_tokens: int = Field(default=2000)
    temperature: float = Field(default=0.7)


class OllamaConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OLLAMA_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = Field(default="http://localhost:11434")
    model: str = Field(default="llama3.2")
    max_tokens: int = Field(default=2000)
    temperature: float = Field(default=0.3)
    timeout: float = Field(default=30.0)


class DatabaseConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NEON_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(default="")
    pool_size: int = Field(default=5)
    max_overflow: int = Field(default=10)
    pool_timeout: int = Field(default=30)


class RedisConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = Field(default="")
    decode_responses: bool = Field(default=True)
    socket_timeout: int = Field(default=5)
    socket_connect_timeout: int = Field(default=5)


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    name: str = Field(default="Aiden")
    user_name: str = Field(default="Sir", validation_alias=AliasChoices("user_name", "USER_NAME"))
    wake_word: str = Field(
        default="aiden",
        validation_alias=AliasChoices("wake_word", "WAKE_WORD", "APP_WAKE_WORD"),
    )
    hotkey: str = Field(default="ctrl+shift+space", validation_alias=AliasChoices("hotkey", "HOTKEY"))
    toggle_hotkey: str = Field(default="ctrl+shift+w", validation_alias=AliasChoices("toggle_hotkey", "TOGGLE_HOTKEY"))
    stop_listening_hotkey: str = Field(
        default="ctrl+shift+/",
        validation_alias=AliasChoices("stop_listening_hotkey", "STOP_LISTENING_HOTKEY"),
    )
    debug: bool = Field(default=False, validation_alias=AliasChoices("debug", "DEBUG"))
    tray_show_restart: bool = Field(
        default=False,
        validation_alias=AliasChoices("tray_show_restart", "TRAY_SHOW_RESTART", "APP_TRAY_SHOW_RESTART"),
    )
    enable_enhanced_responses: bool = Field(
        default=True, validation_alias=AliasChoices("enable_enhanced_responses", "ENABLE_ENHANCED_RESPONSES")
    )
    llm_provider: str = Field(default="gemini", validation_alias=AliasChoices("llm_provider", "LLM_PROVIDER"))
    settings_encryption_key: str = Field(default="", validation_alias=AliasChoices("settings_encryption_key", "SETTINGS_ENCRYPTION_KEY"))
    media_idle_shutdown_enabled: bool = Field(
        default=False, validation_alias=AliasChoices("media_idle_shutdown_enabled", "MEDIA_IDLE_SHUTDOWN_ENABLED")
    )
    media_idle_timeout_minutes: int = Field(
        default=15, validation_alias=AliasChoices("media_idle_timeout_minutes", "MEDIA_IDLE_TIMEOUT_MINUTES")
    )
    jellyfin_url: str = Field(
        default="http://localhost:8096", validation_alias=AliasChoices("jellyfin_url", "JELLYFIN_URL")
    )
    jellyfin_api_key: str = Field(
        default="", validation_alias=AliasChoices("jellyfin_api_key", "JELLYFIN_API_KEY")
    )
    cloudflare_tunnel_token: str = Field(
        default="",
        validation_alias=AliasChoices("cloudflare_tunnel_token", "CLOUDFLARE_TUNNEL_TOKEN"),
    )


    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug_value(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", ""}:
                return False
        return bool(value)

    @field_validator("hotkey", "toggle_hotkey", "stop_listening_hotkey", mode="before")
    @classmethod
    def normalize_hotkey_value(cls, value: Any, info) -> Any:
        if not isinstance(value, str):
            return value

        normalized = value.strip()
        if info.field_name == "hotkey" and normalized == "":
            return "ctrl+shift+space"
        if info.field_name == "toggle_hotkey" and normalized == "":
            return "ctrl+."
        if info.field_name == "stop_listening_hotkey" and normalized == "":
            return "ctrl+shift+/"
        return normalized


class APIConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="API_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=5000)
    reload: bool = Field(default=False)


class ESP32Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ESP32_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = Field(default=True)
    ip_address: str = Field(default="192.168.1.180")
    timeout: int = Field(default=5)
    retry_attempts: int = Field(default=3)


class SpeechConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SPEECH_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    tts_provider: str = Field(default="edge")
    tts_voice: str = Field(default="en-US-AvaNeural")
    tts_rate: float = Field(default=1.2)
    google_tts_credentials_path: str = Field(default="")
    google_tts_voice: str = Field(default="en-US-Chirp-HD-F")
    google_tts_pitch: float = Field(default=0.0)
    google_tts_speaking_rate: float = Field(default=1.0)
    stt_language: str = Field(default="en-US")
    stt_timeout: int = Field(default=5)
    # How long silence must last before speech is considered done.
    stt_pause_threshold: float = Field(default=0.9)
    # Keep a short trailing non-speaking buffer without cutting natural pauses.
    stt_non_speaking_duration: float = Field(default=0.7)
    stt_device_index: Optional[int] = Field(default=None)
    input_device_name: str = Field(default="USB PnP Audio Device")
    stt_energy_threshold: int = Field(default=600)
    pending_clarification_grace_seconds: int = Field(default=60)
    vosk_model_path: str = Field(default="vosk_models/vosk-model-small-en-us-0.15")
    porcupine_access_key: str = Field(default="")
    porcupine_model_path: str = Field(default="vosk_models/aiden_en_windows.ppn")
    porcupine_sensitivity: float = Field(default=0.7)
    porcupine_min_energy: float = Field(default=100.0)
    # Raised from 1.5 → 2.0s: longer debounce prevents rapid re-triggers
    porcupine_debounce_seconds: float = Field(default=2.0)
    porcupine_confirmation_window: float = Field(default=0.2)
    use_porcupine: bool = Field(default=True)
    # openWakeWord — open-source, no API key, built-in Silero VAD gating
    # Set SPEECH_USE_OPENWAKEWORD=true to switch from Porcupine to openWakeWord
    use_openwakeword: bool = Field(default=False)
    oww_model_path: str = Field(default="")          # path to custom .tflite/.onnx model; leave blank for pre-trained
    oww_threshold: float = Field(default=0.5)         # activation score threshold (0-1)
    oww_vad_threshold: float = Field(default=0.3)     # Silero VAD gate; 0=disabled, higher=stricter
    oww_verifier_path: str = Field(default="")
    oww_verifier_gate: float = Field(default=0.25)
    oww_strong_threshold: float = Field(default=0.75)
    oww_smoothing_window: int = Field(default=3)
    oww_smoothing_hits: int = Field(default=2)
    oww_continuation_window_ms: int = Field(default=300)  # 0 disables same-breath command capture
    oww_profile_path: str = Field(default="")
    oww_shadow_mode: bool = Field(default=False)
    oww_capture_diagnostics: bool = Field(default=False)
    # Silero VAD — more accurate than WebRTC VAD (requires torch)
    stt_use_silero_vad: bool = Field(default=True)
    stt_silero_threshold: float = Field(default=0.5)
    # VAD aggressiveness for WebRTC fallback (0=sensitive, 3=strict)
    stt_vad_aggressiveness: int = Field(default=1)

    @field_validator("stt_device_index", mode="before")
    @classmethod
    def parse_optional_device_index(cls, value: Any) -> Optional[int]:
        if value in (None, "", "None", "null"):
            return None
        return value


class CacheConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CACHE_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    enable_caching: bool = Field(default=True, validation_alias=AliasChoices("enable_caching", "ENABLE_CACHING"))
    ttl_context: int = Field(default=300)
    ttl_app_paths: int = Field(default=86400)
    ttl_llm_response: int = Field(default=3600)
    ttl_tts_audio: int = Field(default=604800)


class SpotifyConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SPOTIFY_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = Field(default=True)
    client_id: str = Field(default="")
    client_secret: str = Field(default="")
    refresh_token: str = Field(default="")
    default_device_name: Optional[str] = Field(default=None)


class UPSConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="UPS_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = Field(default=True)
    info_log_path: str = Field(default=r"C:\ViewPower\log\info.log")
    alert_threshold: int = Field(default=80)
    critical_threshold: int = Field(default=50)
    shutdown_threshold: int = Field(default=50)
    polling_interval: float = Field(default=1.0)
    shutdown_timeout: int = Field(default=120)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    gemini: GeminiConfig = Field(default_factory=GeminiConfig)
    groq: GroqConfig = Field(default_factory=GroqConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    app: AppConfig = Field(default_factory=AppConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    esp32: ESP32Config = Field(default_factory=ESP32Config)
    speech: SpeechConfig = Field(default_factory=SpeechConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    spotify: SpotifyConfig = Field(default_factory=SpotifyConfig)
    ups: UPSConfig = Field(default_factory=UPSConfig)

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        provider = self.app.llm_provider
        if provider == "gemini":
            if not any(
                [self.gemini.api_key, self.gemini.api_key_1, self.gemini.api_key_2, self.gemini.api_key_3]
            ):
                raise ValueError("At least one Gemini API key must be configured.")
        elif provider == "groq":
            if not self.groq.api_key:
                raise ValueError("GROQ_API_KEY must be configured.")
        elif provider == "ollama":
            if not self.ollama.base_url:
                raise ValueError("OLLAMA_BASE_URL must be configured.")
        else:
            raise ValueError(f"Invalid llm provider: {provider}")

        if not self.database.database_url:
            raise ValueError("NEON_DATABASE_URL must be configured.")
        if not self.redis.url:
            raise ValueError("REDIS_URL must be configured.")
        return self


settings: Optional[Settings] = None
settings_overrides: Dict[str, Any] = {}


def get_settings_overrides() -> Dict[str, Any]:
    return deepcopy(settings_overrides)


def set_settings_overrides(overrides: Optional[Dict[str, Any]]) -> None:
    global settings_overrides
    settings_overrides = deepcopy(overrides or {})


def clear_settings_overrides() -> None:
    set_settings_overrides({})


def _build_settings() -> Settings:
    base = Settings()
    if not settings_overrides:
        return base
    merged = _deep_merge(base.model_dump(), settings_overrides)
    return Settings.model_validate(merged)


def get_settings() -> Settings:
    global settings
    if settings is None:
        settings = _build_settings()
    return settings


def reload_settings() -> Settings:
    global settings
    settings = _build_settings()
    return settings
