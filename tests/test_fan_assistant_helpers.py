from src.core.assistant import build_fan_spoken_response, infer_simple_fan_command


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
        == "I'm trying to turn the fan off."
    )
