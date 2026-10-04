from __future__ import annotations

from threading import RLock
from typing import Dict

import yaml

from src.utils.logger import get_logger
from src.utils.paths import resource_path

logger = get_logger(__name__)

PROMPTS_PATH = resource_path("config", "prompts.yaml")
PROMPT_OVERRIDES: Dict[str, str] = {}
_CACHE_LOCK = RLock()
_CACHE_KEY: tuple[str, int, int] | None = None
_PROMPT_DEFAULTS: Dict[str, str] = {}


def load_prompt_defaults() -> Dict[str, str]:
    """Cache defaults until the source file changes, returning an isolated copy."""
    global _CACHE_KEY, _PROMPT_DEFAULTS
    with _CACHE_LOCK:
        try:
            stat = PROMPTS_PATH.stat()
            key = (str(PROMPTS_PATH), stat.st_mtime_ns, stat.st_size)
            if key != _CACHE_KEY:
                with PROMPTS_PATH.open("r", encoding="utf-8") as file:
                    data = yaml.safe_load(file) or {}
                if not isinstance(data, dict):
                    raise ValueError("Prompt configuration must be a mapping")
                _PROMPT_DEFAULTS = {key: value for key, value in data.items() if isinstance(value, str)}
                _CACHE_KEY = key
            return dict(_PROMPT_DEFAULTS)
        except FileNotFoundError:
            _CACHE_KEY = None
            _PROMPT_DEFAULTS = {}
            return {}
        except Exception as exc:
            logger.error(f"Failed to load prompts.yaml: {exc}")
            return {}


def set_prompt_overrides(overrides: Dict[str, str] | None) -> None:
    global PROMPT_OVERRIDES
    with _CACHE_LOCK:
        PROMPT_OVERRIDES = dict(overrides or {})


def get_prompt(name: str, default: str = "") -> str:
    with _CACHE_LOCK:
        if name in PROMPT_OVERRIDES:
            return PROMPT_OVERRIDES[name]
    defaults = load_prompt_defaults()
    return defaults.get(name, default)


def get_all_prompts() -> Dict[str, str]:
    prompts = load_prompt_defaults()
    with _CACHE_LOCK:
        prompts.update(PROMPT_OVERRIDES)
    return prompts
