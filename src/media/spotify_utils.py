"""Helper utilities for Spotify integration."""
from __future__ import annotations

from typing import Dict, List, Optional


def find_best_device(devices: List[Dict[str, object]], target_name: Optional[str] = None) -> Optional[Dict[str, object]]:
    """
    Choose the best playback device.
    If target_name provided, match by substring (case-insensitive).
    Otherwise prefer active devices, then computers, then the first entry.
    """
    if not devices:
        return None

    if target_name:
        target_lower = target_name.lower()
        for device in devices:
            if target_lower in str(device.get("name", "")).lower():
                return device

    active_devices = [d for d in devices if d.get("is_active")]
    if active_devices:
        return active_devices[0]

    computer_devices = [d for d in devices if d.get("type") == "Computer"]
    if computer_devices:
        return computer_devices[0]

    return devices[0]
