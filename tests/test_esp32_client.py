from unittest.mock import AsyncMock

import pytest

from src.smart_home.esp32_client import ESP32Client


@pytest.fixture
def sample_config():
    return {
        "deviceName": "Fan Remote",
        "controls": [
            {
                "id": "power",
                "label": "Power",
                "alias": "power",
                "kind": "toggle",
                "feature": "power",
                "stateful": True,
                "steps": [{"key": "off", "label": "Off"}, {"key": "on", "label": "On"}],
            },
            {
                "id": "speed",
                "label": "Speed",
                "alias": "speed",
                "kind": "cycle",
                "feature": "speed",
                "stateful": True,
                "steps": [
                    {"key": "1", "label": "Speed 1"},
                    {"key": "2", "label": "Speed 2"},
                    {"key": "3", "label": "Speed 3"},
                ],
            },
            {
                "id": "timer",
                "label": "Timer",
                "alias": "timer",
                "kind": "cycle",
                "feature": "timer",
                "stateful": True,
                "steps": [
                    {"key": "0.5", "label": "0.5h"},
                    {"key": "1", "label": "1h"},
                    {"key": "7.5", "label": "7.5h"},
                    {"key": "off", "label": "Timer Off"},
                ],
            },
            {
                "id": "mode",
                "label": "Mode",
                "alias": "mode",
                "kind": "cycle",
                "feature": "mode",
                "stateful": True,
                "steps": [
                    {"key": "normal", "label": "Normal"},
                    {"key": "nature", "label": "Nature"},
                    {"key": "sleep", "label": "Sleep"},
                ],
            },
            {
                "id": "osc",
                "label": "Oscillation",
                "alias": "osc",
                "kind": "toggle",
                "feature": "osc",
                "stateful": True,
                "steps": [{"key": "off", "label": "Rotation Off"}, {"key": "on", "label": "Rotation On"}],
            },
        ],
    }


@pytest.fixture
def sample_state():
    return {
        "deviceName": "Fan Remote",
        "controls": {
            "power": {"value": "on", "updatedAt": 1},
            "speed": {"value": "2", "updatedAt": 2},
            "timer": {"value": "1", "updatedAt": 3},
            "mode": {"value": "normal", "updatedAt": 4},
            "osc": {"value": "off", "updatedAt": 5},
        },
    }


def test_normalize_device_snapshot(sample_config, sample_state):
    snapshot = ESP32Client.normalize_device_snapshot(sample_config, sample_state, "192.168.1.180")

    assert snapshot["device_name"] == "Fan Remote"
    assert snapshot["ip_address"] == "192.168.1.180"
    assert snapshot["summary"] == {
        "state": "on",
        "speed": "2",
        "timer": "1",
        "mode": "normal",
        "osc": "off",
    }
    timer_control = next(control for control in snapshot["controls"] if control["id"] == "timer")
    assert timer_control["value"] == "1"
    assert timer_control["value_label"] == "1h"
    assert timer_control["steps"][-1]["key"] == "off"


