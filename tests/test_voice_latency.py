import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.core.assistant import AidenAssistant
from src.media.media_router import MediaRouter
from src.speech.tts import TTSEngine


@pytest.mark.asyncio
async def test_locally_muted_spotify_does_not_delay_capture_for_network(monkeypatch):
    router = MediaRouter.__new__(MediaRouter)
    network_started = asyncio.Event()
    network_finished = asyncio.Event()

    async def background(state):
        network_started.set()
        await network_finished.wait()
        return state

    router._duck_media_for_listening = background
    router.spotify_client = SimpleNamespace(play=AsyncMock())
    local = SimpleNamespace(
        duck_for_listening=lambda: {"muted_sessions": [{"process_name": "spotify.exe"}]},
        restore_after_listening=Mock(),
    )
    monkeypatch.setattr("src.media.media_router.get_audio_session_ducker", lambda: local)
    state = await asyncio.wait_for(router.duck_for_listening(), 0.1)
    assert "pause_task" in state
    await network_started.wait()
    assert not state["pause_task"].done()
    # Stop must settle this worker before unmuting and must not wait for it.
    await asyncio.wait_for(router.restore_after_listening(state), 0.1)
    local.restore_after_listening.assert_called_once()


@pytest.mark.asyncio
async def test_activation_cue_is_short_without_changing_other_sounds(monkeypatch):
    import src.speech.tts as module

    monkeypatch.setattr(module, "_ensure_mixer", lambda: True)
    engine = TTSEngine.__new__(TTSEngine)
    activation = Mock()
    activation.play.return_value = None
    stopped = Mock()
    stopped.play.return_value = None
    acknowledgement = Mock()
    acknowledgement.play.return_value = None
    engine._preloaded_sounds = {"activation": activation, "stopped": stopped, "mmm1": acknowledgement}
    await engine.play_sound_now("activation")
    await engine.play_sound_now("stopped")
    await engine.play_sound_now("mmm1")
    activation.play.assert_called_once_with(maxtime=200, fade_ms=10)
    stopped.play.assert_called_once_with()
    acknowledgement.play.assert_called_once_with(maxtime=300, fade_ms=10)


@pytest.mark.asyncio
async def test_mmm_acknowledgement_precedes_recording_and_beep(monkeypatch):
    events = []
    assistant = AidenAssistant.__new__(AidenAssistant)
    assistant._current_request_task = None
    assistant._speak_tasks = set()
    assistant.tts = SimpleNamespace(stop=Mock(), audio_queue=SimpleNamespace(empty=lambda: True))
    assistant._play_wake_acknowledgement = AsyncMock(side_effect=lambda: events.append("mmm"))
    assistant._play_sound_reliably = AsyncMock(side_effect=lambda name: events.append("beep"))

    async def transcribe(**kwargs):
        events.append("capture")
        await kwargs["ready_cue"]()
        raise asyncio.CancelledError()

    assistant.stt = SimpleNamespace(
        refresh_microphone=lambda: events.append("microphone") or True,
        transcribe=transcribe, close=lambda: events.append("closed"),
    )
    monkeypatch.setattr("src.media.media_router.get_media_router",
                        lambda: SimpleNamespace(duck_for_listening=AsyncMock(return_value=None)))
    monkeypatch.setattr("src.core.wake_word_manager.get_wake_word_manager", lambda: None)
    monkeypatch.setattr("src.media.audio_session_ducker.get_audio_session_ducker",
                        lambda: SimpleNamespace(restore_all=Mock()))
    monkeypatch.setattr("src.utils.websocket_broadcast.broadcast_voice_status", AsyncMock())
    await assistant.handle_voice_activation()
    assert events == ["microphone", "mmm", "capture", "beep", "closed"]


@pytest.mark.asyncio
async def test_capture_releases_device_before_resuming_wake_detection(monkeypatch):
    events = []
    assistant = AidenAssistant.__new__(AidenAssistant)
    assistant.stt = SimpleNamespace(close=lambda: events.append("closed"))
    manager = SimpleNamespace(
        get_state=lambda: True,
        detector=SimpleNamespace(resume=lambda: events.append("wake_ready")),
    )
    monkeypatch.setattr("src.core.wake_word_manager.get_wake_word_manager", lambda: manager)
    await assistant._release_voice_capture()
    assert events == ["closed", "wake_ready"]


