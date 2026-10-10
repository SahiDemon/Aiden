"""Readiness must prove audio delivery before any activation cue."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import numpy as np

from src.speech.stt import STTEngine


def make_engine():
    engine = STTEngine.__new__(STTEngine)
    engine._stop_requested = threading.Event()
    engine._silero = None
    engine.frame_size = 512
    engine.frame_bytes = 1024
    engine.sample_rate = 16000
    engine._persistent_mic = None
    return engine


def test_stalled_microphone_never_performs_a_blocking_read():
    engine = make_engine()
    reads = []
    source = SimpleNamespace(stream=SimpleNamespace(
        get_read_available=lambda: 0,
        read=lambda size: reads.append(size),
    ))
    with pytest.raises(TimeoutError):
        engine._read_live_frame(source, timeout=0.01)
    assert reads == []


@pytest.mark.asyncio
async def test_first_stalled_stream_is_reopened_before_cue(monkeypatch):
    engine = make_engine()
    events = []
    opens = []

    def open_mic():
        attempt = len(opens)
        opens.append(attempt)
        stream = SimpleNamespace(
            get_read_available=lambda: 0 if attempt == 0 else 512,
            read=lambda size: events.append("frame") or bytes(size * 2),
        )
        engine._persistent_mic = SimpleNamespace(
            stream=stream, __exit__=lambda *_args: events.append("closed"),
        )

    async def cue():
        assert len(opens) == 2
        assert events.count("frame") >= 8
        events.append("cue")

    def vad(source, initial_frames=None):
        events.append("vad")
        return None

    monkeypatch.setattr(engine, "_init_persistent_mic", open_mic)
    monkeypatch.setattr(engine, "_listen_with_vad", vad)
    monkeypatch.setattr("src.utils.websocket_broadcast.broadcast_voice_status", AsyncMock())
    await engine.transcribe(media_already_ducked=True, ready_cue=cue)
    assert events.index("closed") < events.index("cue") < events.index("vad")


@pytest.mark.asyncio
async def test_failed_readiness_has_no_beep_or_listening_status(monkeypatch):
    engine = make_engine()
    cue = AsyncMock()
    status = AsyncMock()

    def open_mic():
        raise OSError("device unavailable")

    monkeypatch.setattr(engine, "_init_persistent_mic", open_mic)
    monkeypatch.setattr("src.utils.websocket_broadcast.broadcast_voice_status", status)
    success, _, error = await engine.transcribe(media_already_ducked=True, ready_cue=cue)
    assert not success
    assert "not delivering audio" in error
    cue.assert_not_awaited()
    assert all(call.args[0] != "listening" for call in status.await_args_list)


def test_readiness_cancellation_stops_without_reopening(monkeypatch):
    engine = make_engine()
    engine._stop_requested.set()
    source = SimpleNamespace(stream=SimpleNamespace(get_read_available=lambda: 0))
    monkeypatch.setattr(engine, "_ensure_mic", lambda: source)
    monkeypatch.setattr(engine, "close", lambda: pytest.fail("Cancelled capture must not retry"))
    with pytest.raises(InterruptedError):
        engine._prepare_live_microphone()


@pytest.mark.asyncio
async def test_cancelled_listen_joins_worker_before_returning(monkeypatch):
    engine = make_engine()
    started = threading.Event()
    finished = threading.Event()

    def listen(*_args):
        started.set()
        assert engine._stop_requested.wait(1.0)
        finished.set()
        return False, None, "cancelled"

    monkeypatch.setattr(engine, "_listen_sync", listen)
    monkeypatch.setattr("src.utils.websocket_broadcast.broadcast_voice_status", AsyncMock())
    task = asyncio.create_task(engine.transcribe(
        play_activation_sound=False, media_already_ducked=True,
    ))
    assert await asyncio.to_thread(started.wait, 1.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()


def test_speech_during_cue_is_retained_in_order(monkeypatch):
    engine = make_engine()
    cue_finished = threading.Event()
    speech = [bytes([index]) * engine.frame_bytes for index in (1, 2, 3)]
    reads = iter(speech)
    retained = []
    source = object()

    def read_frame(_source):
        frame = next(reads)
        if frame == speech[-1]:
            cue_finished.set()
        return frame

    def listen(_source, initial_frames):
        retained.extend(initial_frames)
        return object()

    monkeypatch.setattr(engine, "_prepare_live_microphone", lambda *_args: source)
    monkeypatch.setattr(engine, "_discard_buffered_audio", lambda *_args: 0)
    monkeypatch.setattr(engine, "_read_live_frame", read_frame)
    monkeypatch.setattr(engine, "_listen_with_vad", listen)
    success, _, error = engine._listen_sync(start_capture=cue_finished)
    assert success and error is None
    assert retained == speech


def test_command_completed_during_cue_is_in_transcription_audio(monkeypatch):
    engine = make_engine()
    engine.frame_duration_ms = 32
    engine.vad_aggressiveness = 1
    engine._ring_buffer_size = 15
    engine._trailing_window_frames = 7
    engine.pause_threshold = 0.55
    engine.non_speaking_duration = 0.55
    engine.timeout = 8
    engine.speech_start_min_frames = 3
    engine.speech_start_ratio = 0.35
    engine.min_speech_duration = 0.3
    engine.max_speech_duration = 30
    voice = (np.ones(512, dtype=np.int16) * 1000).tobytes()
    silence = bytes(engine.frame_bytes)
    monkeypatch.setattr(engine, "_classify_frame", lambda frame, _vad, **_kwargs: frame == voice)
    monkeypatch.setattr(engine, "_normalize_pcm_gain", lambda pcm: pcm)
    monkeypatch.setattr(engine, "_read_live_frame", lambda *_args: silence)
    audio = engine._listen_with_vad(object(), initial_frames=[voice] * 12)
    assert audio.frame_data.startswith(voice * 12)


def test_first_vad_inference_runs_before_capture_is_armed(monkeypatch):
    engine = make_engine()
    events = []
    source = object()
    engine._silero = SimpleNamespace(
        is_speech=lambda _pcm: events.append("warmed"),
        reset=lambda: events.append("reset"),
    )
    monkeypatch.setattr(engine, "_ensure_mic", lambda: source)
    monkeypatch.setattr(engine, "_discard_buffered_audio", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(engine, "_read_live_frame", lambda *_args, **_kwargs: bytes(1024))
    monkeypatch.setattr(engine, "_listen_with_vad", lambda *_args: object())
    assert engine._listen_sync(lambda: events.append("ready"))[0]
    assert events == ["warmed", "reset", "ready"]


def test_quiet_speech_rejected_by_silero_uses_valid_webrtc_frame():
    engine = make_engine()
    engine._silero = SimpleNamespace(is_speech=lambda _frame: False)
    checked = []

    def speech(frame, rate):
        checked.append((len(frame), rate))
        return True

    voice = (np.ones(512, dtype=np.int16) * 1000).tobytes()
    assert engine._classify_frame(voice, SimpleNamespace(is_speech=speech))
    assert checked == [(960, 16000)]


def test_broken_speech_detector_does_not_silently_discard_command():
    engine = make_engine()

    def broken(_frame):
        raise RuntimeError("inference failed")

    engine._silero = SimpleNamespace(is_speech=broken)
    voice = (np.ones(512, dtype=np.int16) * 1000).tobytes()
    with pytest.raises(RuntimeError, match="inference failed"):
        engine._classify_frame(voice, None)
