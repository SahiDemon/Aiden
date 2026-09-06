"""Tests for personalized wake detection and continuous-command handoff."""

import collections
from types import SimpleNamespace

import numpy as np
import pytest

from src.speech.audio_devices import resolve_input_device_index
from src.speech.openwakeword_wake import OpenWakeWordDetector
from src.speech.stt import STTEngine
from src.speech.wake_detection import WakeDetection, strip_wake_phrase
from src.utils.config import SpeechConfig


@pytest.mark.parametrize(
    ("transcript", "expected"),
    [
        ("Aiden, turn on the light", "turn on the light"),
        ("Hey Aiden play Spotify", "play Spotify"),
        ("okay Aidan, open Steam", "open Steam"),
        ("Ayden! what's the weather", "what's the weather"),
        ("turn on the light", "turn on the light"),
        ("Aiden", ""),
    ],
)
def test_strip_wake_phrase(transcript, expected):
    assert strip_wake_phrase(transcript) == expected


def test_wake_detection_reports_buffered_command():
    detection = WakeDetection("aiden_v2", 0.81, command_audio=b"pcm")
    assert detection.has_command_audio is True


def test_device_name_resolver_ignores_outputs_and_prefers_short_match():
    audio = SimpleNamespace(
        get_device_count=lambda: 4,
        get_device_info_by_index=lambda index: [
            {"name": "Speakers (USB PnP Audio Device)", "maxInputChannels": 0},
            {"name": "Microphone (3- USB PnP Audio Device)", "maxInputChannels": 1},
            {"name": "USB PnP Audio Device", "maxInputChannels": 1},
            {"name": "Steam Streaming Microphone", "maxInputChannels": 8},
        ][index],
    )
    assert resolve_input_device_index("USB PnP Audio Device", audio) == 2
    assert resolve_input_device_index("missing", audio) is None


def test_device_resolver_accepts_truncated_windows_default_name():
    audio = SimpleNamespace(
        get_default_input_device_info=lambda: {
            "index": 1,
            "name": "Microphone (3- USB PnP Audio De",
        },
        get_device_count=lambda: 2,
        get_device_info_by_index=lambda index: {
            "name": "Microphone (USB PnP Audio Device)",
            "maxInputChannels": 1,
        },
    )
    assert resolve_input_device_index("USB PnP Audio Device", audio) == 1


def test_device_resolver_skips_incompatible_windows_endpoint():
    devices = {
        1: {
            "index": 1,
            "name": "Microphone (3- USB PnP Audio De",
            "maxInputChannels": 1,
        },
        50: {
            "index": 50,
            "name": "Microphone (USB PnP Audio Device)",
            "maxInputChannels": 1,
        },
    }

    def supports(_rate, *, input_device, **_kwargs):
        if input_device == 50:
            raise ValueError("Invalid sample rate")
        return True

    audio = SimpleNamespace(
        get_default_input_device_info=lambda: devices[50],
        get_device_count=lambda: 51,
        get_device_info_by_index=lambda index: devices.get(
            index,
            {"name": "output", "maxInputChannels": 0},
        ),
        is_format_supported=supports,
    )

    assert resolve_input_device_index(
        "USB PnP Audio Device",
        audio,
        sample_rate=16_000,
        input_format=8,
    ) == 1


def test_score_smoothing_accepts_two_normal_hits_or_one_strong_hit():
    detector = OpenWakeWordDetector.__new__(OpenWakeWordDetector)
    detector.threshold = 0.50
    detector.strong_threshold = 0.75
    detector.smoothing_window = 3
    detector.smoothing_hits = 2
    detector._score_history = {}

    assert detector._activation_decision("aiden_v2", 0.51) == (False, 1)
    assert detector._activation_decision("aiden_v2", 0.53) == (True, 2)

    detector._score_history.clear()
    assert detector._activation_decision("aiden_v2", 0.80) == (True, 1)


def test_debounce_uses_monotonic_trigger_interval():
    detector = OpenWakeWordDetector.__new__(OpenWakeWordDetector)
    detector._last_trigger_time = 100.0
    detector.debounce = 2.0

    assert detector._is_debounced(101.99) is True
    assert detector._is_debounced(102.0) is False


