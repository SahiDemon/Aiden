"""Cold speech inference must never consume the user's listening window."""

import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np

from src.speech.stt import STTEngine, _SileroVAD


def test_silero_loads_cpu_onnx_instead_of_jit(monkeypatch):
    model = Mock()
    load = Mock(return_value=(model, None))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(hub=SimpleNamespace(load=load)))

    _SileroVAD()

    assert load.call_args.kwargs["onnx"] is True
    assert load.call_args.kwargs["force_onnx_cpu"] is True
    model.eval.assert_not_called()  # ONNX wrappers have no Torch eval mode.
    model.reset_states.assert_called_once()


def test_first_command_after_idle_survives_cold_inference(monkeypatch):
    engine = STTEngine.__new__(STTEngine)
    engine._stop_requested = threading.Event()
    engine._vad_warmed = True  # Already warmed hours ago, as in the recording.
    engine.sample_rate = 16000
    engine.frame_size = 512
    engine.frame_bytes = 1024
    engine.frame_duration_ms = 32
    engine.vad_aggressiveness = 1
    engine._ring_buffer_size = 15
    engine._trailing_window_frames = 7
    engine.timeout = 10.0
    engine.pause_threshold = 0.55
    engine.non_speaking_duration = 0.55
    engine.min_listening_duration = 0.0
    engine.speech_start_min_frames = 3
    engine.speech_start_ratio = 0.35
    engine.min_speech_duration = 0.3
    engine.max_speech_duration = 30.0
    clock = [7200.0]
    cold = [True]
    events = []
    voice = (np.ones(512, dtype=np.int16) * 1000).tobytes()
    silence = bytes(1024)
    frames = iter([silence] * 8 + [voice] * 12 + [silence] * 25)

    def infer(frame):
        if cold[0]:
            clock[0] += 11.0
            cold[0] = False
            events.append("cold_inference")
        return frame == voice

    def read_frame(*_args, **_kwargs):
        clock[0] += 0.032
        return next(frames)

    engine._silero = SimpleNamespace(is_speech=infer, reset=lambda: None)
    monkeypatch.setattr("src.speech.stt.time.monotonic", lambda: clock[0])
    monkeypatch.setattr(engine, "_ensure_mic", lambda: object())
    monkeypatch.setattr(engine, "_discard_buffered_audio", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(engine, "_read_live_frame", read_frame)
    monkeypatch.setattr(engine, "_normalize_pcm_gain", lambda pcm: pcm)

    success, audio, error = engine._listen_sync(lambda: events.append("ready"))

    assert success, error
    assert events == ["cold_inference", "ready"]
    assert audio.frame_data.startswith(voice * 12)
