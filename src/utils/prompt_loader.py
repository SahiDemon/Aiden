from __future__ import annotations

from pathlib import Path
from typing import Dict

import yaml

from src.utils.logger import get_logger

logger = get_logger(__name__)

PROMPTS_PATH = Path("config/prompts.yaml")
PROMPT_OVERRIDES: Dict[str, str] = {}


def load_prompt_defaults() -> Dict[str, str]:
    try:
        if not PROMPTS_PATH.exists():
            return {}
        with open(PROMPTS_PATH, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        return {key: value for key, value in data.items() if isinstance(value, str)}
    except Exception as exc:
        logger.error(f"Failed to load prompts.yaml: {exc}")
        return {}


def set_prompt_overrides(overrides: Dict[str, str] | None) -> None:
    global PROMPT_OVERRIDES
    PROMPT_OVERRIDES = dict(overrides or {})


def get_prompt(name: str, default: str = "") -> str:
    if name in PROMPT_OVERRIDES:
        return PROMPT_OVERRIDES[name]
    defaults = load_prompt_defaults()
    return defaults.get(name, default)


def get_all_prompts() -> Dict[str, str]:
    prompts = load_prompt_defaults()
    prompts.update(PROMPT_OVERRIDES)
    return prompts
