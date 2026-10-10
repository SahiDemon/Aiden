from unittest.mock import AsyncMock, Mock

import pytest

from src.core.assistant import _repair_youtube_search_request
from src.media import browser_media_controller as module
from src.media.browser_media_controller import BrowserMediaController
from src.media.media_router import MediaRouter


@pytest.mark.parametrize("provider,target", [("YouTube", "youtube"), ("YouTube Music", "youtube_music")])
def test_recovers_mood_query_instead_of_query_free_resume(provider, target):
    commands = [{"type": "media_control", "params": {"action": "play", "target": target}}]
    repaired = _repair_youtube_search_request(f"Play some relaxing music on {provider}.", commands)
    assert repaired[0]["params"] == {"action": "play_track", "target": target, "query": "relaxing music"}


@pytest.mark.parametrize("text", ["Don't play relaxing music on YouTube", "How do I play music on YouTube?", "Play it on YouTube", "Play relaxing music and turn off the fan on YouTube"])
def test_repair_does_not_invent_search_for_other_intents(text):
    assert _repair_youtube_search_request(text, []) == []


@pytest.mark.asyncio
async def test_router_preserves_query_with_generic_play():
    router = MediaRouter.__new__(MediaRouter)
    router.browser_controller = Mock(control=AsyncMock(return_value=(True, {})))
    await router.handle_media_command("play", "youtube_music", "relaxing music")
    router.browser_controller.control.assert_awaited_once_with("play_track", "youtube_music", "relaxing music")


@pytest.mark.parametrize("target,category,base", [
    ("youtube", "videos", "https://www.youtube.com"),
    ("youtube_music", "songs", "https://music.youtube.com"),
])
def test_track_opens_direct_watch_without_toggling_autoplay(monkeypatch, target, category, base):
    yt = Mock()
    yt.search.return_value = [{"videoId": "abcdefghijk", "title": "Relaxing piano"}]
    monkeypatch.setattr(module, "YTMusic", Mock(return_value=yt))
    monkeypatch.setattr(module, "YTMUSIC_AVAILABLE", True)
    opening = Mock(return_value=True)
    monkeypatch.setattr(module.webbrowser, "open", opening)
    controller = BrowserMediaController()
    controller._send_keystroke = Mock()
    success, result = controller._open_search_selection(target, "relaxing music")
    assert success
    opening.assert_called_once_with(f"{base}/watch?v=abcdefghijk&autoplay=1", new=2)
    assert result["playback_confirmed"] is False
    assert result["autoplay_requested"] is True
    assert "Relaxing piano" in result["message"]
    yt.search.assert_called_once_with("relaxing music", filter=category, limit=5)
    controller._send_keystroke.assert_not_called()


def test_playlist_uses_first_playable_track_and_playlist_id(monkeypatch):
    yt = Mock()
    yt.search.return_value = [{"browseId": "VLPLtest", "title": "Piano playlist"}]
    yt.get_playlist.return_value = {"tracks": [{"videoId": "abcdefghijk"}]}
    monkeypatch.setattr(module, "YTMusic", Mock(return_value=yt))
    monkeypatch.setattr(module, "YTMUSIC_AVAILABLE", True)
    monkeypatch.setattr(module.webbrowser, "open", Mock(return_value=True))
    success, result = BrowserMediaController()._open_search_selection("youtube_music", "piano playlist", True)
    assert success
    assert "v=abcdefghijk" in result["url"] and "list=PLtest" in result["url"]


def test_failed_resolution_opens_search_without_claiming_playback(monkeypatch):
    monkeypatch.setattr(module, "YTMUSIC_AVAILABLE", False)
    monkeypatch.setattr(module.webbrowser, "open", Mock(return_value=True))
    success, result = BrowserMediaController()._open_search_selection("youtube_music", "piano & rain")
    assert success
    assert result["url"] == "https://music.youtube.com/search?q=piano+%26+rain"
    assert not result["autoplay_requested"]
    assert "Select a result" in result["message"]


def test_browser_open_failure_is_reported(monkeypatch):
    monkeypatch.setattr(module, "YTMUSIC_AVAILABLE", False)
    monkeypatch.setattr(module.webbrowser, "open", Mock(return_value=False))
    success, _ = BrowserMediaController()._open_search_selection("youtube", "piano")
    assert not success


def test_opening_homepage_never_claims_playback_started(monkeypatch):
    monkeypatch.setattr(module, "WIN32_AVAILABLE", True)
    controller = BrowserMediaController()
    controller._find_window = Mock(return_value=None)
    controller._maybe_open_target = Mock()
    controller._send_keystroke = Mock()
    success, result = controller._control_sync("play_pause", "youtube")
    assert success
    assert not result["playback_confirmed"]
    assert "started playback" not in result["message"]
    controller._send_keystroke.assert_not_called()
