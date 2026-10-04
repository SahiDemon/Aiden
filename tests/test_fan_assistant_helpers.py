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


def test_jellyfin_shortcut_never_claims_an_explicit_spotify_request():
    assert extract_jellyfin_movie_request("Can you play Bad News by Aries on Spotify?") is None
    assert extract_jellyfin_movie_request("play something on Spotify using speakers") is None
    assert extract_jellyfin_movie_request("play Arrival on Jellyfin") == "Arrival"
