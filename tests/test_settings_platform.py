import asyncio
from pathlib import Path

from src.ai.ollama_client import OllamaClient
from src.services.settings_service import get_provider_models
from src.utils.config import (
    Settings,
    clear_settings_overrides,
    get_settings,
    reload_settings,
    set_settings_overrides,
)
from src.utils.env_sync import sync_settings_to_env


def test_settings_override_merge_updates_runtime_config():
    original = get_settings()
    original_name = original.app.name

    set_settings_overrides({"app": {"name": "Control Room"}, "ollama": {"model": "llama3.2:latest"}})
    reloaded = reload_settings()

    assert reloaded.app.name == "Control Room"
    assert reloaded.ollama.model == "llama3.2:latest"

    clear_settings_overrides()
    reset = reload_settings()
    assert reset.app.name == original_name


def test_provider_models_for_static_providers():
    gemini = asyncio.run(get_provider_models("gemini"))
    groq = asyncio.run(get_provider_models("groq"))

    assert gemini["reachable"] is True
    assert any(model["value"].startswith("gemini-") for model in gemini["models"])
    assert groq["reachable"] is True
    assert any("llama" in model["value"] or "mixtral" in model["value"] for model in groq["models"])


def test_env_sync_writes_unquoted_values_and_optional_ints_round_trip(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "NEON_DATABASE_URL=postgresql://example",
                "REDIS_URL=redis://localhost:6379/0",
                "GEMINI_API_KEY=test-key",
                "LLM_PROVIDER=gemini",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings.model_validate(
        {
            "app": {"llm_provider": "ollama"},
            "database": {"database_url": "postgresql://example"},
            "redis": {"url": "redis://localhost:6379/0"},
            "gemini": {"api_key": "test-key"},
            "ollama": {"model": "qwen2.5:3b"},
            "speech": {"stt_device_index": None},
        }
    )

    sync_settings_to_env(settings, env_path=str(env_path))
    content = env_path.read_text(encoding="utf-8")

    assert "LLM_PROVIDER=ollama" in content
    assert "OLLAMA_MODEL=qwen2.5:3b" in content
    assert "SPEECH_STT_DEVICE_INDEX=" in content
    assert "LLM_PROVIDER='ollama'" not in content


def test_ollama_client_extracts_json_from_wrapped_content():
    client = OllamaClient()
    parsed = client._parse_json_response(
        'Here is the result:\n```json\n{"intent":"command","commands":[],"response":"Done"}\n```'
    )

    assert parsed is not None
    assert parsed["intent"] == "command"
    assert parsed["response"] == "Done"


def test_ollama_client_falls_back_for_plain_text_content():
    client = OllamaClient()
    fallback = client._fallback_response("I can help with that, but I need more detail.")

    assert fallback["commands"] == []
    assert fallback["intent"] == "question"
    assert "need more detail" in fallback["response"]
