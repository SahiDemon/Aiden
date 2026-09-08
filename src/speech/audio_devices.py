"""Stable input-device selection shared by wake detection and STT."""

from __future__ import annotations

from typing import Any, Optional


def resolve_input_device_index(
    preferred_name: str,
    audio: Any,
    *,
    sample_rate: Optional[int] = None,
    input_format: Optional[int] = None,
) -> Optional[int]:
    """Return the best input device whose name contains ``preferred_name``.

    ``None`` deliberately means "use the operating-system default". Matching
    by name is more stable than persisting a PyAudio index, which can change
    after reboots, Bluetooth reconnects, and driver updates.
    """
    needle = (preferred_name or "").strip().casefold()
    if not needle:
        return None
    tokens = [token for token in needle.replace("-", " ").split() if len(token) >= 3]

    def name_matches(candidate_name: str) -> bool:
        folded = candidate_name.casefold()
        if needle in folded:
            return True
        matching_tokens = sum(token in folded for token in tokens)
        return bool(tokens and matching_tokens >= max(1, len(tokens) - 1))

    def supports_format(index: int) -> bool:
        if sample_rate is None or input_format is None:
            return True
        try:
            audio.is_format_supported(
                sample_rate,
                input_device=index,
                input_channels=1,
                input_format=input_format,
            )
            return True
        except (OSError, ValueError):
            return False

    # Prefer the current default endpoint when it is clearly the requested
    # physical device. Windows can expose full-name DirectSound endpoints that
    # open successfully but deliver silence, while its truncated MME default
    # carries the real signal. Allow one missing name token for that default.
    try:
        default_info = audio.get_default_input_device_info()
        default_name = str(default_info.get("name", "")).casefold()
        matching_tokens = sum(token in default_name for token in tokens)
        default_index = int(default_info["index"])
        if (
            needle in default_name
            or (tokens and matching_tokens >= max(1, len(tokens) - 1))
        ) and supports_format(default_index):
            return default_index
    except Exception:
        pass

    candidates: list[tuple[int, int]] = []
    for index in range(audio.get_device_count()):
        info = audio.get_device_info_by_index(index)
        if int(info.get("maxInputChannels", 0)) <= 0:
            continue
        name = str(info.get("name", ""))
        folded = name.casefold()
        if not name_matches(name):
            continue
        if not supports_format(index):
            continue

        # Prefer a complete name match, then the shortest matching endpoint.
        if folded == needle:
            rank = 0
        elif needle in folded:
            rank = len(folded)
        else:
            rank = 1_000 + len(folded)
        candidates.append((rank, index))

    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]
