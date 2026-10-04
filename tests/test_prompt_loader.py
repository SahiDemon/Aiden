from unittest.mock import patch

import pytest

from src.utils import prompt_loader


@pytest.fixture
def prompts_file(tmp_path, monkeypatch):
    path = tmp_path / "prompts.yaml"
    path.write_text("system_prompt: first\n", encoding="utf-8")
    monkeypatch.setattr(prompt_loader, "PROMPTS_PATH", path)
    monkeypatch.setattr(prompt_loader, "_CACHE_KEY", None)
    monkeypatch.setattr(prompt_loader, "_PROMPT_DEFAULTS", {})
    monkeypatch.setattr(prompt_loader, "PROMPT_OVERRIDES", {})
    return path


def test_prompt_defaults_reuse_yaml_parse_and_reload_changed_file(prompts_file):
    with patch.object(prompt_loader.yaml, "safe_load", wraps=prompt_loader.yaml.safe_load) as parse:
        assert prompt_loader.get_prompt("system_prompt") == "first"
        assert prompt_loader.get_prompt("system_prompt") == "first"
        assert parse.call_count == 1
        prompts_file.write_text("system_prompt: updated value\n", encoding="utf-8")
        assert prompt_loader.get_prompt("system_prompt") == "updated value"
        assert parse.call_count == 2


def test_prompt_overrides_and_returned_copies_do_not_mutate_cached_defaults(prompts_file):
    prompt_loader.set_prompt_overrides({"system_prompt": "override"})
    assert prompt_loader.get_prompt("system_prompt") == "override"
    prompt_loader.get_all_prompts()["system_prompt"] = "modified copy"
    prompt_loader.set_prompt_overrides(None)
    assert prompt_loader.get_prompt("system_prompt") == "first"


def test_deleted_prompt_file_does_not_reuse_stale_defaults(prompts_file):
    assert prompt_loader.get_prompt("system_prompt") == "first"
    prompts_file.unlink()
    assert prompt_loader.get_prompt("system_prompt", "fallback") == "fallback"
