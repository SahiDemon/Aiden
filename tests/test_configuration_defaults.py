from src.utils.config import APIConfig, ESP32Config, SpeechConfig, UPSConfig


def test_fresh_configuration_keeps_commands_local_and_hardware_opt_in(monkeypatch):
    for name in (
        "API_HOST", "ESP32_ENABLED", "UPS_ENABLED", "SPEECH_USE_PORCUPINE",
        "SPEECH_INPUT_DEVICE_NAME",
    ):
        monkeypatch.delenv(name, raising=False)

    assert APIConfig(_env_file=None).host == "localhost"
    assert ESP32Config(_env_file=None).enabled is False
    assert UPSConfig(_env_file=None).enabled is False
    speech = SpeechConfig(_env_file=None)
    assert speech.use_porcupine is False
    assert speech.input_device_name == ""


def test_explicit_configuration_can_enable_existing_integrations():
    assert APIConfig(_env_file=None, host="127.0.0.1").host == "127.0.0.1"
    assert ESP32Config(_env_file=None, enabled=True).enabled is True
    assert UPSConfig(_env_file=None, enabled=True).enabled is True
    assert SpeechConfig(_env_file=None, use_porcupine=True).use_porcupine is True
