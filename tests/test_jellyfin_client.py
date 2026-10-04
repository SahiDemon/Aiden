from unittest.mock import AsyncMock

import pytest

from src.media.jellyfin_client import JellyfinClient, JellyfinError


@pytest.mark.asyncio
async def test_playing_session_detection_excludes_paused_and_uncontrollable_sessions(monkeypatch):
    client = JellyfinClient.__new__(JellyfinClient)
    client.get_sessions = AsyncMock(return_value=[
        {"Id": "playing", "NowPlayingItem": {"Name": "Film"}, "PlayState": {"IsPaused": False}},
        {"Id": "paused", "NowPlayingItem": {"Name": "Film"}, "PlayState": {"IsPaused": True}},
        {"Id": "stale", "NowPlayingItem": {"Name": "Film"}},
        {"Id": "uncontrollable", "NowPlayingItem": {"Name": "Film"}, "SupportsMediaControl": False},
        {"Id": "idle", "PlayState": {"IsPaused": False}},
    ])

    assert await client.get_playing_session_ids() == ["playing"]
    assert await client.get_paused_session_ids() == ["paused"]


@pytest.mark.asyncio
async def test_pause_playing_sessions_returns_only_successfully_paused_ids():
    client = JellyfinClient.__new__(JellyfinClient)
    client.get_playing_session_ids = AsyncMock(return_value=["first", "second"])
    client.pause_session = AsyncMock(side_effect=[None, JellyfinError("offline")])

    # The public operation remains best-effort: a failed remote client must not
    # cause Aiden to resume a session it never paused.
    assert await client.pause_playing_sessions() == ["first"]