def test_personal_verifier_replaces_base_score_above_gate():
    detector = OpenWakeWordDetector.__new__(OpenWakeWordDetector)
    detector.verifier_gate = 0.25
    detector._verifier_model = SimpleNamespace(
        predict_proba=lambda _features: np.array([[0.1, 0.9]])
    )
    detector._oww_model = SimpleNamespace(
        get_parent_model_from_label=lambda _label: "aiden_v2",
        model_inputs={"aiden_v2": 16},
        preprocessor=SimpleNamespace(get_features=lambda _size: np.ones((1, 2))),
    )

    assert detector._apply_personal_verifier("aiden_v2", 0.20) == (0.20, None)
    assert detector._apply_personal_verifier("aiden_v2", 0.60) == (0.90, 0.90)


def test_missing_personal_model_rolls_back_to_legacy_policy(tmp_path, monkeypatch):
    fallback = tmp_path / "hey_aiden.onnx"
    fallback.touch()

    class FakeModel:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.models = {"hey_aiden": object()}

    monkeypatch.setattr("openwakeword.model.Model", FakeModel)
    monkeypatch.setattr(
        "src.speech.openwakeword_wake.resource_path",
        lambda *_parts: fallback,
    )
    detector = OpenWakeWordDetector.__new__(OpenWakeWordDetector)
    detector.model_path = str(tmp_path / "missing-aiden-v2.onnx")
    detector.verifier_path = str(tmp_path / "missing-verifier.pkl")
    detector.vad_threshold = 0.2
    detector.threshold = 0.4
    detector.strong_threshold = 0.7
    detector.smoothing_window = 3
    detector.smoothing_hits = 2
    detector._legacy_threshold = 0.5
    detector._legacy_vad_threshold = 0.3
    detector._score_history = {}
    detector._verifier_model = None

    detector._load_model()

    assert detector.model_path == str(fallback)
    assert detector.threshold == 0.5
    assert detector.vad_threshold == 0.3
    assert detector.smoothing_hits == 1
    assert detector._oww_model.kwargs["wakeword_models"] == [str(fallback)]


def test_personal_model_without_verifier_rolls_back(tmp_path, monkeypatch):
    personal = tmp_path / "aiden_v2.onnx"
    fallback = tmp_path / "hey_aiden.onnx"
    personal.touch()
    fallback.touch()

    class FakeModel:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.models = {"hey_aiden": object()}

    monkeypatch.setattr("openwakeword.model.Model", FakeModel)
    monkeypatch.setattr(
        "src.speech.openwakeword_wake.resource_path",
        lambda *_parts: fallback,
    )
    detector = OpenWakeWordDetector.__new__(OpenWakeWordDetector)
    detector.model_path = str(personal)
    detector.verifier_path = ""
    detector.vad_threshold = 0.2
    detector.threshold = 0.4
    detector.strong_threshold = 0.7
    detector.smoothing_window = 3
    detector.smoothing_hits = 2
    detector._legacy_threshold = 0.5
    detector._legacy_vad_threshold = 0.3
    detector._score_history = {}
    detector._verifier_model = None

    detector._load_model()

    assert detector.model_path == str(fallback)
    assert detector._oww_model.kwargs["wakeword_models"] == [str(fallback)]


def test_continuation_capture_keeps_wake_preroll_and_command_tail():
    loud = np.full(1_280, 1_000, dtype=np.int16).tobytes()
    quiet = np.zeros(1_280, dtype=np.int16).tobytes()
    frames = [loud] * 6 + [quiet] * 8

    class Stream:
        def read(self, *_args, **_kwargs):
            return frames.pop(0) if frames else quiet

    detector = OpenWakeWordDetector.__new__(OpenWakeWordDetector)
    detector._stream = Stream()
    detector._noise_rms = 30.0
    detector.continuation_window_ms = 300
    detector._audio_history = collections.deque([b"wake"], maxlen=20)

    pcm, metadata = detector._capture_command_continuation()

    assert pcm is not None and pcm.startswith(b"wake")
    assert metadata["continuation"] is True


