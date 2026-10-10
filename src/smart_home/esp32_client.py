"""
ESP32 Smart Home Client
Metadata-driven runtime control for ESP32 smart devices.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import httpx

from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _stringify(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _extract_message(data: Any) -> str:
    if isinstance(data, dict):
        return _stringify(data.get("message")) or ""
    if isinstance(data, str):
        return data
    return ""


class ESP32Client:
    """ESP32 smart home controller with retry logic and normalized runtime state."""

    def __init__(self):
        self.settings = get_settings()
        self.enabled = self.settings.esp32.enabled
        self.ip_address = self.settings.esp32.ip_address
        self.timeout = self.settings.esp32.timeout
        self.retry_attempts = self.settings.esp32.retry_attempts
        self.base_url = f"http://{self.ip_address}"
        self.client = httpx.AsyncClient(timeout=self.timeout)

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Make an HTTP request to the ESP32 with retry logic."""
        if not self.enabled:
            logger.warning("ESP32 is disabled in configuration")
            return {"success": False, "error": "ESP32 disabled"}

        retries = retries or self.retry_attempts
        url = f"{self.base_url}{endpoint}"

        for attempt in range(retries):
            try:
                logger.debug(
                    "ESP32 %s request to %s (attempt %s/%s)",
                    method,
                    url,
                    attempt + 1,
                    retries,
                )
                response = await self.client.request(method, url, json=json_body)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    payload: Any = response.json()
                else:
                    payload = response.text

                return {
                    "success": True,
                    "status_code": response.status_code,
                    "data": payload,
                }
            except httpx.TimeoutException:
                logger.warning("ESP32 request timeout (attempt %s/%s)", attempt + 1, retries)
                if attempt < retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                return {"success": False, "error": "Timeout"}
            except httpx.HTTPStatusError as exc:
                logger.error("ESP32 HTTP error for %s %s: %s", method, url, exc.response.status_code)
                error_text = exc.response.text
                try:
                    error_payload = exc.response.json()
                except ValueError:
                    error_payload = error_text
                return {
                    "success": False,
                    "error": f"HTTP {exc.response.status_code}",
                    "status_code": exc.response.status_code,
                    "data": error_payload,
                }
            except httpx.RequestError as exc:
                logger.warning("ESP32 connection error (attempt %s/%s): %s", attempt + 1, retries, exc)
                if attempt < retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                return {"success": False, "error": "Connection failed"}
            except Exception as exc:
                logger.error("Unexpected ESP32 error: %s", exc)
                return {"success": False, "error": str(exc)}

        return {"success": False, "error": "Max retries exceeded"}

    @staticmethod
    def _normalize_steps(control: Dict[str, Any]) -> list[Dict[str, Optional[str]]]:
        steps = control.get("steps") or []
        normalized_steps: list[Dict[str, Optional[str]]] = []
        for step in steps:
            key = _stringify(step.get("key"))
            normalized_steps.append(
                {
                    "key": key,
                    "label": _stringify(step.get("label")) or key,
                }
            )
        return normalized_steps

    @staticmethod
    def _value_label(steps: list[Dict[str, Optional[str]]], value: Optional[str]) -> Optional[str]:
        for step in steps:
            if step.get("key") == value:
                return step.get("label") or value
        return value

    @classmethod
    def normalize_device_snapshot(
        cls,
        config: Dict[str, Any],
        state: Dict[str, Any],
        ip_address: str,
    ) -> Dict[str, Any]:
        """Normalize live ESP32 config + state into a stable dashboard payload."""
        config_controls = config.get("controls") or []
        state_controls = state.get("controls") or {}

        normalized_controls = []
        for index, control in enumerate(config_controls):
            control_id = _stringify(control.get("id"))
            if not control_id:
                continue

            state_control = state_controls.get(control_id, {})
            steps = cls._normalize_steps(control)
            value = _stringify(state_control.get("value"))
            normalized_controls.append(
                {
                    "id": control_id,
                    "label": _stringify(control.get("label")) or control_id,
                    "alias": _stringify(control.get("alias")) or control_id,
                    "kind": _stringify(control.get("kind")) or "raw",
                    "feature": _stringify(control.get("feature")) or control_id,
                    "stateful": bool(control.get("stateful", False)),
                    "steps": steps,
                    "value": value,
                    "value_label": cls._value_label(steps, value),
                    "updated_at": state_control.get("updatedAt"),
                    "order": index,
                }
            )

        summary = {
            "state": ((_stringify((state_controls.get("power") or {}).get("value")) or "unknown").lower()),
            "speed": _stringify((state_controls.get("speed") or {}).get("value")),
            "timer": _stringify((state_controls.get("timer") or {}).get("value")),
            "mode": _stringify((state_controls.get("mode") or {}).get("value")),
            "osc": _stringify((state_controls.get("osc") or {}).get("value")),
        }

        return {
            "device_name": _stringify(config.get("deviceName"))
            or _stringify(state.get("deviceName"))
            or "ESP32 Device",
            "ip_address": ip_address,
            "controls": normalized_controls,
            "summary": summary,
            "raw_state": state,
            "raw_config": config,
        }

    @staticmethod
    def _find_control(snapshot: Dict[str, Any], control_id: str) -> Optional[Dict[str, Any]]:
        for control in snapshot.get("controls", []):
            if control.get("id") == control_id:
                return control
        return None

    async def get_config(self) -> Dict[str, Any]:
        result = await self._request("GET", "/api/config", retries=1)
        if not result.get("success") or not isinstance(result.get("data"), dict):
            return {}
        return result["data"]

    async def get_state(self) -> Dict[str, Any]:
        result = await self._request("GET", "/api/state", retries=1)
        if not result.get("success") or not isinstance(result.get("data"), dict):
            return {}
        return result["data"]

    async def get_runtime_power_state(self) -> str:
        """Read the raw power state directly from /api/state even if config fetch fails."""
        state = await self.get_state()
        controls = state.get("controls") or {}
        power = controls.get("power") or {}
        return ((_stringify(power.get("value")) or "unknown").lower())

    @staticmethod
    def _is_network_unreachable_error(result: Dict[str, Any]) -> bool:
        error = str(result.get("error") or "").lower()
        return error in {"timeout", "connection failed", "max retries exceeded"}

    async def get_device_snapshot(self) -> Dict[str, Any]:
        config, state = await asyncio.gather(self.get_config(), self.get_state())
        return self.normalize_device_snapshot(config, state, self.ip_address)

    async def _blind_set_control(self, control_id: str, target: str) -> Dict[str, Any]:
        """Attempt an exact runtime control write without requiring cached metadata."""
        result = await self._request(
            "POST",
            "/api/actions/set",
            json_body={"controlId": control_id, "target": target},
        )
        if not result.get("success"):
            return result

        updated_snapshot = await self.get_device_snapshot()
        message = _extract_message(result.get("data"))

        return {
            "success": True,
            "message": message or f"{control_id} updated",
            "device": updated_snapshot,
            "control_id": control_id,
            "target": target,
        }

    async def _verify_power_target_result(
        self,
        result: Dict[str, Any],
        target: str,
    ) -> Dict[str, Any]:
        """
        Confirm power commands against runtime state so we don't claim success
        when the device route failed and only a weak fallback responded.
        """
        runtime_state = await self.get_runtime_power_state()
        if runtime_state == target:
            updated_snapshot = await self.get_device_snapshot()
            result["device"] = updated_snapshot
            if "already" in (result.get("message") or "").lower():
                result["message"] = f"The fan is already {target}."
            elif not result.get("message") or result.get("message") == f"power updated":
                result["message"] = "Turning the fan on." if target == "on" else "Turning the fan off."
            return result

        logger.warning(
            "ESP32 power verification failed: requested=%s runtime_state=%s message=%s",
            target,
            runtime_state,
            result.get("message"),
        )
        return {
            "success": False,
            "error": f"Fan did not confirm {target} state after command.",
            "control_id": "power",
            "target": target,
            "device": result.get("device"),
        }

    async def _resync_control_state(self, control_id: str, value: str) -> Dict[str, Any]:
        """Update the ESP32 runtime state cache to a specific value."""
        return await self._request(
            "POST",
            "/api/state/resync",
            json_body={"controlId": control_id, "value": value},
        )

    async def _recover_power_desync(self, target: str) -> Dict[str, Any]:
        """
        Recover from stale power state by sending one raw toggle, then forcing
        the ESP32 runtime cache back to the user's requested target.
        """
        toggle_result = await self.force_toggle("power")
        if not toggle_result.get("success"):
            return toggle_result

        resync_result = await self._resync_control_state("power", target)
        if not resync_result.get("success"):
            return resync_result

        updated_snapshot = await self.get_device_snapshot()
        return {
            "success": True,
            "message": f"Power state resynced to {target}.",
            "device": updated_snapshot,
            "control_id": "power",
            "target": target,
        }

    @staticmethod
    def _build_power_noop_result(target: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": True,
            "message": f"The fan is already {target}.",
            "device": snapshot,
            "control_id": "power",
            "target": target,
        }

    async def _try_direct_shortcut_first(
        self,
        *,
        control_id: Optional[str] = None,
        target: Optional[str] = None,
        action: Optional[str] = None,
        legacy_action: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Prefer the ESP32 shortcut routes for simple fan commands that should
        always send an immediate IR signal instead of relying on cached state.
        """
        wants_direct_shortcut = False

        if legacy_action and legacy_action.lower() in {"turn_on", "on", "turn_off", "off", "stop", "change_mode", "mode", "switch_mode"}:
            wants_direct_shortcut = True
        elif control_id == "power" and target is not None and str(target) in {"on", "off"}:
            wants_direct_shortcut = True
        elif control_id == "mode" and action and action.lower() == "cycle":
            wants_direct_shortcut = True

        if not wants_direct_shortcut:
            return None

        result = await self._direct_control_fallback(
            control_id=control_id,
            target=target,
            action=action,
            legacy_action=legacy_action,
        )
        if result.get("success"):
            return result

        logger.warning(
            "Direct ESP32 shortcut path failed for control_id=%s target=%s action=%s legacy_action=%s; falling back to runtime API",
            control_id,
            target,
            action,
            legacy_action,
        )
        return None

    async def direct_toggle(self, path: str) -> Dict[str, Any]:
        """
        Fire a single GET request to a shortcut path on the ESP32 and return
        immediately — no state pre-check, no post-verification snapshot.

        This is the fastest possible fan command path:
          await client.direct_toggle("/power")   # ~50-200 ms on LAN
          await client.direct_toggle("/speed/3")

        Returns success=True as long as the device responded with 2xx.
        """
        # A toggle can have taken effect even when its response times out.
        # Retrying it could undo the requested change.
        result = await self._request("GET", path, retries=1 if path == "/power" else None)
        if not result.get("success"):
            return result

        message = _extract_message(result.get("data")) or "Done."
        return {
            "success": True,
            "message": message,
            "path": path,
        }

    async def _direct_control_fallback(
        self,
        *,
        control_id: Optional[str] = None,
        target: Optional[str] = None,
        action: Optional[str] = None,
        legacy_action: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fallback to direct ESP32 shortcut routes when metadata is unavailable."""
        endpoint: Optional[str] = None

        if legacy_action:
            alias = legacy_action.lower()
            if alias in {"turn_on", "on"}:
                endpoint = "/on"
            elif alias in {"turn_off", "off", "stop"}:
                endpoint = "/off"
            elif alias in {"change_mode", "mode", "switch_mode"}:
                endpoint = "/mode"

        if endpoint is None and control_id and target is not None:
            normalized_target = str(target)
            if control_id == "power" and normalized_target in {"on", "off"}:
                endpoint = f"/{normalized_target}"
            elif control_id in {"speed", "timer", "mode", "osc"}:
                endpoint = f"/{control_id}/{normalized_target}"
            elif control_id:
                endpoint = f"/{control_id}/{normalized_target}"

        if endpoint is None and control_id and action:
            normalized_action = action.lower()
            if control_id == "mode" and normalized_action == "cycle":
                endpoint = "/mode"
            elif control_id == "power" and normalized_action == "toggle":
                endpoint = "/power/on"

        if endpoint is None:
            return {"success": False, "error": "No direct fallback route available"}

        result = await self._request("GET", endpoint)
        if not result.get("success"):
            return result

        updated_snapshot = await self.get_device_snapshot()
        message = _extract_message(result.get("data"))

        return {
            "success": True,
            "message": message or "ESP32 command sent",
            "device": updated_snapshot,
            "control_id": control_id,
            "target": target,
        }

    async def check_connection(self) -> bool:
        result = await self._request("GET", "/api/state", retries=1)
        return result.get("success", False)

    async def resolve_relative_action(
        self,
        control_id: str,
        action: str,
        snapshot: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Resolve a relative control action into an exact step target."""
        snapshot = snapshot or await self.get_device_snapshot()
        control = self._find_control(snapshot, control_id)
        if not control:
            return None

        steps = control.get("steps") or []
        values = [step["key"] for step in steps if step.get("key") is not None]
        if not values:
            return None

        current_value = control.get("value")
        try:
            current_index = values.index(current_value)
        except ValueError:
            current_index = -1

        normalized_action = action.lower()
        if normalized_action == "toggle":
            if len(values) >= 2 and current_index != -1:
                return values[1] if current_index == 0 else values[0]
            return None

        if normalized_action == "cycle":
            if current_index == -1:
                return values[0]
            return values[(current_index + 1) % len(values)]

        if normalized_action == "increase":
            if current_index == -1:
                return values[0]
            return values[min(current_index + 1, len(values) - 1)]

        if normalized_action == "decrease":
            if current_index == -1:
                return values[-1]
            return values[max(current_index - 1, 0)]

        return None

    async def set_control(self, control_id: str, target: str) -> Dict[str, Any]:
        """Set a control to an exact target value using the ESP32 runtime API."""
        snapshot = await self.get_device_snapshot()
        control = self._find_control(snapshot, control_id)
        if not control:
            logger.warning("ESP32 metadata missing control '%s'; trying blind API set", control_id)
            blind_result = await self._blind_set_control(control_id, target)
            if blind_result.get("success"):
                return blind_result

            logger.warning(
                "Blind API set failed for control '%s' target '%s'; trying direct fallback",
                control_id,
                target,
            )
            return await self._direct_control_fallback(control_id=control_id, target=target)

        allowed_values = [step["key"] for step in control.get("steps", []) if step.get("key") is not None]
        if allowed_values and target not in allowed_values:
            return {
                "success": False,
                "error": f"Invalid target '{target}' for control '{control_id}'",
                "allowed_targets": allowed_values,
            }

        result = await self._request(
            "POST",
            "/api/actions/set",
            json_body={"controlId": control_id, "target": target},
        )
        if not result.get("success"):
            return result

        updated_snapshot = await self.get_device_snapshot()
        message = _extract_message(result.get("data"))

        return {
            "success": True,
            "message": message or f"{control.get('label', control_id)} updated",
            "device": updated_snapshot,
            "control_id": control_id,
            "target": target,
        }

    async def force_toggle(self, control_id: str) -> Dict[str, Any]:
        result = await self._request(
            "POST",
            "/api/actions/force-toggle",
            json_body={"controlId": control_id},
        )
        if not result.get("success"):
            return result

        updated_snapshot = await self.get_device_snapshot()
        message = _extract_message(result.get("data"))

        return {
            "success": True,
            "message": message or f"{control_id} toggled",
            "device": updated_snapshot,
            "control_id": control_id,
        }

    async def execute_control_request(
        self,
        *,
        control_id: Optional[str] = None,
        target: Optional[str] = None,
        action: Optional[str] = None,
        legacy_action: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a generic or legacy fan control request."""
        requested_power_target: Optional[str] = None
        if legacy_action:
            alias = legacy_action.lower()
            if alias in {"turn_on", "on"}:
                requested_power_target = "on"
            elif alias in {"turn_off", "off", "stop"}:
                requested_power_target = "off"
        elif control_id == "power" and target is not None and str(target).lower() in {"on", "off"}:
            requested_power_target = str(target).lower()

        snapshot: Optional[Dict[str, Any]] = None
        if requested_power_target is not None:
            snapshot = await self.get_device_snapshot()
            current_state = await self.get_runtime_power_state()
            if current_state == requested_power_target:
                return self._build_power_noop_result(requested_power_target, snapshot)

        direct_result = await self._try_direct_shortcut_first(
            control_id=control_id,
            target=str(target) if target is not None else None,
            action=action,
            legacy_action=legacy_action,
        )
        if direct_result is not None:
            if requested_power_target is not None and direct_result.get("success"):
                return await self._verify_power_target_result(direct_result, requested_power_target)
            return direct_result
        if requested_power_target is not None and direct_result is None:
            # If the direct route already burned through retries because the device
            # is unreachable, stop here instead of stacking more timeouts from
            # config/state lookups and blind fallback requests.
            health_check = await self._request("GET", "/api/state", retries=1)
            if self._is_network_unreachable_error(health_check):
                return {
                    "success": False,
                    "error": "ESP32 device is not responding.",
                    "control_id": "power",
                    "target": requested_power_target,
                }

        snapshot = snapshot or await self.get_device_snapshot()

        if legacy_action:
            alias = legacy_action.lower()
            if alias in {"turn_on", "on"}:
                control_id = "power"
                target = "on"
            elif alias in {"turn_off", "off", "stop"}:
                control_id = "power"
                target = "off"
            elif alias in {"change_mode", "mode", "switch_mode"}:
                control_id = "mode"
                action = "cycle"
            elif alias in {"increase", "speed_up", "faster"}:
                control_id = "speed"
                action = "increase"
            elif alias == "high":
                control_id = "speed"
                speed_control = self._find_control(snapshot, "speed")
                speed_steps = speed_control.get("steps", []) if speed_control else []
                if speed_steps:
                    target = speed_steps[-1]["key"]
            elif alias == "toggle":
                control_id = "power"
                action = "toggle"
            else:
                return {"success": False, "error": f"Unsupported legacy action: {legacy_action}"}

            if not self._find_control(snapshot, control_id):
                logger.warning(
                    "ESP32 metadata unavailable for legacy action '%s'; trying metadata-free set path",
                    legacy_action,
                )
                if target is not None:
                    result = await self.set_control(control_id, str(target))
                    if result.get("success"):
                        return result
                return await self._direct_control_fallback(
                    control_id=control_id,
                    target=target,
                    action=action,
                    legacy_action=legacy_action,
                )

        if not control_id:
            return {"success": False, "error": "control_id is required"}

        if target is not None:
            result = await self.set_control(control_id, str(target))
            if control_id == "power" and str(target) in {"on", "off"} and result.get("success"):
                return await self._verify_power_target_result(result, str(target))
            if (
                legacy_action
                and control_id == "power"
                and str(target) in {"on", "off"}
                and result.get("success")
                and "already matches" in (result.get("message") or "").lower()
            ):
                logger.warning(
                    "ESP32 reported power already '%s' during legacy request; attempting desync recovery",
                    target,
                )
                return await self._recover_power_desync(str(target))
            return result

        if not action:
            return {"success": False, "error": "Either target or action is required"}

        resolved_target = await self.resolve_relative_action(control_id, action, snapshot=snapshot)
        if resolved_target is not None:
            return await self.set_control(control_id, resolved_target)

        if action.lower() == "toggle":
            return await self.force_toggle(control_id)

        return {
            "success": False,
            "error": f"Unable to resolve action '{action}' for control '{control_id}'",
        }

    async def get_status(self) -> Dict[str, Any]:
        """Compatibility status payload used by older backend/dashboard code."""
        snapshot = await self.get_device_snapshot()
        summary = snapshot.get("summary", {})
        return {
            "state": summary.get("state", "unknown"),
            "speed": summary.get("speed"),
            "timer": summary.get("timer"),
            "mode": summary.get("mode"),
            "osc": summary.get("osc"),
            "device_name": snapshot.get("device_name"),
        }

    async def turn_on(self) -> tuple[bool, Optional[str]]:
        result = await self.execute_control_request(legacy_action="turn_on")
        return result.get("success", False), result.get("message")

    async def turn_off(self) -> tuple[bool, Optional[str]]:
        result = await self.execute_control_request(legacy_action="turn_off")
        return result.get("success", False), result.get("message")

    async def toggle(self) -> tuple[bool, Optional[str]]:
        result = await self.execute_control_request(legacy_action="toggle")
        return result.get("success", False), result.get("message")

    async def change_mode(self) -> tuple[bool, Optional[str]]:
        result = await self.execute_control_request(legacy_action="change_mode")
        return result.get("success", False), result.get("message")

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()


_esp32_client: Optional[ESP32Client] = None


async def get_esp32_client() -> ESP32Client:
    """Get or create global ESP32 client."""
    global _esp32_client
    if _esp32_client is None:
        _esp32_client = ESP32Client()
    return _esp32_client


async def close_esp32_client():
    """Close global ESP32 client."""
    global _esp32_client
    if _esp32_client:
        await _esp32_client.close()
        _esp32_client = None
