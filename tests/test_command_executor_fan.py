from src.execution.command_executor import CommandExecutor


def test_fan_control_requires_post_response():
    executor = CommandExecutor()
    # fan_control uses the optimistic fast-path (speaks immediately, appends
    # failure message only if ESP32 rejects the command) — so it does NOT
    # require a blocking post-response wait.
    assert executor.command_requires_post_response({"type": "fan_control", "params": {"operation": "off"}}) is False