def test_no_continuation_returns_normal_two_step_mode():
    quiet = np.zeros(1_280, dtype=np.int16).tobytes()

    class Stream:
        def read(self, *_args, **_kwargs):
            return quiet

    detector = OpenWakeWordDetector.__new__(OpenWakeWordDetector)
    detector._stream = Stream()
    detector._noise_rms = 30.0
    detector.continuation_window_ms = 300
    detector._audio_history = collections.deque([b"wake"], maxlen=20)

    pcm, metadata = detector._capture_command_continuation()

    assert pcm is None
    assert metadata["continuation"] is False


def test_zero_continuation_window_disables_command_capture():
    class Stream:
        def read(self, *_args, **_kwargs):
            raise AssertionError("disabled continuation must not read the microphone")

    detector = OpenWakeWordDetector.__new__(OpenWakeWordDetector)
    detector._stream = Stream()
    detector.continuation_window_ms = 0

    pcm, metadata = detector._capture_command_continuation()

    assert pcm is None
    assert metadata == {"continuation": False, "continuation_disabled": True}


def test_wake_word_trailing_frame_is_not_treated_as_command():
    loud = np.full(1_280, 1_000, dtype=np.int16).tobytes()
    quiet = np.zeros(1_280, dtype=np.int16).tobytes()
    frames = [loud, quiet, quiet, quiet]

    class Stream:
        def read(self, *_args, **_kwargs):
            return frames.pop(0) if frames else quiet

    detector = OpenWakeWordDetector.__new__(OpenWakeWordDetector)
    detector._stream = Stream()
    detector._noise_rms = 30.0
    detector.continuation_window_ms = 300
    detector._audio_history = collections.deque([b"wake"], maxlen=20)

    pcm, metadata = detector._capture_command_continuation()

    assert pcm is None
    assert metadata["continuation"] is False


def test_usb_room_noise_is_not_treated_as_continuous_command():
    room_noise = np.full(1_280, 80, dtype=np.int16).tobytes()
    frames = [room_noise] * 8

    class Stream:
        def read(self, *_args, **_kwargs):
            return frames.pop(0) if frames else room_noise

    detector = OpenWakeWordDetector.__new__(OpenWakeWordDetector)
    detector._stream = Stream()
    detector._noise_rms = 30.0
    detector.continuation_window_ms = 300
    detector._audio_history = collections.deque([b"wake"], maxlen=20)

    pcm, metadata = detector._capture_command_continuation()

    assert pcm is None
    assert metadata["continuation"] is False


def test_profile_loader_ignores_invalid_json(tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text("not json", encoding="utf-8")
    assert OpenWakeWordDetector._load_profile(str(profile)) == {}


def test_profile_loader_rejects_unsafe_thresholds(tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text('{"threshold": -1}', encoding="utf-8")

    assert OpenWakeWordDetector._load_profile(str(profile)) == {}


@pytest.mark.asyncio
async def test_buffered_pcm_transcription_removes_wake_prefix(monkeypatch):
    engine = STTEngine.__new__(STTEngine)
    engine.sample_rate = 16_000
    engine.min_speech_duration = 0.3
    engine._normalize_pcm_gain = lambda value: value

    client = SimpleNamespace(
        transcribe_audio=lambda _wav: None,
    )

    async def transcribe(_wav):
        return "Hey Aiden, turn on the office light"

    async def get_client():
        client.transcribe_audio = transcribe
        return client

    monkeypatch.setattr("src.ai.groq_client.get_groq_client", get_client)
    pcm = np.ones(16_000, dtype=np.int16).tobytes()

    result = await engine.transcribe_captured_pcm(pcm)

    assert result == (True, "turn on the office light", None)


def test_calibration_profile_path_can_be_read(tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text('{"threshold": 0.42, "model_path": "model.onnx"}', encoding="utf-8")
    assert OpenWakeWordDetector._load_profile(str(profile))["threshold"] == 0.42


def test_new_wake_settings_keep_legacy_configuration_defaults():
    config = SpeechConfig(
        oww_model_path="vosk_models/hey_aiden.onnx",
        oww_threshold=0.55,
    )

    assert config.oww_model_path.endswith("hey_aiden.onnx")
    assert config.oww_threshold == 0.55
    assert config.oww_verifier_path == ""
