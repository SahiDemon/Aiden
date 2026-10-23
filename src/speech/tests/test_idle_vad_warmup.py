"""Idle maintenance must not touch live capture or outlive the engine."""

import threading
from types import SimpleNamespace
from unittest.mock import Mock

from src.speech.stt import STTEngine


def make_engine():
    engine = STTEngine.__new__(STTEngine)
    engine._vad_lock = threading.RLock()
    engine._idle_warmup_stop = threading.Event()
    engine._idle_warmup_thread = None
    engine._stop_requested = threading.Event()
    engine._persistent_mic = None
    engine.frame_bytes = 1024
    engine._silero = SimpleNamespace(reset=Mock(), is_speech=Mock(return_value=False))
    return engine


def test_idle_tick_uses_synthetic_frames_without_opening_microphone(monkeypatch):
    engine = make_engine()
    open_mic = Mock(side_effect=AssertionError("Idle warm-up must not open the microphone"))
    monkeypatch.setattr(engine, "_init_persistent_mic", open_mic)

    engine._warm_idle_vad()

    assert engine._silero.is_speech.call_count == 2
    assert all(call.args == (bytes(1024),) for call in engine._silero.is_speech.call_args_list)
    assert engine._silero.reset.call_count == 2
    open_mic.assert_not_called()


def test_idle_tick_skips_entire_active_capture(monkeypatch):
    engine = make_engine()
    capturing = threading.Event()
    finish_capture = threading.Event()
    result = []

    def listen(_source):
        capturing.set()
        assert finish_capture.wait(2.0)
        return b"recorded speech"

    monkeypatch.setattr(engine, "_prepare_live_microphone", lambda *_args: object())
    monkeypatch.setattr(engine, "_discard_buffered_audio", lambda *_args: 0)
    monkeypatch.setattr(engine, "_listen_with_vad", listen)
    engine.sample_rate = 16000
    worker = threading.Thread(target=lambda: result.append(engine._listen_sync()))
    worker.start()
    try:
        assert capturing.wait(1.0)
        resets = engine._silero.reset.call_count
        engine._warm_idle_vad()
        assert engine._silero.reset.call_count == resets
        engine._silero.is_speech.assert_not_called()
    finally:
        finish_capture.set()
        worker.join(timeout=2.0)

    assert result == [(True, b"recorded speech", None)]
    engine._warm_idle_vad()
    assert engine._silero.is_speech.call_count == 2


def test_microphone_handoff_does_not_disable_idle_maintenance():
    engine = make_engine()
    engine.close()
    engine._warm_idle_vad()
    assert not engine._idle_warmup_stop.is_set()
    assert engine._silero.is_speech.call_count == 2


def test_periodic_worker_recovers_after_failure_and_stops_on_shutdown(monkeypatch):
    engine = make_engine()
    recovered = threading.Event()
    calls = []

    def warm(**_kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("temporary inference failure")
        recovered.set()

    monkeypatch.setattr("src.speech.stt._IDLE_VAD_WARMUP_SECONDS", 0.01)
    monkeypatch.setattr(engine, "_warm_vad", warm)
    engine._start_idle_warmup()
    worker = engine._idle_warmup_thread
    engine._start_idle_warmup()
    assert engine._idle_warmup_thread is worker
    try:
        assert recovered.wait(1.0)
    finally:
        engine.shutdown()

    assert not worker.is_alive()
    assert engine._stop_requested.is_set()
    count = len(calls)
    engine._warm_idle_vad()
    engine.shutdown()  # Repeated shutdown is safe.
    assert len(calls) == count


def test_fallback_detector_does_not_start_idle_worker():
    engine = make_engine()
    engine._silero = None
    engine._start_idle_warmup()
    assert engine._idle_warmup_thread is None
    engine.shutdown()


def test_reset_engine_stops_maintenance(monkeypatch):
    import src.speech.stt as module

    engine = make_engine()
    monkeypatch.setattr(module, "_stt_engine", engine)
    module.reset_stt_engine()
    assert engine._idle_warmup_stop.is_set()
    assert module._stt_engine is None
