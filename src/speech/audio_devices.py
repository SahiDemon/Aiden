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

    # Remember the current default as a tie-breaker only. Windows MME names
    # are often truncated (for example "USB PnP Audio De"), while WASAPI and
    # WDM-KS expose the complete device name. An explicit full-name match is
    # more stable and, importantly, preserves the endpoint used for wake-word
    # recordings instead of silently switching to an MME duplicate.
    default_index: Optional[int] = None
    try:
        default_info = audio.get_default_input_device_info()
        candidate_default_index = int(default_info["index"])
        if supports_format(candidate_default_index):
            default_index = candidate_default_index
    except Exception:
        pass

    candidates: list[tuple[int, int, int, int]] = []
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

        # A full configured-name match outranks a fuzzy/truncated one. Within
        # an equally good match, the Windows default is preferred, then the
        # shortest endpoint name and its stable PyAudio index break ties.
        match_rank = 0 if needle in folded else 1
        default_rank = 0 if index == default_index else 1
        candidates.append((match_rank, default_rank, len(folded), index))

    if not candidates:
        return None
    candidates.sort()
    return candidates[0][-1]
