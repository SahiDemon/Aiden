import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.core.assistant import AidenAssistant
from src.media.audio_session_ducker import AudioSessionDucker
from src.media.media_router import MediaRouter


def test_restore_all_unmutes_only_sessions_aiden_muted(monkeypatch):
    import src.media.audio_session_ducker as module

    changes = []

    def session(identifier, muted):
        volume = SimpleNamespace(GetMute=lambda: muted[0])

        def set_mute(value, context):
            muted[0] = bool(value)
            changes.append((identifier, value))

        volume.SetMute = set_mute
        return SimpleNamespace(
            Process=SimpleNamespace(name=lambda: "spotify.exe", pid=12345),
            InstanceIdentifier=identifier, State=1, SimpleAudioVolume=volume,
        )

    sessions = [session("playing", [False]), session("already-muted", [True])]
    monkeypatch.setattr(module, "PYCAW_AVAILABLE", True)
    monkeypatch.setattr(module, "AudioSessionState", SimpleNamespace(Active=1))
    monkeypatch.setattr(module, "AudioUtilities", SimpleNamespace(GetAllSessions=lambda: sessions))
    ducker = AudioSessionDucker()
    ducker.duck_for_listening()  # Simulate losing the returned startup state.
    ducker.restore_all()
    ducker.restore_all()
    assert changes == [("playing", 1), ("playing", 0)]
    assert sessions[1].SimpleAudioVolume.GetMute()


@pytest.mark.asyncio
async def test_stop_releases_owned_mutes_even_without_active_request(monkeypatch):
    restore = Mock()
    monkeypatch.setattr("src.media.audio_session_ducker.get_audio_session_ducker",
                        lambda: SimpleNamespace(restore_all=restore))
    assistant = AidenAssistant.__new__(AidenAssistant)
    assistant._is_listening = False
    assistant._current_request_task = None
    assistant._speak_tasks = set()
    assistant.tts = SimpleNamespace(stop_playback_now=Mock())
    await assistant.cancel_active_listening()
    restore.assert_called_once()


@pytest.mark.asyncio
async def test_stop_during_media_startup_restores_mute_and_spotify(monkeypatch):
    pause_started = asyncio.Event()
    restored = Mock()
    router = MediaRouter.__new__(MediaRouter)

    async def pause(**kwargs):
        pause_started.set()
        await asyncio.Event().wait()

    router.spotify_client = SimpleNamespace(
        is_enabled=lambda: True, has_fresh_token=lambda: True,
        get_current_playback=AsyncMock(return_value={
            "is_playing": True, "device": {"id": "desktop"},
        }),
        pause=pause, play=AsyncMock(),
    )
    state = {"muted_sessions": [{"process_id": 12345, "process_name": "spotify.exe"}]}
    monkeypatch.setattr("src.media.media_router.get_audio_session_ducker", lambda: SimpleNamespace(
        duck_for_listening=lambda: state, restore_after_listening=restored,
    ))
    listening_state = await router.duck_for_listening()
    await asyncio.wait_for(pause_started.wait(), 1)
    await router.restore_after_listening(listening_state)
    restored.assert_called_once_with(state)
    router.spotify_client.play.assert_awaited_once_with(device_id="desktop")
