from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Tuple

from src.ai.ollama_client import get_ollama_client
from src.database.neon_client import get_db_client
from src.utils.config import (
    Settings,
    get_settings,
    reload_settings,
    set_settings_overrides,
)
from src.utils.logger import get_logger
from src.utils.env_sync import sync_settings_to_env
from src.utils.prompt_loader import get_all_prompts, set_prompt_overrides
from src.utils.secret_crypto import decrypt_value, encrypt_value

logger = get_logger(__name__)

SECRET_FIELDS = {
    ("gemini", "api_key"),
    ("gemini", "api_key_1"),
    ("gemini", "api_key_2"),
    ("gemini", "api_key_3"),
    ("groq", "api_key"),
    ("spotify", "client_id"),
    ("spotify", "client_secret"),
    ("spotify", "refresh_token"),
    ("speech", "google_tts_credentials_path"),
    ("speech", "porcupine_access_key"),
}

BACKEND_MODEL_OPTIONS = {
    "gemini": [
        {"value": "gemini-2.5-flash-lite", "label": "Gemini 2.5 Flash Lite"},
        {"value": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
        {"value": "gemini-1.5-pro", "label": "Gemini 1.5 Pro"},
    ],
    "groq": [
        {"value": "llama-3.1-8b-instant", "label": "Llama 3.1 8B Instant"},
        {"value": "llama-3.1-70b-versatile", "label": "Llama 3.1 70B Versatile"},
        {"value": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B Versatile"},
        {"value": "mixtral-8x7b-32768", "label": "Mixtral 8x7B"},
    ],
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * max(4, len(value) - 8)}{value[-4:]}"


def _get_master_key() -> str:
    settings = get_settings()
    return (
        getattr(settings.app, "settings_encryption_key", "")
        or settings.database.database_url
        or settings.redis.url
        or ""
    )


def _encrypt_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    encrypted = deepcopy(payload)
    master_key = _get_master_key()
    for section, field in SECRET_FIELDS:
        section_data = encrypted.get(section)
        if not isinstance(section_data, dict):
            continue
        value = section_data.get(field)
        if isinstance(value, str) and value and not value.startswith("gAAAA"):
            section_data[field] = encrypt_value(master_key, value)
    return encrypted


def _decrypt_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    decrypted = deepcopy(payload)
    master_key = _get_master_key()
    for section, field in SECRET_FIELDS:
        section_data = decrypted.get(section)
        if not isinstance(section_data, dict):
            continue
        value = section_data.get(field)
        if isinstance(value, str) and value.startswith("gAAAA"):
            section_data[field] = decrypt_value(master_key, value)
    return decrypted


def _sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = deepcopy(payload)
    for section, field in SECRET_FIELDS:
        section_data = sanitized.get(section)
        if not isinstance(section_data, dict):
            continue
        value = section_data.get(field, "")
        section_data[field] = _mask(value) if value else ""
    return sanitized


async def load_settings_overrides(user_id: str = "default") -> Dict[str, Any]:
    try:
        db = await get_db_client()
        prefs = await db.get_user_preferences(user_id=user_id)
    except Exception as exc:
        logger.warning(f"Settings overrides unavailable from database: {exc}")
        set_prompt_overrides({})
        set_settings_overrides({})
        reload_settings()
        return {}

    if not prefs or not prefs.settings:
        set_prompt_overrides({})
        set_settings_overrides({})
        reload_settings()
        return {}
    raw = deepcopy(prefs.settings)
    prompts = raw.pop("prompts", {})
    decrypted = _decrypt_payload(raw)
    set_prompt_overrides(prompts)
    set_settings_overrides(decrypted)
    reload_settings()
    return {"prompts": prompts, **decrypted}


def _build_settings_payload(settings: Settings, overrides: Dict[str, Any]) -> Dict[str, Any]:
    prompts = get_all_prompts()
    payload = settings.model_dump()
    payload["prompts"] = prompts
    payload["meta"] = {
        "provider": settings.app.llm_provider,
        "gemini": {
            "configured_key_count": sum(
                bool(key)
                for key in [
                    settings.gemini.api_key,
                    settings.gemini.api_key_1,
                    settings.gemini.api_key_2,
                    settings.gemini.api_key_3,
                ]
            ),
            "rotation_enabled": settings.gemini.auto_key_rotation,
        },
        "overrides_present": bool(overrides),
    }
    payload["model_options"] = deepcopy(BACKEND_MODEL_OPTIONS)
    return _sanitize_payload(payload)


async def get_settings_payload(user_id: str = "default") -> Dict[str, Any]:
    overrides = await load_settings_overrides(user_id=user_id)
    settings = get_settings()
    return _build_settings_payload(settings, overrides)


def _prepare_save_payload(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    payload = deepcopy(payload)
    prompts = payload.pop("prompts", {})
    payload.pop("meta", None)
    payload.pop("model_options", None)

    current = get_settings()
    current_dump = current.model_dump()
    for section, field in SECRET_FIELDS:
        incoming = payload.get(section, {}).get(field) if isinstance(payload.get(section), dict) else None
        if not isinstance(incoming, str) or not incoming:
            continue
        masked = _mask(current_dump.get(section, {}).get(field, ""))
        if incoming == masked:
            payload[section][field] = current_dump.get(section, {}).get(field, "")
    return payload, prompts


async def save_settings_payload(payload: Dict[str, Any], user_id: str = "default") -> Dict[str, Any]:
    data, prompts = _prepare_save_payload(payload)
    merged = _deep_merge(get_settings().model_dump(), data)
    validated = Settings.model_validate(merged)
    overrides = validated.model_dump()
    encrypted_overrides = _encrypt_payload(overrides)

    db = await get_db_client()
    await db.update_user_preferences(
        user_id=user_id,
        settings={**encrypted_overrides, "prompts": prompts},
    )
    set_prompt_overrides(prompts)
    set_settings_overrides(overrides)
    reload_settings()
    sync_settings_to_env(get_settings())
    return _build_settings_payload(get_settings(), {**overrides, "prompts": prompts})


async def get_provider_models(provider: str) -> Dict[str, Any]:
    if provider == "ollama":
        try:
            client = await get_ollama_client()
            models = await client.list_models()
            return {
                "provider": "ollama",
                "reachable": True,
                "models": [
                    {"value": model.get("name", ""), "label": model.get("name", "")}
                    for model in models
                    if model.get("name")
                ],
            }
        except Exception as exc:
            logger.warning(f"Ollama model discovery failed: {exc}")
            return {"provider": "ollama", "reachable": False, "models": [], "error": str(exc)}

    return {"provider": provider, "reachable": True, "models": deepcopy(BACKEND_MODEL_OPTIONS.get(provider, []))}
