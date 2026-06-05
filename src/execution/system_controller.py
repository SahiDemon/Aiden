"""
System Controller
Control Windows system operations, hardware toggles, and telemetry.
"""
from __future__ import annotations

import ctypes
import json
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List
import shutil
import re

from src.utils.logger import get_logger
from src.utils.paths import app_root
from src.utils.system_parsers import (
    parse_netsh_interfaces,
    select_wireless_interface,
    parse_netsh_wlan_interfaces,
    parse_pnp_bluetooth_devices,
    select_primary_bluetooth_device,
    parse_powercfg_plans,
)

logger = get_logger(__name__)

REPO_ROOT = app_root()


def _resolve_tool_path(candidates: List[Path]) -> Optional[Path]:
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


CLICKMONITOR_CANDIDATES = [
    Path(r"C:\Tools\ClickMonitorDDC\ClickMonitorDDC.exe"),
    Path(r"C:\Tools\ClickMonitorDDC.exe"),
    REPO_ROOT / "tools" / "ClickMonitorDDC" / "ClickMonitorDDC.exe",
    REPO_ROOT / "tools" / "ClickMonitorDDC.exe",
    REPO_ROOT / "tools" / "ClickMonitorDDC_7_2.exe",
]

NIRCMD_CANDIDATES = [
    Path(r"C:\Tools\nircmd\nircmd.exe"),
    Path(r"C:\Tools\nircmd.exe"),
    REPO_ROOT / "tools" / "nircmd" / "nircmd.exe",
    REPO_ROOT / "tools" / "nircmd.exe",
]

NVIDIA_SMI_CANDIDATES = [
    REPO_ROOT / "tools" / "nvidia-smi.exe",
    Path(r"C:\Tools\nvidia-smi\nvidia-smi.exe"),
]

POWER_STATUS_MAP = {
    1: "Discharging",
    2: "Connected to power",
    3: "Fully charged",
    4: "Low",
    5: "Critical",
    6: "Charging",
    7: "Charging (High)",
    8: "Charging (Low)",
    9: "Charging (Critical)",
    10: "Unknown",
    11: "Partially charged",
}


