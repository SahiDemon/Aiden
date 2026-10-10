import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.core.assistant import (
    AidenAssistant,
    build_fan_spoken_response,
    extract_jellyfin_movie_request,
    infer_simple_fan_command,
)


def test_infer_simple_fan_command_handles_common_variants():
    off_cases = [
        "turn off fan",
        "trun of fan",
        "turn of the fan",
        "switch fan off",
        "fan off",
    ]
    on_cases = [
        "turn on fan",
        "trun on fan",
        "switch the fan on",
        "fan on",
    ]

    for text in off_cases:
        result = infer_simple_fan_command(text)
        assert result is not None
        assert result["commands"][0]["type"] == "fan_control"
        assert result["commands"][0]["params"] == {"control_id": "power", "target": "off"}

    for text in on_cases:
        result = infer_simple_fan_command(text)
        assert result is not None
        assert result["commands"][0]["params"] == {"control_id": "power", "target": "on"}


def test_infer_simple_fan_command_skips_multi_action_requests():
    assert infer_simple_fan_command("turn off fan and lock pc") is None
    assert infer_simple_fan_command("turn off the fan in 10 seconds") is None


def test_fan_recovery_does_not_replace_scheduled_plan():
    assistant = AidenAssistant.__new__(AidenAssistant)
    plan = {"commands": [{"type": "scheduled_command", "params": {
        "duration_seconds": 10,
        "command": {"type": "fan_control", "params": {"operation": "off"}},
    }}]}

    assert assistant._maybe_apply_simple_fan_heuristic("turn off the fan in 10 seconds", plan) is plan


def test_build_fan_spoken_response_is_deterministic():
    assert (
        build_fan_spoken_response(
            {
                "control_id": "power",
                "target": "off",
                "message": "The fan is already off.",
            }
        )
        == "The fan is already off."
    )
    assert (
        build_fan_spoken_response(
            {
                "control_id": "power",
                "target": "on",
                "message": "Toggle signal sent.",
                "device": {"summary": {"state": "on"}},
            }
        )
        == "The fan is on."
    )
    assert (
        build_fan_spoken_response(
            {
                "control_id": "speed",
                "target": "2",
                "message": "Speed updated",
            }
        )
        == "Fan speed set to 2."
    )


def test_build_fan_spoken_response_uses_attempt_wording_when_unconfirmed():
    assert (
        build_fan_spoken_response(
            {
                "control_id": "power",
                "target": "off",
                "message": "Command sent.",
                "device": {"summary": {"state": "on"}},
            }
        )
        == "I sent the command to turn the fan off."
    )
    assert build_fan_spoken_response({
        "control_id": "power", "target": "off", "unverified_toggle": True,
        "message": "The fan is already off.",
        "device": {"summary": {"state": "off"}},
    }) == "I sent a power toggle to the fan."


def test_multi_action_reply_does_not_read_raw_esp32_signal():
    assistant = AidenAssistant.__new__(AidenAssistant)
    reply = assistant._response_after_execution(
        "Turning off the fan and hibernating the computer.",
        [
            {"command": "fan_control", "success": True, "response_data": {"message": "Signal sent."}},
            {"command": "system_command", "success": True, "response_data": None},
        ],
    )

    assert reply == "Turning off the fan and hibernating the computer."


def test_multi_action_reply_does_not_append_tool_status_messages():
    assistant = AidenAssistant.__new__(AidenAssistant)
    reply = assistant._response_after_execution(
        "Playing Spotify and setting a shutdown timer for 45 minutes.",
        [
            {"command": "media_control", "success": True,
             "response_data": {"message": "Starting Spotify playback."}},
            {"command": "scheduled_command", "success": True,
             "response_data": "Timer created: shutdown in 2700 seconds"},
        ],
    )

    assert reply == "Playing Spotify and setting a shutdown timer for 45 minutes."


def test_multi_action_reply_keeps_model_language_and_reports_failure():
    assistant = AidenAssistant.__new__(AidenAssistant)
    results = [
        {"command": "media_control", "success": True,
         "response_data": {"message": "Starting Spotify playback."}},
        {"command": "scheduled_command", "success": True,
         "response_data": "Timer created: shutdown in 2700 seconds"},
    ]

    assert assistant._response_after_execution("Spotify चल रहा है और टाइमर लगा दिया है।", results) == (
        "Spotify चल रहा है और टाइमर लगा दिया है।"
    )

    results[1] = {"command": "scheduled_command", "success": False,
                  "params": {"action": "shutdown"}, "response_data": None}
    assert "couldn't set the shutdown timer" in assistant._response_after_execution(
        "Playing Spotify and setting a shutdown timer.", results
    )


def test_partial_failure_reply_uses_user_language_and_keeps_failure():
    assistant = AidenAssistant.__new__(AidenAssistant)
    llm = SimpleNamespace(chat=AsyncMock(return_value={
        "commands": [], "response": "Spotify चल रहा है, लेकिन shutdown timer नहीं लग सका।",
    }))
    results = [
        {"command": "media_control", "success": True, "params": {"action": "play", "target": "spotify"}},
        {"command": "scheduled_command", "success": False, "params": {"action": "shutdown"}},
    ]

    reply = asyncio.run(assistant._localized_failure_reply(
        llm, "Spotify चलाओ और 45 मिनट में shutdown करो",
        "Playing Spotify and setting a shutdown timer.", results,
        "I completed part of that, but couldn't set the shutdown timer.",
    ))

    assert reply == "Spotify चल रहा है, लेकिन shutdown timer नहीं लग सका।"
    assert '"success": false' in llm.chat.await_args.args[0][1]["content"]


def test_jellyfin_shortcut_never_claims_an_explicit_spotify_request():
    assert extract_jellyfin_movie_request("Can you play Bad News by Aries on Spotify?") is None
    assert extract_jellyfin_movie_request("play something on Spotify using speakers") is None
    assert extract_jellyfin_movie_request("play Arrival on Jellyfin") == "Arrival"
