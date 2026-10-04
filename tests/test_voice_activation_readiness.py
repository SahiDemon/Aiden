"""Regression tests for wake acknowledgement and microphone readiness ordering."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.media.media_router as media_router_module
from src.core.assistant import AidenAssistant
from src.media.media_router import MediaRouter
from src.speech.stt import STTEngine
from src.speech.wake_detection import WakeDetection


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("from_hotkey", "expected"),
    [
        (False, ["activation"]),
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
async def test_activation_sound_retries_once_before_fallback():
    assistant = AidenAssistant.__new__(AidenAssistant)
    attempts = []

    async def play_sound(sound_name):
        attempts.append(sound_name)
        return len(attempts) == 2

    assistant.tts = SimpleNamespace(play_sound_now=play_sound)

    assert await assistant._play_sound_reliably("activation") is True
    assert attempts == ["activation", "activation"]


def test_command_flow_uses_buffered_audio_only_for_wake_detection():
    detection = WakeDetection("aiden_v2", 0.9, command_audio=b"wake and command")

    assert AidenAssistant._should_use_buffered_command(False, detection) is True
    assert AidenAssistant._should_use_buffered_command(True, detection) is False
    assert AidenAssistant._should_use_buffered_command(False, None) is False


@pytest.mark.asyncio
async def test_listening_status_is_published_only_after_microphone_ready(monkeypatch):
    engine = STTEngine.__new__(STTEngine)
    engine._silero = None
    engine._stop_requested = threading.Event()
    events = []

    def fake_listen(
        on_listening_ready,
        preserve_recent_audio,
        start_capture,
        on_capture_armed,
    ):
        events.append(("microphone_ready", preserve_recent_audio))
        assert start_capture is None
        assert on_capture_armed is not None
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

    native_stream = SimpleNamespace(get_read_available=lambda: 3_200)
    stream = SimpleNamespace(
        pyaudio_stream=native_stream,
        read=lambda samples: events.append(("flushed", samples)),
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
        ("flushed", 3_200),
        ("ready",),
    ]


@pytest.mark.asyncio
async def test_ready_cue_finishes_before_listening_starts(monkeypatch):
    engine = STTEngine.__new__(STTEngine)
    engine._silero = None
    engine._stop_requested = threading.Event()
    events = []

    def fake_listen(
        on_listening_ready,
        preserve_recent_audio,
        start_capture,
        on_capture_armed,
    ):
        events.append("worker_started")
        on_capture_armed()
        assert start_capture.wait(timeout=1)
        events.append("capture_started")
        on_listening_ready()
        return False, None, "timeout"

    async def cue():
        events.append("cue_started")
        await asyncio.sleep(0)
        events.append("cue_finished")

    async def fake_broadcast(*_args, **_kwargs):
        return None

    monkeypatch.setattr(engine, "_listen_sync", fake_listen)
    monkeypatch.setattr(
        "src.utils.websocket_broadcast.broadcast_voice_status",
        fake_broadcast,
    )

    result = await engine.transcribe(
        play_activation_sound=False,
        media_already_ducked=True,
        ready_cue=cue,
    )

    assert result == (False, None, "timeout")
    assert events == [
        "worker_started",
        "cue_started",
        "cue_finished",
        "capture_started",
    ]


def test_microphone_is_reopened_for_the_wake_to_stt_handoff(monkeypatch):
    engine = STTEngine.__new__(STTEngine)
    events = []
    engine._persistent_mic = SimpleNamespace(
        __exit__=lambda *_args: events.append("closed"),
    )

    def reopen():
        events.append("opened")
        engine._persistent_mic = object()

    monkeypatch.setattr(engine, "_init_persistent_mic", reopen)

    assert engine.refresh_microphone() is True
    assert events == ["closed", "opened"]


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


@pytest.mark.asyncio
async def test_media_restore_resumes_only_sources_ducked_by_aiden(monkeypatch):
    """A paused source must never be started by voice-turn cleanup."""
    router = MediaRouter.__new__(MediaRouter)
    router.spotify_client = SimpleNamespace(
        is_enabled=lambda: True,
        has_fresh_token=lambda: True,
        get_current_playback=AsyncMock(
            return_value={"is_playing": True, "device": {"id": "desktop"}}
        ),
        pause=AsyncMock(),
        play=AsyncMock(),
    )
    router.browser_controller = SimpleNamespace(
        duck_for_listening=AsyncMock(return_value={"toggled_handles": [42]}),
        restore_after_listening=AsyncMock(),
    )
    local_ducker = SimpleNamespace(
        duck_for_listening=lambda: {"muted_sessions": []},
        restore_after_listening=lambda _state: None,
    )
    monkeypatch.setattr(media_router_module, "get_audio_session_ducker", lambda: local_ducker)

    state = await router.duck_for_listening()
    assert state["spotify_was_playing"] is True
    assert state["spotify_device_id"] == "desktop"
    assert state["browser_media"] == {"toggled_handles": [42]}

    await router.restore_after_listening(state)
    router.spotify_client.play.assert_awaited_once_with(device_id="desktop")
    router.browser_controller.restore_after_listening.assert_awaited_once_with(
        {"toggled_handles": [42]}
    )

    router.spotify_client.play.reset_mock()
    await router.restore_after_listening({"spotify_was_playing": False})
    router.spotify_client.play.assert_not_awaited()


@pytest.mark.asyncio
async def test_jellyfin_duck_restores_only_the_sessions_paused_by_aiden(monkeypatch):
    """Jellyfin sessions paused before the voice turn must remain paused."""
    router = MediaRouter.__new__(MediaRouter)
    router.spotify_client = SimpleNamespace(
        is_enabled=lambda: False,
        has_fresh_token=lambda: False,
    )
    router.browser_controller = None
    router.jellyfin_client = SimpleNamespace(
        is_enabled=lambda: True,
        pause_playing_sessions=AsyncMock(return_value=["playing-session"]),
        resume_sessions=AsyncMock(return_value=["playing-session"]),
    )
    local_ducker = SimpleNamespace(
        duck_for_listening=lambda: {"muted_sessions": []},
        restore_after_listening=lambda _state: None,
    )
    monkeypatch.setattr(media_router_module, "get_audio_session_ducker", lambda: local_ducker)

    state = await router.duck_for_listening()
    assert state["jellyfin_session_ids"] == ["playing-session"]

    await router.restore_after_listening(state)
    router.jellyfin_client.resume_sessions.assert_awaited_once_with(["playing-session"])

    router.jellyfin_client.resume_sessions.reset_mock()
    await router.restore_after_listening({"jellyfin_session_ids": []})
    router.jellyfin_client.resume_sessions.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_jellyfin_pause_and_resume_use_existing_sessions():
    router = MediaRouter.__new__(MediaRouter)
    router.jellyfin_client = SimpleNamespace(
        is_enabled=lambda: True,
        pause_playing_sessions=AsyncMock(return_value=["session-1"]),
        get_paused_session_ids=AsyncMock(return_value=["session-1"]),
        resume_sessions=AsyncMock(return_value=["session-1"]),
    )

    paused, pause_payload = await router.handle_media_command("pause", target="jellyfin")
    resumed, resume_payload = await router.handle_media_command("resume", target="jellyfin")

    assert paused is True
    assert pause_payload["message"] == "Jellyfin playback paused."
    assert resumed is True
    assert resume_payload["message"] == "Jellyfin playback resumed."
    router.jellyfin_client.pause_playing_sessions.assert_awaited_once_with()
    router.jellyfin_client.resume_sessions.assert_awaited_once_with(["session-1"])


@pytest.mark.asyncio
async def test_voice_turn_waits_for_background_reply_before_media_restore():
    assistant = AidenAssistant.__new__(AidenAssistant)
    events = []

    async def speak_in_background():
        await asyncio.sleep(0)
        events.append("reply_generated")

    async def wait_until_done(timeout):
        events.append(("playback_finished", timeout))
        return True

    task = asyncio.create_task(speak_in_background())
    assistant._speak_tasks = {task}
    assistant.tts = SimpleNamespace(wait_until_done=wait_until_done)

    await assistant._wait_for_voice_output()

    assert events == ["reply_generated", ("playback_finished", 60.0)]
