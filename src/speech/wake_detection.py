"""Shared wake-detection payloads and text helpers."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional


_WAKE_PREFIX = re.compile(
    r"^\s*(?:(?:hey|okay|ok)[\s,.-]+)?(?:aiden|aidan|ayden)\b[\s,;:!?.-]*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class WakeDetection:
    """A wake-word activation and any command audio captured with it."""

    model_name: str
    confidence: float
    timestamp: float = field(default_factory=time.time)
    command_audio: Optional[bytes] = None
    sample_rate: int = 16_000
    sample_width: int = 2
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_command_audio(self) -> bool:
        return bool(self.command_audio)


def strip_wake_phrase(text: str) -> str:
    """Remove a leading Aiden wake phrase from a one-sentence transcript."""
    if not text:
        return ""
    return _WAKE_PREFIX.sub("", text, count=1).strip()
