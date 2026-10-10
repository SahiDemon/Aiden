from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.media.media_router import MediaRouter
from src.media.audio_session_ducker import AudioSessionDucker


@pytest.mark.asyncio
async def test_cold_token_refreshes_then_pauses_and_restores_same_device(monkeypatch):
    events = []
    router = MediaRouter.__new__(MediaRouter)

    async def refresh(**kwargs):
        assert kwargs == {"interactive_auth": False}
        events.append("refresh")

    async def playback():
        events.append("lookup")
        return {"is_playing": True, "device": {"id": "desktop"}}

    async def pause(**kwargs):
        assert kwargs == {"device_id": "desktop"}
        events.append("pause")

    router.spotify_client = SimpleNamespace(
        is_enabled=lambda: True, has_fresh_token=lambda: False,
        _ensure_token=refresh, get_current_playback=playback,
        pause=pause, play=AsyncMock(),
    )
    monkeypatch.setattr("src.media.media_router.get_audio_session_ducker", lambda: SimpleNamespace(
        duck_for_listening=lambda: {"muted_sessions": []},
        restore_after_listening=lambda state: None,
    ))
    state = await router.duck_for_listening()
    assert events == ["refresh", "lookup", "pause"]
    assert state["spotify_was_playing"]
    await router.restore_after_listening(state)
    router.spotify_client.play.assert_awaited_once_with(device_id="desktop")


@pytest.mark.asyncio
async def test_already_paused_spotify_is_not_started_after_listening():
    router = MediaRouter.__new__(MediaRouter)
    router.spotify_client = SimpleNamespace(
        is_enabled=lambda: True, has_fresh_token=lambda: True,
        get_current_playback=AsyncMock(return_value={"is_playing": False}),
        pause=AsyncMock(), play=AsyncMock(),
    )
    playing, device = await router._duck_spotify_for_listening()
    assert (playing, device) == (False, None)
    await router.restore_after_listening({"spotify_was_playing": playing})
    router.spotify_client.pause.assert_not_awaited()
    router.spotify_client.play.assert_not_awaited()


def test_spotify_audio_is_muted_and_restored_if_api_is_unavailable(monkeypatch):
    import src.media.audio_session_ducker as module

    muted = []
    volume = SimpleNamespace(
        GetMute=lambda: muted[-1] if muted else False,
        SetMute=lambda value, context: muted.append(value),
    )
    session = SimpleNamespace(
        Process=SimpleNamespace(name=lambda: "Spotify.exe", pid=12345),
        State=1, SimpleAudioVolume=volume,
    )
    monkeypatch.setattr(module, "PYCAW_AVAILABLE", True)
    monkeypatch.setattr(module, "AudioSessionState", SimpleNamespace(Active=1))
    monkeypatch.setattr(module, "AudioUtilities", SimpleNamespace(GetAllSessions=lambda: [session]))
    ducker = AudioSessionDucker()
    state = ducker.duck_for_listening()
    assert muted == [1]
    ducker.restore_after_listening(state)
    assert muted == [1, 0]
