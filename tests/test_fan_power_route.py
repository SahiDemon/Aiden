import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.execution.command_executor import CommandExecutor


def test_explicit_fan_off_uses_off_route_and_preserves_target():
    executor = CommandExecutor.__new__(CommandExecutor)
    client = SimpleNamespace(direct_toggle=AsyncMock(return_value={
        "success": True, "message": "Signal sent.",
    }))
    executor.esp32_client = client

    success, payload = asyncio.run(executor._handle_fan_control({"operation": "off"}))

    assert success
    client.direct_toggle.assert_awaited_once_with("/off")
    assert payload["control_id"] == "power"
    assert payload["target"] == "off"
