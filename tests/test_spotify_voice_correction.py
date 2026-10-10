import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.core.assistant import _keep_spotify_correction_as_one_action
from src.media.media_router import MediaRouter


@pytest.mark.parametrize("text", [
    "Please mute Spotify. I mean post the playback of Spotify.",
    "Mute Spotify, I mean pause the playback of Spotify.",
    "Play Spotify, actually pause it.",
])
def test_final_pause_correction_replaces_mute_and_play(text):
    commands = [{"type": "media_control", "params": {"action": action, "target": "spotify"}}
                for action in ("play", "mute")]
    result, response = _keep_spotify_correction_as_one_action(text, commands)
    assert result == [{"type": "media_control", "params": {"action": "pause", "target": "spotify"}}]
    assert response == "Spotify paused."


@pytest.mark.parametrize("text", ["Mute Spotify and play music", "Pause Spotify, actually stop the fan", "Pause Spotify, actually don't pause it"])
def test_unrelated_or_negated_requests_are_not_rewritten(text):
    commands = [{"type": "fan_control", "params": {"action": "stop"}}]
    assert _keep_spotify_correction_as_one_action(text, commands) == (commands, None)


def spotify_router(monkeypatch):
    router = MediaRouter.__new__(MediaRouter)
    device = {"id": "desktop", "is_active": True, "volume_percent": 65}
    router.spotify_client = SimpleNamespace(
        is_enabled=lambda: True, get_devices=AsyncMock(return_value=[device]),
        pause=AsyncMock(), play=AsyncMock(), set_volume=AsyncMock(),
    )
    router._ensure_computer_device = AsyncMock(return_value=(device, None))
    router._activate_device = AsyncMock(return_value="desktop")
    monkeypatch.setattr("src.media.media_router.get_audio_session_ducker", lambda: SimpleNamespace(restore_after_listening=Mock()))
    return router


@pytest.mark.asyncio
async def test_pause_requested_during_listening_is_not_undone_by_cleanup(monkeypatch):
    router = spotify_router(monkeypatch)
    state = {"spotify_was_playing": True, "spotify_device_id": "desktop", "spotify_playback_revision": 0}
    success, _ = await router.handle_media_command("pause", target="spotify")
    assert success
    await router.restore_after_listening(state)
    router.spotify_client.pause.assert_awaited_once_with(device_id="desktop")
    router.spotify_client.play.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_mute_and_unmute_preserve_previous_spotify_volume(monkeypatch):
    router = spotify_router(monkeypatch)
    assert (await router.handle_media_command("mute", target="spotify"))[0]
    assert (await router.handle_media_command("unmute", target="spotify"))[0]
    assert [call.args[0] for call in router.spotify_client.set_volume.await_args_list] == [0, 65]


@pytest.mark.asyncio
async def test_background_listening_pause_is_cancelled_before_explicit_player_command(monkeypatch):
    router = spotify_router(monkeypatch)
    events = []
    started = asyncio.Event()

    async def background_pause():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            events.append("background settled")

    task = asyncio.create_task(background_pause())
    await started.wait()
    router._listening_pause_tasks = {task}
    router.spotify_client.pause.side_effect = lambda **_: events.append("explicit pause")
    assert (await router.handle_media_command("pause", target="spotify"))[0]
    assert events == ["background settled", "explicit pause"]