class SystemController:
    """Control Windows system operations"""

    def __init__(self):
        self.clickmonitor_path = _resolve_tool_path(CLICKMONITOR_CANDIDATES)
        self.nircmd_path = _resolve_tool_path(NIRCMD_CANDIDATES)
        which_path = shutil.which("nvidia-smi")
        self.nvidia_smi_path = _resolve_tool_path(NVIDIA_SMI_CANDIDATES)
        if not self.nvidia_smi_path and which_path:
            self.nvidia_smi_path = Path(which_path)

    async def lock_screen(self) -> bool:
        """Lock the Windows screen"""
        try:
            ctypes.windll.user32.LockWorkStation()
            logger.info("Screen locked successfully")
            return True
        except Exception as e:
            logger.error(f"Error locking screen: {e}")
            return False

    async def shutdown(self, force: bool = True) -> bool:
        """Shutdown Windows"""
        command = "shutdown /s /t 0"
        if force:
            command += " /f"
        return self._run_simple_command(command)

    async def restart(self, force: bool = False) -> bool:
        """Restart Windows"""
        command = "shutdown /r /t 0"
        if force:
            command += " /f"
        return self._run_simple_command(command)

    async def sleep(self) -> bool:
        """Put Windows to sleep"""
        return self._run_simple_command("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")

    async def hibernate(self) -> bool:
        """Hibernate Windows"""
        return self._run_simple_command("shutdown /h")

    async def empty_recycle_bin(self) -> bool:
        """Empty the Windows Recycle Bin"""
        try:
            # Use PowerShell to empty recycle bin
            # Note: Clear-RecycleBin returns exit code 0 even when recycle bin is already empty
            command = 'powershell -Command "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"'
            logger.info("Emptying recycle bin...")
            
            # Run command - it always succeeds if PowerShell executes
            success, stdout, stderr = self._run_command(command, shell=True)
            
            # PowerShell returns 0 even when recycle bin is empty, so we consider it success
            # as long as the command executed without PowerShell errors
            if success or not stderr or stderr.strip() == "":
                logger.info("Recycle bin emptied successfully")
                return True
            else:
                logger.error(f"Error emptying recycle bin: {stderr}")
                return False
        except Exception as e:
            logger.error(f"Error emptying recycle bin: {e}")
            return False

    async def execute_shell_command(self, command: str) -> tuple[bool, str]:
        """Execute arbitrary shell command."""
        try:
            logger.info(f"Executing shell command: {command}")
            success, stdout, stderr = self._run_command(command, shell=True)
            output = stdout if success else stderr
            return success, output
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {command}")
            return False, "Command timed out"
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return False, str(e)

    def _run_simple_command(self, command: str) -> bool:
        success, _, stderr = self._run_command(command, shell=True)
        if not success:
            logger.error(f"Command failed: {command} -> {stderr}")
        return success

    def _run_command(
        self,
        command,
        shell: bool = False,
        timeout: int = 30,
    ) -> Tuple[bool, str, str]:
        """Helper to run subprocess commands."""
        result = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        success = result.returncode == 0
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        return success, stdout, stderr

    async def set_wifi_state(self, enable: bool) -> tuple[bool, Optional[dict]]:
        """Enable or disable the wireless adapter using discovery-first approach."""
        success, stdout, stderr = self._run_command(
            ["netsh", "interface", "show", "interface"]
        )
        if not success:
            logger.error(f"Failed to list network interfaces: {stderr}")
            return False, {"type": "wifi", "message": "Unable to read network interfaces."}

        interfaces = parse_netsh_interfaces(stdout)
        wifi_interface = select_wireless_interface(interfaces)
        if not wifi_interface:
            logger.error("Wireless adapter not found in interface list")
            return False, {"type": "wifi", "message": "Wireless adapter not found."}

        action = "enabled" if enable else "disabled"
        command = [
            "netsh",
            "interface",
            "set",
            "interface",
            f'name="{wifi_interface["name"]}"',
            f"admin={'enabled' if enable else 'disabled'}",
        ]
        logger.info(f"Setting Wi-Fi adapter '{wifi_interface['name']}' to {action}")
        success, _, stderr = self._run_command(command)
        if not success:
            logger.error(f"Failed to set Wi-Fi state: {stderr}")
            hint = " Failed to set Wi-Fi {action}. Try running Aiden as administrator."
            message = f"Failed to set Wi-Fi {action}."
            if "access is denied" in (stderr or "").lower() or not stderr:
                message += " Please run Aiden with administrator permissions."
            return False, {"type": "wifi", "message": message}

        return True, {
            "type": "wifi",
            "message": f"Wi-Fi adapter '{wifi_interface['name']}' {action}.",
        }

    async def disconnect_wifi(self) -> tuple[bool, Optional[dict]]:
        """Disconnect current Wi-Fi network without disabling adapter."""
        success, stdout, stderr = self._run_command(
            ["netsh", "wlan", "show", "interfaces"]
        )
        if not success:
            logger.error(f"Failed to show WLAN interfaces: {stderr}")
            return False, {"type": "wifi", "message": "Unable to read Wi-Fi state."}

        interfaces = parse_netsh_wlan_interfaces(stdout)
        interface = next((iface for iface in interfaces if iface.get("name")), None)
        if not interface:
            logger.error("No WLAN interface found to disconnect")
            return False, {"type": "wifi", "message": "No active Wi-Fi interface found."}

        command = [
            "netsh",
            "wlan",
            "disconnect",
            f'interface="{interface["name"]}"',
        ]
        logger.info(f"Disconnecting Wi-Fi interface '{interface['name']}'")
        success, _, stderr = self._run_command(command)
        if not success:
            logger.error(f"Failed to disconnect Wi-Fi: {stderr}")
            return False, {"type": "wifi", "message": "Failed to disconnect Wi-Fi."}

        ssid = interface.get("ssid") or "current network"
        message = f"Disconnected {ssid} on interface '{interface['name']}'."
        return True, {"type": "wifi", "message": message}

    async def set_bluetooth_state(self, enable: bool) -> tuple[bool, Optional[dict]]:
        """Enable or disable the main Bluetooth radio using PnP discovery."""
        script = "Get-PnpDevice -Class Bluetooth | Format-List"
        success, stdout, stderr = self._run_command(
            ["powershell", "-NoProfile", "-Command", script]
        )
        if not success:
            logger.error(f"Failed to list Bluetooth devices: {stderr}")
            return False, {"type": "bluetooth", "message": "Unable to list Bluetooth devices."}

        devices = parse_pnp_bluetooth_devices(stdout)
        target = select_primary_bluetooth_device(devices)
        if not target:
            logger.error("No Bluetooth radio detected for toggling")
            return False, {"type": "bluetooth", "message": "Bluetooth radio not found."}

        escaped_instance = target["instanceid"].replace("`", "``").replace('"', '`"')
        cmd_name = "Enable" if enable else "Disable"
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            f'{cmd_name}-PnpDevice -InstanceId "{escaped_instance}" -Confirm:$false',
        ]
        logger.info(f"{cmd_name} Bluetooth radio: {target.get('friendlyname')}")
        success, _, stderr = self._run_command(command)
        if not success:
            logger.error(f"Failed to toggle Bluetooth: {stderr}")
            message = f"Failed to {cmd_name.lower()} Bluetooth."
            if "access is denied" in (stderr or "").lower() or "0x800" in (stderr or "") or not stderr:
                message += " Please run Aiden as administrator."
            return False, {"type": "bluetooth", "message": message}

        message = f"Bluetooth radio {'enabled' if enable else 'disabled'}."
        return True, {"type": "bluetooth", "message": message}

    async def set_airplane_mode(self, enable: bool) -> tuple[bool, Optional[dict]]:
        """Custom airplane mode toggles both Wi-Fi and Bluetooth."""
        if enable:
            wifi_success, wifi_payload = await self.set_wifi_state(False)
        else:
            wifi_success, wifi_payload = await self.set_wifi_state(True)

        bt_target_state = False if enable else True
        bluetooth_success, bluetooth_payload = await self.set_bluetooth_state(bt_target_state)

        success = wifi_success and bluetooth_success
        if not success:
            logger.error("Airplane mode toggle failed on one or more adapters")

        state_text = "enabled" if enable else "disabled"
        message_parts: List[str] = [f"Airplane mode {state_text}."]
        for payload in (wifi_payload, bluetooth_payload):
            if payload and payload.get("message"):
                message_parts.append(payload["message"])

        return success, {"type": "airplane_mode", "message": " ".join(message_parts).strip()}

    async def set_power_plan(self, mode: str) -> tuple[bool, Optional[dict]]:
        """Switch between Balanced and Power Saver plans."""
        success, stdout, stderr = self._run_command(["powercfg", "/L"])
        if not success:
            logger.error(f"Failed to list power plans: {stderr}")
            return False, {"type": "power", "message": "Unable to list power plans."}

        plans = parse_powercfg_plans(stdout)
        target_name = "power saver" if mode == "power_saver" else "balanced"
        target = next(
            (plan for plan in plans if target_name in plan["name"].lower()),
            None,
        )
        if not target:
            logger.error(f"Power plan '{target_name}' not found.")
            return False, {"type": "power", "message": f"{target_name.title()} plan not found."}

        success, _, stderr = self._run_command(["powercfg", "/S", target["guid"]])
        if not success:
            logger.error(f"Failed to set power plan: {stderr}")
            return False, {"type": "power", "message": "Failed to change power plan."}

        mode_label = "Power saver" if mode == "power_saver" else "Balanced"
        return True, {"type": "power", "message": f"{mode_label} plan activated."}

    async def set_brightness(self, level: int) -> tuple[bool, Optional[dict]]:
        """Set monitor brightness via ClickMonitorDDC."""
        if not self.clickmonitor_path or not self.clickmonitor_path.exists():
            logger.error(f"ClickMonitorDDC not found at {self.clickmonitor_path}")
            return False, {"type": "display", "message": "ClickMonitorDDC.exe not found."}

        level = max(0, min(100, level))
        success, _, stderr = self._run_command(
            [str(self.clickmonitor_path), "b", str(level)]
        )
        if not success:
            logger.error(f"Failed to set brightness: {stderr}")
            return False, {"type": "display", "message": "Unable to set display brightness."}

        return True, {"type": "display", "message": f"Brightness set to {level}%."}

    async def control_volume(
        self,
        action: str,
        level: Optional[int] = None,
    ) -> tuple[bool, Optional[dict]]:
        """Control system volume via NirCmd."""
        if not self.nircmd_path or not self.nircmd_path.exists():
            logger.error(f"NirCmd not found at {self.nircmd_path}")
            return False, {"type": "audio", "message": "nircmd.exe not found."}

        action_map = {
            "mute": ["mutesysvolume", "1"],
            "unmute": ["mutesysvolume", "0"],
            "toggle_mute": ["mutesysvolume", "2"],
            "volume_up": ["changesysvolume", "3276"],
            "volume_down": ["changesysvolume", "-3276"],
        }
        if action == "set_volume":
            if level is None:
                return False, {"type": "audio", "message": "Volume level missing."}
            level = max(0, min(100, level))
            value = round(level * 655.35)
            args = ["setsysvolume", str(value)]
        else:
            args = action_map.get(action, [])
        if not args:
            logger.error(f"Unknown volume action: {action}")
            return False, {"type": "audio", "message": "Unknown volume command."}

        success, _, stderr = self._run_command([str(self.nircmd_path), *args])
        if not success:
            logger.error(f"NirCmd failed for {action}: {stderr}")
            return False, {"type": "audio", "message": "Audio command failed."}

        if action == "set_volume":
            msg = f"Volume set to {level}%."
        elif action == "mute":
            msg = "System muted."
        elif action == "unmute":
            msg = "System unmuted."
        elif action == "toggle_mute":
            msg = "Toggled mute."
        elif action == "volume_up":
            msg = "Volume increased."
        else:
            msg = "Volume decreased."
        return True, {"type": "audio", "message": msg}

    async def set_audio_output(self, target: str) -> tuple[bool, Optional[dict]]:
        """Change the audio output device dynamically using Python heuristics."""
        target = target.lower()
        if target not in ["speaker", "headphone"]:
            return False, {"type": "audio", "message": f"Unknown audio target: {target}"}

        # 1. Get playback devices
        ps_command = (
            "if (-not (Get-Module -ListAvailable -Name AudioDeviceCmdlets)) {"
            "Install-Module -Name AudioDeviceCmdlets -Scope CurrentUser -Force -ErrorAction SilentlyContinue;"
            "}; "
            "Import-Module AudioDeviceCmdlets; "
            "$current = Get-AudioDevice -Playback; "
            "$devices = Get-AudioDevice -List | ? Type -eq 'Playback' | Select-Object Name, Index, ID; "
            "@{current=$current.ID; devices=$devices} | ConvertTo-Json -Depth 3"
        )
        success, stdout, stderr = self._run_command(["powershell", "-NoProfile", "-Command", ps_command])
        
        if not success or not stdout:
            logger.error(f"Failed to query audio devices: {stderr}")
            return False, {"type": "audio", "message": "Failed to query audio devices."}
            
        try:
            # Extract JSON from stdout (ignoring initial loading bars etc.)
            json_start = stdout.find('{')
            json_end = stdout.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found")
            data = json.loads(stdout[json_start:json_end])
            
            current_id = data.get("current")
            devices = data.get("devices", [])
            if isinstance(devices, dict):  # ConvertTo-Json behavior with 1 item
                devices = [devices]
        except Exception as e:
            logger.error(f"Failed to parse audio devices JSON: {e}\nStdout: {stdout}")
            return False, {"type": "audio", "message": "Failed to parse audio devices."}

        # 2. Filter real devices
        real_devices = [
            d for d in devices
            if not re.search(r"(?i)fxsound|steam|nvidia|virtual|enhancer|ddk", d.get("Name", ""))
        ]

        selected_device = None
        if target == "headphone":
            for d in real_devices:
                if re.search(r"(?i)head|ear|headset|buds|usb", d.get("Name", "")):
                    selected_device = d
                    break
        elif target == "speaker":
            speakers = [
                d for d in real_devices
                if re.search(r"(?i)speaker|line out|high definition audio|realtek", d.get("Name", ""))
                and not re.search(r"(?i)digital|hdmi|head|ear|headset|buds|usb", d.get("Name", ""))
            ]
            
            if speakers:
                # Prefer current if it's already a suitable speaker to avoid needless switching
                for s in speakers:
                    if s.get("ID") == current_id:
                        selected_device = s
                        break
                
                # Otherwise, prefer non-digital
                if not selected_device:
                    for s in speakers:
                        if not re.search(r"(?i)digital|hdmi", s.get("Name", "")):
                            selected_device = s
                            break
                            
                # Fallback to first
                if not selected_device:
                    selected_device = speakers[0]

        if not selected_device:
            return False, {"type": "audio", "message": f"Could not find a suitable {target}."}

        if selected_device.get("ID") == current_id:
            logger.info(f"Already using target audio device: {selected_device.get('Name')}")
            return True, {"type": "audio", "message": f"Already using {selected_device.get('Name')}."}

        # 3. Switch device
        logger.info(f"Switching audio output to: {selected_device.get('Name')}")
        switch_cmd = f"Import-Module AudioDeviceCmdlets; Set-AudioDevice -Index {selected_device.get('Index')}"
        s_success, s_stdout, s_stderr = self._run_command(["powershell", "-NoProfile", "-Command", switch_cmd])
        
        if not s_success:
            logger.error(f"Failed to switch to {selected_device.get('Name')}: {s_stderr}")
            return False, {"type": "audio", "message": "Failed to execute switch command."}
            
        return True, {"type": "audio", "message": f"Switched audio to {selected_device.get('Name')}."}

    async def turn_off_screen(self) -> tuple[bool, Optional[dict]]:
        """Turn off displays using NirCmd."""
        if not self.nircmd_path or not self.nircmd_path.exists():
            logger.error("NirCmd not available for monitor control")
            return False, {"type": "display", "message": "nircmd.exe not found."}
        success, _, stderr = self._run_command(
            [str(self.nircmd_path), "monitor", "off"]
        )
        if not success:
            logger.error(f"Failed to turn off screen: {stderr}")
            return False, {"type": "display", "message": "Failed to turn off screen."}
        return True, {"type": "display", "message": "Screen turned off."}

    async def get_battery_status(self) -> tuple[bool, Optional[dict]]:
        """Fetch laptop battery status."""
        script = (
            "Get-WmiObject -Class Win32_Battery "
            "| Select-Object EstimatedChargeRemaining,BatteryStatus "
            "| ConvertTo-Json"
        )
        success, stdout, stderr = self._run_command(
            ["powershell", "-NoProfile", "-Command", script]
        )
        if not success:
            logger.error(f"Failed to read battery info: {stderr}")
            return False, {"type": "battery_status", "message": "Unable to read battery info."}
        if not stdout:
            logger.warning("Battery information unavailable (desktop or no battery).")
            return False, {"type": "battery_status", "message": "No battery detected."}

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            logger.error(f"Battery JSON parse error: {e}")
            return False, {"type": "battery_status", "message": "Invalid battery data."}

        if isinstance(data, list):
            data = data[0] if data else None
        if not data:
            return False, {"type": "battery_status", "message": "Battery data unavailable."}

        percent = data.get("EstimatedChargeRemaining")
        status_code = data.get("BatteryStatus")
        status_text = POWER_STATUS_MAP.get(status_code, "Unknown")
        if percent is None:
            return False, {"type": "battery_status", "message": "Battery percentage not reported."}

        message = f"Battery at {int(percent)}% ({status_text.lower()})."
        payload = {
            "type": "battery_status",
            "percentage": int(percent),
            "status_code": status_code,
            "status_text": status_text,
            "message": message,
        }
        return True, payload

    async def get_cpu_usage(self) -> tuple[bool, Optional[dict]]:
        """Get CPU usage percentage via Get-Counter."""
        script = (
            "(Get-Counter '\\Processor(_Total)\\% Processor Time' "
            "-SampleInterval 1 -MaxSamples 1).CounterSamples[0].CookedValue"
        )
        success, stdout, stderr = self._run_command(
            ["powershell", "-NoProfile", "-Command", script]
        )
        if not success:
            logger.error(f"Failed to read CPU usage: {stderr}")
            return False, {"type": "cpu_status", "message": "Unable to read CPU usage."}
        try:
            value = float(stdout.strip())
        except (TypeError, ValueError):
            logger.error(f"Invalid CPU usage output: {stdout}")
            return False, {"type": "cpu_status", "message": "CPU usage unavailable."}

        value = max(0.0, min(100.0, value))
        message = f"CPU usage is {value:.1f}%."
        return True, {"type": "cpu_status", "usage": value, "message": message}

    async def get_gpu_status(self) -> tuple[bool, Optional[dict]]:
        """Get GPU utilization using nvidia-smi."""
        executable = str(self.nvidia_smi_path) if self.nvidia_smi_path else "nvidia-smi"
        command = [
            executable,
            "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total",
            "--format=csv,noheader",
        ]
        success, stdout, stderr = self._run_command(command)
        if not success or not stdout:
            logger.error(f"Failed to query GPU: {stderr}")
            return False, {"type": "gpu_status", "message": "Unable to read GPU stats."}

        try:
            parts = [part.strip() for part in stdout.split(",")]
            util = int(parts[0].split()[0])
            temp = int(parts[1].split()[0])
            mem_used = int(parts[2].split()[0])
            mem_total = int(parts[3].split()[0])
        except (IndexError, ValueError) as e:
            logger.error(f"GPU output parse error: {e} -> {stdout}")
            return False, {"type": "gpu_status", "message": "Invalid GPU stats output."}

        message = (
            f"GPU at {util}% load, {temp}°C, "
            f"{mem_used}/{mem_total} MiB VRAM used."
        )
        payload = {
            "type": "gpu_status",
            "utilization": util,
            "temperature": temp,
            "memory_used": mem_used,
            "memory_total": mem_total,
            "message": message,
        }
        return True, payload


# Global instance
_system_controller: Optional[SystemController] = None


def get_system_controller() -> SystemController:
    """Get or create global system controller"""
    global _system_controller
    if _system_controller is None:
        _system_controller = SystemController()
    return _system_controller
