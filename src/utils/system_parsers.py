"""
Parsing helpers for Windows system commands.
These functions keep subprocess parsing logic isolated and testable.
"""
from __future__ import annotations

import re
from typing import List, Dict, Optional


def parse_netsh_interfaces(output: str) -> List[Dict[str, str]]:
    """
    Parse `netsh interface show interface` output into structured rows.
    """
    interfaces: List[Dict[str, str]] = []
    lines = output.splitlines()
    # Skip header until dashed line
    start_idx = 0
    for idx, line in enumerate(lines):
        if set(line.strip()) == {"-"}:
            start_idx = idx + 1
            break
    for line in lines[start_idx:]:
        line = line.strip()
        if not line:
            continue
        match = re.match(r"(\S+)\s+(\S+)\s+(\S+)\s+(.+)", line)
        if not match:
            continue
        admin, state, iface_type, name = match.groups()
        interfaces.append(
            {
                "admin_state": admin,
                "state": state,
                "type": iface_type,
                "name": name.strip(),
            }
        )
    return interfaces


def select_wireless_interface(interfaces: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """
    Choose the most likely Wi-Fi adapter from parsed interface rows.
    Preference order: names containing wifi/wlan/wireless, type 'Wireless'.
    """
    keywords = ("wi-fi", "wifi", "wlan", "wireless")
    # Pass 1: name based
    for interface in interfaces:
        name_lower = interface.get("name", "").lower()
        if any(keyword in name_lower for keyword in keywords):
            return interface
    # Pass 2: explicit Wireless type
    for interface in interfaces:
        if interface.get("type", "").lower() == "wireless":
            return interface
    return None


def parse_netsh_wlan_interfaces(output: str) -> List[Dict[str, str]]:
    """
    Parse `netsh wlan show interfaces` output.
    Returns list with keys like name, state, ssid.
    """
    interfaces: List[Dict[str, str]] = []
    current: Dict[str, str] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                interfaces.append(current)
                current = {}
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        current[key.strip().lower()] = value.strip()
    if current:
        interfaces.append(current)
    # Normalize keys we use
    normalized: List[Dict[str, str]] = []
    for iface in interfaces:
        if "name" not in iface and "ssid" not in iface:
            continue
        normalized.append(
            {
                "name": iface.get("name"),
                "state": iface.get("state"),
                "ssid": iface.get("ssid"),
                "description": iface.get("description"),
            }
        )
    return normalized


def parse_pnp_bluetooth_devices(output: str) -> List[Dict[str, str]]:
    """
    Parse `Get-PnpDevice -Class Bluetooth | Format-List` output.
    """
    devices: List[Dict[str, str]] = []
    current: Dict[str, str] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                devices.append(current)
                current = {}
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized_key = key.strip().lower().replace(" ", "_")
        current[normalized_key] = value.strip()
    if current:
        devices.append(current)
    return devices


def select_primary_bluetooth_device(devices: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """
    Pick the Bluetooth radio we should toggle.
    Preference for Status=OK/Started and FriendlyName containing 'Bluetooth'.
    """
    best_device: Optional[Dict[str, str]] = None
    best_score = -1
    for device in devices:
        friendly = device.get("friendlyname", "")
        instance_id = device.get("instanceid")
        if not instance_id:
            continue
        score = 0
        status = device.get("status", "").lower()
        if status in {"ok", "started"}:
            score += 2
        if "bluetooth" in friendly.lower():
            score += 3
        if device.get("class", "").lower() == "bluetooth":
            score += 1
        if score > best_score:
            best_device = device
            best_score = score
    return best_device


def parse_powercfg_plans(output: str) -> List[Dict[str, str]]:
    """
    Parse `powercfg /L` output into plan dictionaries.
    """
    plans: List[Dict[str, str]] = []
    pattern = re.compile(
        r"Power Scheme GUID:\s+([0-9a-fA-F-]+)\s+\(([^)]+)\)(?:\s+\*)?"
    )
    for line in output.splitlines():
        line = line.strip()
        match = pattern.search(line)
        if not match:
            continue
        guid, name = match.groups()
        plans.append({"guid": guid.strip(), "name": name.strip()})
    return plans
