"""Speech recovery and command validation without live audio or actions."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.speech import tts
from src.execution.command_executor import CommandExecutor
from src.execution.process_manager import ProcessManager


def speech_engine():
    engine = tts.TTSEngine.__new__(tts.TTSEngine)
    engine.provider = "edge"
    engine.voice_id = "en-US-AriaNeural"
    engine.rate = 1
    engine.audio_queue = asyncio.Queue()
    engine._get_cached_audio = AsyncMock(return_value=None)
    engine._generate_speech = AsyncMock(return_value=b"mp3")
    engine._cache_audio = AsyncMock()
    return engine


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["lookup", "synthesis"])
async def test_interruption_discards_late_speech_but_allows_next_request(monkeypatch, stage):
    engine = speech_engine()
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed(*_):
        entered.set()
        await release.wait()
        return b"old audio" if stage == "synthesis" else None

    attribute = "_get_cached_audio" if stage == "lookup" else "_generate_speech"
    setattr(engine, attribute, delayed)
    monkeypatch.setattr(tts, "_ensure_mixer", lambda: False)
    speaking = asyncio.create_task(engine.speak("Old reply"))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        engine.stop_playback_now()
        release.set()
        await speaking
        assert engine.audio_queue.empty()
        engine._cache_audio.assert_not_awaited()
        setattr(engine, attribute, AsyncMock(return_value=None if stage == "lookup" else b"new audio"))
        await engine.speak("New reply")
        assert engine.audio_queue.get_nowait()["text"] == "New reply"
    finally:
        release.set()
        await speaking


@pytest.mark.asyncio
async def test_network_fallback_is_played_without_poisoning_online_cache():
    engine = speech_engine()
    engine._generate_speech = AsyncMock(side_effect=OSError("Cannot connect"))
    engine._generate_offline_speech = AsyncMock(return_value=b"RIFF offline")
    await engine.speak("Opening Chrome")
    assert engine.audio_queue.get_nowait()["data"] == b"RIFF offline"
    engine._cache_audio.assert_not_awaited()


@pytest.mark.asyncio
async def test_interrupted_failed_request_does_not_start_offline_generation(monkeypatch):
    engine = speech_engine()
    monkeypatch.setattr(tts, "_ensure_mixer", lambda: False)

    async def interrupted(*_):
        engine.stop_playback_now()
        raise OSError("connection lost")

    engine._generate_speech = interrupted
    engine._generate_offline_speech = AsyncMock()
    await engine.speak("Old reply")
    engine._generate_offline_speech.assert_not_awaited()
    assert engine.audio_queue.empty()


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["local", "web"])
async def test_interruption_during_caption_broadcast_releases_queue_and_browser_wait(monkeypatch, source):
    from src.speech import playback_events
    engine = speech_engine()
    engine.is_processing = False
    monkeypatch.setattr(tts, "_ensure_mixer", lambda: False)
    monkeypatch.setattr("src.utils.websocket_broadcast.broadcast_voice_status", AsyncMock())
    payloads = []

    async def interrupted(kind, payload):
        payloads.append(payload)
        engine.stop_playback_now()

    monkeypatch.setattr("src.utils.websocket_broadcast.broadcast_message", interrupted)
    engine._play_audio_data = AsyncMock()
    await engine.audio_queue.put({"type": "speak", "data": b"mp3", "text": "Old reply", "source": source})
    processor = asyncio.create_task(engine._process_queue())
    try:
        await asyncio.wait_for(engine.audio_queue.join(), 1)
        engine._play_audio_data.assert_not_awaited()
        assert not engine.is_processing
        assert payloads[0]["speech_id"] not in playback_events._pending
    finally:
        processor.cancel()
        with pytest.raises(asyncio.CancelledError):
            await processor


@pytest.mark.asyncio
async def test_interruption_during_audio_broadcast_does_not_start_local_playback(monkeypatch):
    engine = speech_engine()
    checks = []
    monkeypatch.setattr(tts, "_ensure_mixer", lambda: checks.append(True) or False)

    async def interrupted(*_):
        engine.stop_playback_now()

    monkeypatch.setattr("src.api.server.broadcast_update", interrupted)
    await engine._play_audio_data(b"mp3")
    # Only stop_playback_now checked the mixer; playback never reached it.
    assert checks == [True]


@pytest.mark.asyncio
async def test_interruption_just_before_mixer_load_discards_audio_and_file(monkeypatch, tmp_path):
    engine = speech_engine()
    engine.temp_dir = str(tmp_path)

    def interrupted():
        engine._speech_generation = 1
        return True

    monkeypatch.setattr(tts, "_ensure_mixer", interrupted)
    monkeypatch.setattr("src.api.server.broadcast_update", AsyncMock())
    load = Mock()
    monkeypatch.setattr(tts.pygame.mixer.music, "load", load)
    await engine._play_audio_data(b"mp3")
    load.assert_not_called()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("setting,value", [("voice_id", "en-US-GuyNeural"), ("rate", 1.5)])
def test_edge_cache_changes_with_rendered_voice_settings(setting, value):
    engine = speech_engine()
    original = engine._cache_key("Hello")
    setattr(engine, setting, value)
    assert engine._cache_key("Hello") != original
    assert engine._cache_key("Different text") != engine._cache_key("Hello")


def test_edge_cache_reuses_audio_when_effective_rate_is_unchanged():
    engine = speech_engine()
    original = engine._cache_key("Hello")
    engine.rate = 1.1
    assert engine._cache_key("Hello") == original


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ['{}', '[1]', '[{"text":"Hello","start":0,"end":"bad"}]',
                                '[{"text":"Hello","start":0,"end":NaN}]', 'broken JSON'])
async def test_corrupt_cached_timings_become_cache_miss(monkeypatch, raw):
    engine = speech_engine()
    del engine._get_cached_audio
    redis = SimpleNamespace(get_tts_audio=AsyncMock(return_value=b"mp3"), get=AsyncMock(return_value=raw))
    monkeypatch.setattr(tts, "get_redis_client", AsyncMock(return_value=redis))
    assert await engine._get_cached_audio("Hello") is None
    assert engine._timings_for(b"mp3") == []


@pytest.mark.parametrize("setting,value", [("google_voice", "other"), ("google_pitch", 2), ("google_speaking_rate", 1.5)])
def test_google_cache_changes_with_rendered_voice_settings(setting, value):
    engine = speech_engine()
    engine.provider = "google"
    engine.google_voice, engine.google_pitch, engine.google_speaking_rate = "test", 0, 1
    original = engine._cache_key("Hello")
    setattr(engine, setting, value)
    assert engine._cache_key("Hello") != original


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["load", "progress", "cancel"])
async def test_playback_always_releases_temporary_file(monkeypatch, tmp_path, failure):
    engine = speech_engine()
    engine.temp_dir = str(tmp_path)
    music = SimpleNamespace(load=Mock(), play=Mock(), stop=Mock(), unload=Mock(),
                            get_busy=Mock(return_value=True), get_pos=Mock(return_value=0))
    if failure == "load":
        music.load.side_effect = RuntimeError("bad audio")
    monkeypatch.setattr(tts, "_ensure_mixer", lambda: True)
    monkeypatch.setattr(tts.pygame.mixer, "music", music)
    monkeypatch.setattr("src.api.server.broadcast_update", AsyncMock())
    entered = asyncio.Event()

    async def progress(*_):
        if failure == "progress":
            raise OSError("browser disconnected")
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("src.utils.websocket_broadcast.broadcast_message", progress)
    playing = asyncio.create_task(engine._play_audio_data(b"mp3"))
    if failure == "cancel":
        await asyncio.wait_for(entered.wait(), 1)
        playing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await playing
    else:
        await playing
    assert list(tmp_path.iterdir()) == []
    if failure != "load":
        music.stop.assert_called_once()
        music.unload.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [None, [], "launch_app", {}, {"type": ""},
                                    {"type": "launch_app", "params": []}])
async def test_invalid_command_is_rejected_before_side_effects(payload, monkeypatch):
    monkeypatch.setattr("src.execution.command_executor.get_db_client", AsyncMock(side_effect=AssertionError("must not write")))
    executor = CommandExecutor.__new__(CommandExecutor)
    result = await executor.execute(payload)
    assert result["success"] is False
    assert result["error"]


@pytest.mark.asyncio
async def test_bad_command_does_not_disrupt_valid_commands_in_batch(monkeypatch):
    executor = CommandExecutor.__new__(CommandExecutor)
    executor._handle_launch_app = AsyncMock(return_value=True)
    db = SimpleNamespace(log_command=AsyncMock())
    monkeypatch.setattr("src.execution.command_executor.get_db_client", AsyncMock(return_value=db))
    results = await executor.execute_multiple([None, {"type": "launch_app", "params": {"name": "notepad"}}])
    assert [result["success"] for result in results] == [False, True]
    executor._handle_launch_app.assert_awaited_once()
    db.log_command.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["", "  ", None, []])
async def test_empty_process_name_never_reaches_process_discovery(monkeypatch, name):
    monkeypatch.setattr("src.utils.system_context.get_system_context", Mock(side_effect=AssertionError("must not discover")))
    assert await ProcessManager().kill_process(name) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("pid", [0, -1, True, "42", None])
async def test_invalid_pid_never_launches_taskkill(monkeypatch, pid):
    monkeypatch.setattr("src.execution.process_manager.subprocess.run", Mock(side_effect=AssertionError("must not launch")))
    assert await ProcessManager().kill_process_by_pid(pid) is False
