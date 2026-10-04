import asyncio
from unittest.mock import AsyncMock

from src.execution.command_executor import CommandExecutor


def test_fan_finishes_before_hibernate():
    executor = CommandExecutor.__new__(CommandExecutor)
    executor.execute = AsyncMock(side_effect=lambda command, conversation_id=None: {
        "command": command["type"], "success": True,
    })
    commands = [
        {"type": "system_command", "params": {"action": "hibernate"}},
        {"type": "fan_control", "params": {"operation": "off"}},
    ]

    results = asyncio.run(executor.execute_multiple(commands))

    assert [call.args[0]["type"] for call in executor.execute.await_args_list] == [
        "fan_control", "system_command",
    ]
    assert [result["command"] for result in results] == ["fan_control", "system_command"]
