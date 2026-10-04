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

    logger = __import__("src.utils.logger", fromlist=["get_logger"]).get_logger(__name__)
    
    if target_name:
        target_lower = target_name.lower()
        original_target = target_lower
        
        # Normalize common aliases
        is_desktop_request = "pc" in target_lower or "desktop" in target_lower or "computer" in target_lower
        is_mobile_request = "phone" in target_lower or "mobile" in target_lower
        is_tv_request = "tv" in target_lower or "television" in target_lower or "cast" in target_lower
             
        logger.info(f"Looking for device matching: '{target_name}' (desktop={is_desktop_request}, mobile={is_mobile_request}, tv={is_tv_request})")
             
        for device in devices:
            d_name = str(device.get("name", "")).lower()
            d_type = str(device.get("type", "")).lower()
            logger.info(f"Checking device: name='{d_name}', type='{d_type}'")
            
            # Try exact substring match with original target
            if original_target in d_name or d_name in original_target:
                logger.info(f"Found device by name substring match: {device['name']}")
                return device
            
            # Type-based matching for desktop/pc/computer
            if is_desktop_request and d_type == "computer":
                logger.info(f"Found desktop device by type: {device['name']}")
                return device
                
            # Type-based matching for mobile/phone
            if is_mobile_request and (d_type == "smartphone" or d_type == "phone"):
                logger.info(f"Found mobile device by type: {device['name']}")
                return device
            
            # Type-based matching for TV/Cast devices
            if is_tv_request and ("tv" in d_type or "cast" in d_type or "tv" in d_name or "cast" in d_name):
                logger.info(f"Found TV/Cast device: {device['name']}")
                return device
            
            # Partial word matching
            target_words = original_target.split()
            for word in target_words:
                if len(word) >= 3 and word in d_name:
                    logger.info(f"Found device by partial word match '{word}': {device['name']}")
                    return device
        
        logger.warning(f"No device matched '{target_name}'")
        return None

    # No target specified, prioritize Computer devices
    logger.info("No specific device requested - using priority logic")
    
    # Find Computer-type devices
    computer_devices = [d for d in devices if str(d.get("type", "")).lower() == "computer"]
    if computer_devices:
        active_computer = next((d for d in computer_devices if d.get("is_active")), None)
        if active_computer:
            logger.info(f"Using active computer device: {active_computer['name']}")
            return active_computer
        else:
            logger.info(f"Defaulting to computer device: {computer_devices[0]['name']}")
            return computer_devices[0]
    
    # If no computer found, use currently active device
    active_devices = [d for d in devices if d.get("is_active")]
    if active_devices:
        logger.info(f"No computer device found - using active device: {active_devices[0]['name']}")
        return active_devices[0]
    
    # Fallback to first available device
    logger.info(f"Fallback to first available device: {devices[0]['name']}")
    return devices[0]
