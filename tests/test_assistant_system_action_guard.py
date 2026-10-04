from src.core.assistant import (
    _keep_delayed_close_as_one_action,
    _validated_ai_commands,
    infer_delayed_close_command,
    remove_unrequested_system_commands,
)


def test_blocks_unrequested_delayed_lock_action():
    commands = [
        {
            "type": "scheduled_command",
            "params": {"action": "lock", "duration_seconds": 60},
        }
    ]

    allowed, blocked = remove_unrequested_system_commands("Close Notepad in one minute", commands)

    assert allowed == []
    assert blocked == ["lock"]


def test_allows_explicit_delayed_lock_action():
    commands = [
        {
            "type": "scheduled_command",
            "params": {"action": "lock", "duration_seconds": 60},
        }
    ]

    allowed, blocked = remove_unrequested_system_commands("Lock my computer in one minute", commands)

    assert allowed == commands
    assert blocked == []


def test_recovers_delayed_close_as_a_process_command():
    command = infer_delayed_close_command("Close Notepad in one minute")

    assert command == {
        "type": "scheduled_command",
        "params": {
            "duration_seconds": 60,
            "command": {"type": "kill_process", "params": {"name": "notepad"}},
        },
    }


def test_spoken_correction_uses_last_affirmative_time():
    command = infer_delayed_close_command(
        "Close Spotify after 5 minutes. No, no, 1 minute. Not 5 minutes, only 1 minute."
    )

    assert command["params"]["duration_seconds"] == 60
    assert command["params"]["command"]["params"]["name"] == "spotify"


def test_delayed_close_replaces_split_ai_plan_before_execution():
    raw_plan = [
        {"type": "kill_process", "params": {"name": "spotify.exe"}},
        {"type": "scheduled_command", "params": {"action": "close", "duration_seconds": 60}},
    ]

    commands, reply = _keep_delayed_close_as_one_action(
        "Close Spotify after one minute", _validated_ai_commands(raw_plan)
    )

    assert commands == [infer_delayed_close_command("Close Spotify after one minute")]
    assert reply == "I'll close Spotify in 1 minute."


def test_delayed_close_does_not_absorb_a_second_explicit_action():
    assert infer_delayed_close_command(
        "Close Spotify after one minute and turn off the fan"
    ) is None


def test_followup_command_cannot_exit_or_restart_aiden_without_request():
    commands = [
        {"type": "self_termination", "params": {}},
        {"type": "restart_application", "params": {}},
    ]

    allowed, blocked = remove_unrequested_system_commands(
        "Play Friends on Jellyfin", commands
    )

    assert allowed == []
    assert blocked == ["exit Aiden", "restart Aiden"]


def test_explicit_aiden_restart_is_still_allowed():
    command = {"type": "restart_application", "params": {}}

    allowed, blocked = remove_unrequested_system_commands(
        "Restart yourself", [command]
    )

    assert allowed == [command]
    assert blocked == []

