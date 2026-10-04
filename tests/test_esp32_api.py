from unittest.mock import AsyncMock

import httpx
import pytest

import src.api.server as server_module
from src.smart_home.esp32_client import ESP32Client


def build_snapshot():
    return ESP32Client.normalize_device_snapshot(
        {
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
            ],
        },
        {
            "deviceName": "Fan Remote",
            "controls": {
                "power": {"value": "on", "updatedAt": 1},
                "speed": {"value": "2", "updatedAt": 2},
                "timer": {"value": "1", "updatedAt": 3},
            },
        },
        "192.168.1.180",
    )


class FakeESP32Client:
    def __init__(self):
        self.enabled = True
        self.ip_address = "192.168.1.180"
        self.snapshot = build_snapshot()

    async def check_connection(self):
        return True

    async def get_device_snapshot(self):
        return self.snapshot

    async def execute_control_request(self, *, control_id=None, target=None, action=None, legacy_action=None):
        if control_id and target is None and action is None:
            return {"success": False, "error": "Either target or action is required"}

        if control_id == "speed" and target == "3":
            for control in self.snapshot["controls"]:
                if control["id"] == "speed":
                    control["value"] = "3"
                    control["value_label"] = "Speed 3"
            self.snapshot["summary"]["speed"] = "3"
            return {
                "success": True,
                "message": "Speed updated",
                "device": self.snapshot,
                "control_id": control_id,
                "target": target,
            }

        return {"success": False, "error": "Unsupported request"}


@pytest.mark.asyncio
async def test_get_esp32_device(monkeypatch):
    fake_client = FakeESP32Client()
    monkeypatch.setattr(server_module, "get_esp32_client", AsyncMock(return_value=fake_client))

    transport = httpx.ASGITransport(app=server_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/esp32/device")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["connected"] is True
    assert payload["device"]["device_name"] == "Fan Remote"
    assert payload["device"]["summary"]["timer"] == "1"


@pytest.mark.asyncio
async def test_post_esp32_control_updates_device(monkeypatch):
    fake_client = FakeESP32Client()
    monkeypatch.setattr(server_module, "get_esp32_client", AsyncMock(return_value=fake_client))
    broadcast_mock = AsyncMock()
    monkeypatch.setattr(server_module.manager, "broadcast", broadcast_mock)

    transport = httpx.ASGITransport(app=server_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/v1/esp32/control", json={"control_id": "speed", "target": "3"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["device"]["summary"]["speed"] == "3"
    broadcast_mock.assert_awaited()


@pytest.mark.asyncio
async def test_post_esp32_control_rejects_invalid_payload(monkeypatch):
    fake_client = FakeESP32Client()
    monkeypatch.setattr(server_module, "get_esp32_client", AsyncMock(return_value=fake_client))
    monkeypatch.setattr(server_module.manager, "broadcast", AsyncMock())

    transport = httpx.ASGITransport(app=server_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/v1/esp32/control", json={"control_id": "timer"})

    assert response.status_code == 400
    assert "Either target or action is required" in response.json()["detail"]