@pytest.mark.asyncio
async def test_resolve_relative_actions(sample_config, sample_state):
    snapshot = ESP32Client.normalize_device_snapshot(sample_config, sample_state, "192.168.1.180")
    client = ESP32Client()
    client.get_device_snapshot = AsyncMock(return_value=snapshot)

    try:
        assert await client.resolve_relative_action("speed", "increase") == "3"
        assert await client.resolve_relative_action("speed", "decrease") == "1"
        assert await client.resolve_relative_action("mode", "cycle") == "nature"
        assert await client.resolve_relative_action("osc", "toggle") == "on"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_set_control_rejects_invalid_target(sample_config, sample_state):
    snapshot = ESP32Client.normalize_device_snapshot(sample_config, sample_state, "192.168.1.180")
    client = ESP32Client()
    client.get_device_snapshot = AsyncMock(return_value=snapshot)
    client._request = AsyncMock(side_effect=AssertionError("ESP32 write should not be called"))

    try:
        result = await client.set_control("timer", "9")
        assert result["success"] is False
        assert "Invalid target" in result["error"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_legacy_action_falls_back_when_metadata_missing():
    client = ESP32Client()
    client.get_device_snapshot = AsyncMock(
        return_value={
            "device_name": "ESP32 Device",
            "ip_address": "192.168.1.180",
            "controls": [],
            "summary": {"state": "unknown", "speed": None, "timer": None, "mode": None, "osc": None},
        }
    )
    client.get_runtime_power_state = AsyncMock(side_effect=["on", "off"])
    client._request = AsyncMock(return_value={"success": True, "data": {"message": "Cycle target reached."}})

    try:
        result = await client.execute_control_request(legacy_action="off")
        assert result["success"] is True
        client._request.assert_any_await("GET", "/off")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_power_toggle_is_never_retried_after_ambiguous_timeout():
    client = ESP32Client()
    client._request = AsyncMock(return_value={"success": False, "error": "Timeout"})

    try:
        result = await client.direct_toggle("/power")
        assert result["success"] is False
        client._request.assert_awaited_once_with("GET", "/power", retries=1)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_legacy_power_request_prefers_direct_shortcut(sample_config, sample_state):
    snapshot = ESP32Client.normalize_device_snapshot(sample_config, sample_state, "192.168.1.180")

    client = ESP32Client()
    client.get_device_snapshot = AsyncMock(return_value=snapshot)
    client.get_runtime_power_state = AsyncMock(side_effect=["on", "off"])
    client._request = AsyncMock(return_value={"success": True, "data": {"message": "Fan turned off."}})

    try:
        result = await client.execute_control_request(legacy_action="off")
        assert result["success"] is True
        client._request.assert_any_await("GET", "/off")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_exact_power_target_prefers_direct_shortcut(sample_config, sample_state):
    snapshot = ESP32Client.normalize_device_snapshot(sample_config, sample_state, "192.168.1.180")

    client = ESP32Client()
    client.get_device_snapshot = AsyncMock(return_value=snapshot)
    client.get_runtime_power_state = AsyncMock(side_effect=["on", "off"])
    client._request = AsyncMock(return_value={"success": True, "data": {"message": "Fan turned off."}})

    try:
        result = await client.execute_control_request(control_id="power", target="off")
        assert result["success"] is True
        client._request.assert_any_await("GET", "/off")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_power_request_noops_when_target_already_matches(sample_config, sample_state):
    sample_state["controls"]["power"]["value"] = "off"
    snapshot = ESP32Client.normalize_device_snapshot(sample_config, sample_state, "192.168.1.180")

    client = ESP32Client()
    client.get_device_snapshot = AsyncMock(return_value=snapshot)
    client.get_runtime_power_state = AsyncMock(return_value="off")
    client._request = AsyncMock(side_effect=AssertionError("ESP32 should not resend duplicate power command"))

    try:
        result = await client.execute_control_request(control_id="power", target="off")
        assert result["success"] is True
        assert result["message"] == "The fan is already off."
        assert result["device"]["summary"]["state"] == "off"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_power_request_uses_direct_shortcut_when_state_unknown(sample_config, sample_state):
    sample_state["controls"]["power"]["value"] = "unknown"
    snapshot = ESP32Client.normalize_device_snapshot(sample_config, sample_state, "192.168.1.180")

    client = ESP32Client()
    client.get_device_snapshot = AsyncMock(return_value=snapshot)
    client.get_runtime_power_state = AsyncMock(side_effect=["unknown", "off"])
    client._request = AsyncMock(return_value={"success": True, "data": {"message": "Fan turned off."}})

    try:
        result = await client.execute_control_request(control_id="power", target="off")
        assert result["success"] is True
        client._request.assert_any_await("GET", "/off")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_power_set_requires_runtime_state_confirmation(sample_config, sample_state):
    snapshot_before = ESP32Client.normalize_device_snapshot(sample_config, sample_state, "192.168.1.180")
    sample_state["controls"]["power"]["value"] = "off"
    snapshot_after = ESP32Client.normalize_device_snapshot(sample_config, sample_state, "192.168.1.180")

    client = ESP32Client()
    client.get_device_snapshot = AsyncMock(side_effect=[snapshot_before, snapshot_after, snapshot_after])
    client.get_runtime_power_state = AsyncMock(side_effect=["on", "off"])
    client._request = AsyncMock(return_value={"success": True, "data": {"message": "Toggle signal sent."}})

    try:
        result = await client.execute_control_request(control_id="power", target="off")
        assert result["success"] is True
        assert result["device"]["summary"]["state"] == "off"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_power_set_fails_when_runtime_state_does_not_change(sample_config, sample_state):
    snapshot = ESP32Client.normalize_device_snapshot(sample_config, sample_state, "192.168.1.180")

    client = ESP32Client()
    client.get_device_snapshot = AsyncMock(return_value=snapshot)
    client.get_runtime_power_state = AsyncMock(side_effect=["on", "on"])
    client._request = AsyncMock(return_value={"success": True, "data": {"message": "Toggle signal sent."}})

    try:
        result = await client.execute_control_request(control_id="power", target="off")
        assert result["success"] is False
        assert "did not confirm off state" in result["error"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_power_request_fails_fast_when_device_is_unreachable(sample_config, sample_state):
    snapshot = ESP32Client.normalize_device_snapshot(sample_config, sample_state, "192.168.1.180")

    client = ESP32Client()
    client.get_device_snapshot = AsyncMock(return_value=snapshot)
    client.get_runtime_power_state = AsyncMock(return_value="unknown")

    async def fake_request(method, endpoint, **kwargs):
        if endpoint == "/off":
            return {"success": False, "error": "Timeout"}
        if endpoint == "/api/state":
            return {"success": False, "error": "Timeout"}
        raise AssertionError(f"Unexpected follow-up request: {method} {endpoint}")

    client._request = AsyncMock(side_effect=fake_request)

    try:
        result = await client.execute_control_request(control_id="power", target="off")
        assert result["success"] is False
        assert result["error"] == "ESP32 device is not responding."
    finally:
        await client.close()