@pytest.mark.asyncio
async def test_new_activation_stops_output_before_waiting_for_old_cleanup(monkeypatch):
    assistant = AidenAssistant.__new__(AidenAssistant)
    assistant._is_listening = True
    assistant.stt = SimpleNamespace(request_stop=Mock())
    assistant.tts = SimpleNamespace(stop_playback_now=Mock(), stop=Mock())
    assistant._speak_tasks = set()
    ready = asyncio.Event()

    async def previous_request():
        ready.set()
        try:
            await asyncio.Event().wait()
        finally:
            assistant.tts.stop_playback_now.assert_called_once()
            assert assistant._voice_stop_requested

    previous = asyncio.create_task(previous_request())
    await ready.wait()
    assistant._current_request_task = previous
    detector = SimpleNamespace(
        pause=Mock(), resume=Mock(), wait_until_stream_released=lambda timeout: False,
    )
    monkeypatch.setattr("src.core.wake_word_manager.get_wake_word_manager",
                        lambda: SimpleNamespace(detector=detector))
    monkeypatch.setattr("src.utils.websocket_broadcast.broadcast_voice_status", AsyncMock())
    await assistant.handle_voice_activation(from_hotkey=True)
    assert previous.cancelled()


@pytest.mark.asyncio
async def test_generated_speech_can_play_while_cache_save_is_blocked():
    engine = TTSEngine.__new__(TTSEngine)
    engine.provider = "edge"
    engine.audio_queue = asyncio.Queue()
    engine._get_cached_audio = AsyncMock(return_value=None)
    engine._generate_speech = AsyncMock(return_value=b"speech-audio")
    save_started = asyncio.Event()
    finish_save = asyncio.Event()

    async def save(text, audio):
        save_started.set()
        await finish_save.wait()

    engine._cache_audio = save
    speaking = asyncio.create_task(engine.speak("Opening Chrome."))
    try:
        await asyncio.wait_for(save_started.wait(), .5)
        # A stalled Redis write must not hold back already generated speech.
        queued = await asyncio.wait_for(engine.audio_queue.get(), .1)
        assert queued["data"] == b"speech-audio"
        assert queued["text"] == "Opening Chrome."
        assert queued["source"] == "local"
        assert not speaking.done()
        finish_save.set()
        await speaking
        assert engine.audio_queue.empty()
    finally:
        finish_save.set()
        await speaking


@pytest.mark.asyncio
async def test_cache_failure_does_not_prevent_generated_audio_playback(monkeypatch):
    engine = TTSEngine.__new__(TTSEngine)
    engine.provider = "edge"
    engine.audio_queue = asyncio.Queue()
    engine._get_cached_audio = AsyncMock(return_value=None)
    engine._generate_speech = AsyncMock(return_value=b"speech-audio")
    redis = SimpleNamespace(cache_tts_audio=AsyncMock(side_effect=OSError("cache unavailable")))
    monkeypatch.setattr("src.speech.tts.get_redis_client", AsyncMock(return_value=redis))
    await engine.speak("Opening Chrome.")
    assert engine.audio_queue.get_nowait()["data"] == b"speech-audio"
    assert engine.audio_queue.empty()


@pytest.mark.asyncio
async def test_cached_speech_does_not_regenerate_or_save_again():
    engine = TTSEngine.__new__(TTSEngine)
    engine.provider = "edge"
    engine.audio_queue = asyncio.Queue()
    engine._get_cached_audio = AsyncMock(return_value=b"cached-audio")
    engine._generate_speech = AsyncMock()
    engine._cache_audio = AsyncMock()
    await engine.speak("Opening Chrome.", source="web")
    queued = engine.audio_queue.get_nowait()
    assert queued["data"] == b"cached-audio"
    assert queued["source"] == "web"
    engine._generate_speech.assert_not_awaited()
    engine._cache_audio.assert_not_awaited()
