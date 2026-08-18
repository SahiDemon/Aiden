"""Regression tests for wake acknowledgement and microphone readiness ordering."""

import asyncio
import threading
from types import SimpleNamespace

import pytest

import src.media.media_router as media_router_module
from src.core.assistant import AidenAssistant
from src.media.media_router import MediaRouter
from src.speech.stt import STTEngine


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("from_hotkey", "expected"),
    [
        (False, ["acknowledgement", "activation"]),
        (True, ["activation"]),
    ],
)
async def test_activation_sound_is_the_final_speak_now_cue(from_hotkey, expected):
    assistant = AidenAssistant.__new__(AidenAssistant)
    events = []

    async def acknowledgement():
        events.append("acknowledgement")

    async def play_sound(sound_name):
        events.append(sound_name)

    assistant._play_wake_acknowledgement = acknowledgement
    assistant.tts = SimpleNamespace(play_sound_now=play_sound)

    await assistant._play_activation_ready_cue(from_hotkey)

    assert events == expected


@pytest.mark.asyncio
async def test_listening_status_is_published_only_after_microphone_ready(monkeypatch):
    engine = STTEngine.__new__(STTEngine)
    engine._silero = None
    engine._stop_requested = threading.Event()
    events = []

    def fake_listen(on_listening_ready, preserve_recent_audio):
        events.append(("microphone_ready", preserve_recent_audio))
        on_listening_ready()
        return False, None, "timeout"

    async def fake_broadcast(status, **payload):
        events.append(("broadcast", status, payload))

    monkeypatch.setattr(engine, "_listen_sync", fake_listen)
    monkeypatch.setattr(
        "src.utils.websocket_broadcast.broadcast_voice_status",
        fake_broadcast,
    )

    result = await engine.transcribe(
        play_activation_sound=False,
        media_already_ducked=True,
    )

    assert result == (False, None, "timeout")
    assert events[0] == ("microphone_ready", False)
    assert events[1] == (
        "broadcast",
        "listening",
        {"speaking": False, "active": True},
    )


def test_microphone_buffer_is_flushed_before_ready_signal(monkeypatch):
    engine = STTEngine.__new__(STTEngine)
    engine.sample_rate = 16_000
    engine._persistent_mic = object()
    events = []

    stream = SimpleNamespace(
        get_read_available=lambda: 3_200,
        read=lambda samples, **kwargs: events.append(("flushed", samples, kwargs)),
    )
    source = SimpleNamespace(stream=stream)

    monkeypatch.setattr(engine, "_ensure_mic", lambda: source)
    monkeypatch.setattr(engine, "_listen_with_vad", lambda ready_source: object())

    success, _, error = engine._listen_sync(
        lambda: events.append(("ready",)),
        preserve_recent_audio=False,
    )

    assert success is True
    assert error is None
    assert events == [
        ("flushed", 3_200, {"exception_on_overflow": False}),
        ("ready",),
    ]


@pytest.mark.asyncio
async def test_slow_spotify_does_not_block_listening_readiness(monkeypatch):
    router = MediaRouter.__new__(MediaRouter)

    async def slow_playback_lookup():
        await asyncio.sleep(1)
        return {"is_playing": True, "device": {"id": "device"}}

    router.spotify_client = SimpleNamespace(
        is_enabled=lambda: True,
        has_fresh_token=lambda: True,
        get_current_playback=slow_playback_lookup,
        pause=lambda **kwargs: None,
    )
    local_ducker = SimpleNamespace(
        duck_for_listening=lambda: {"muted_sessions": []},
    )

    monkeypatch.setattr(media_router_module, "get_audio_session_ducker", lambda: local_ducker)
    monkeypatch.setattr(media_router_module, "_SPOTIFY_DUCK_DEADLINE_SECONDS", 0.01)

    started = asyncio.get_running_loop().time()
    state = await router.duck_for_listening()
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 0.2
    assert state["spotify_was_playing"] is False
    assert state["muted_app_sessions"] == {"muted_sessions": []}
