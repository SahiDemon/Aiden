"""Regression coverage for the malformed commands seen in live voice logs."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.media.media_router import MediaRouter


def make_router():
    router = MediaRouter.__new__(MediaRouter)
    router.jellyfin_client = SimpleNamespace(
        is_enabled=lambda: True,
        get_sessions=AsyncMock(return_value=[{
            "Id": "desktop", "NowPlayingItem": {"Name": "Movie"},
            "PlayState": {"IsPaused": True},
        }]),
        set_paused=AsyncMock(),
    )
    router._spotify_is_active = AsyncMock(return_value=True)
    router._handle_spotify = AsyncMock(return_value=(True, {"type": "spotify"}))
    router.browser_controller = SimpleNamespace(control=AsyncMock(return_value=(True, {"type": "browser_media"})))
    return router


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["jellyfin", "Jellyfin.", "Jelly fin", "Jellyfish"])
async def test_resume_player_in_query_reaches_paused_jellyfin_session(query):
    router = make_router()

    success, payload = await router.handle_media_command("resume", query=query)

    assert success
    assert payload["message"] == "Jellyfin playback resumed."
    router.jellyfin_client.set_paused.assert_awaited_once_with("desktop", paused=False)
    router._spotify_is_active.assert_not_awaited()
    router.browser_controller.control.assert_not_awaited()


@pytest.mark.asyncio
async def test_pause_player_in_query_reaches_playing_jellyfin_session():
    router = make_router()
    router.jellyfin_client.get_sessions.return_value[0]["PlayState"]["IsPaused"] = False

    success, payload = await router.handle_media_command("pause", query="Jellyfin")

    assert success
    assert payload["message"] == "Jellyfin paused."
    router.jellyfin_client.set_paused.assert_awaited_once_with("desktop", paused=True)
    router.browser_controller.control.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_spotify_target_is_preserved():
    router = make_router()
    await router.handle_media_command("resume", target="spotify", query="Jellyfish")
    router._handle_spotify.assert_awaited_once()
    router.jellyfin_client.get_sessions.assert_not_awaited()


@pytest.mark.asyncio
async def test_song_title_is_not_reinterpreted_as_jellyfin():
    router = make_router()
    await router.handle_media_command("play_track", query="Jellyfish")
    router._handle_spotify.assert_awaited_once()
    router.jellyfin_client.get_sessions.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_without_player_selects_the_detected_session():
    router = make_router()
    router._get_media_candidates = AsyncMock(return_value=[{"target": "spotify", "id": "desktop", "is_playing": True}])
    await router.handle_media_command("resume")
    router._handle_spotify.assert_awaited_once()
    router.jellyfin_client.get_sessions.assert_not_awaited()
