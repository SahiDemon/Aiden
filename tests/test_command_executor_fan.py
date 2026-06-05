from src.execution.command_executor import CommandExecutor


def test_fan_control_requires_post_response():
    executor = CommandExecutor()
    assert executor.command_requires_post_response({"type": "fan_control", "params": {"operation": "off"}}) is True
