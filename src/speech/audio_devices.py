"""Stable input-device selection shared by wake detection and STT."""

from __future__ import annotations

from typing import Any, Optional


def resolve_input_device_index(
    preferred_name: str,
    audio: Any,
) -> Optional[int]:
    """Return the best input device whose name contains ``preferred_name``.

    ``None`` deliberately means "use the operating-system default". Matching
    by name is more stable than persisting a PyAudio index, which can change
    after reboots, Bluetooth reconnects, and driver updates.
    """
    needle = (preferred_name or "").strip().casefold()
    if not needle:
        return None

    # Prefer the current default endpoint when it is clearly the requested
    # physical device. Windows MME names are sometimes truncated (for example
    # "USB PnP Audio De"), so allow one missing name token.
    try:
        default_info = audio.get_default_input_device_info()
        default_name = str(default_info.get("name", "")).casefold()
        tokens = [token for token in needle.replace("-", " ").split() if len(token) >= 3]
        matching_tokens = sum(token in default_name for token in tokens)
        if needle in default_name or (tokens and matching_tokens >= max(1, len(tokens) - 1)):
            return int(default_info["index"])
    except Exception:
        pass

    candidates: list[tuple[int, int]] = []
    for index in range(audio.get_device_count()):
        info = audio.get_device_info_by_index(index)
        if int(info.get("maxInputChannels", 0)) <= 0:
            continue
        name = str(info.get("name", ""))
        folded = name.casefold()
        if needle not in folded:
            continue

        # Prefer a complete name match, then the shortest matching endpoint.
        rank = 0 if folded == needle else len(folded)
        candidates.append((rank, index))

    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]
