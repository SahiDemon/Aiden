import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from src.core.assistant import _repair_contextual_media_request
from src.media.browser_media_controller import BrowserMediaController
from src.media.jellyfin_client import JellyfinClient
from src.media.media_router import MediaRouter
from src.media.playback_context import select_playback


def player(target, playing=False, identifier=None):
    return {"target": target, "id": identifier or target, "is_playing": playing}


@pytest.mark.parametrize("active", ["spotify", "jellyfin", "youtube"])
def test_only_playing_session_wins_over_other_paused_players(active):
    candidates = [player(target, target == active) for target in ("spotify", "jellyfin", "youtube")]
    selected, error = select_playback(candidates, player("spotify"))
    assert selected["target"] == active
    assert not error


def test_multiple_playing_sessions_are_not_arbitrarily_ranked():
    selected, error = select_playback([player("spotify", True), player("youtube", True)])
    assert selected is None
    assert "Which one" in error


def test_resume_remembers_last_paused_session_if_it_still_exists():
    candidates = [player("spotify"), player("jellyfin")]
    assert select_playback(candidates, player("jellyfin"))[0]["target"] == "jellyfin"
    assert select_playback(candidates, player("youtube"))[0] is None


@pytest.mark.parametrize("text,action", [
    ("Pause", "pause"), ("Pause the music", "pause"), ("Please resume it", "resume"),
    ("Next song", "next"), ("Next", "next"), ("Previous video", "previous"),
    ("Can you turn the volume up?", "volume_up"), ("Lower the volume", "volume_down"),
])
def test_generic_voice_request_does_not_inherit_ai_guessed_provider(text, action):
    wrong = [{"type": "media_control", "params": {"action": action, "target": "spotify"}}]
    assert _repair_contextual_media_request(text, wrong) == [{"type": "media_control", "params": {"action": action}}]


@pytest.mark.parametrize("text", ["Pause Spotify", "Next on YouTube", "Don't pause", "How do I pause?", "Pause and open Notepad", "Increase system volume"])
def test_explicit_or_non_command_requests_are_preserved(text):
    commands = [{"type": "system_control", "params": {"action": "audio.volume_up"}}]
    assert _repair_contextual_media_request(text, commands) == commands


def make_router():
    router = MediaRouter.__new__(MediaRouter)
    router.spotify_client = SimpleNamespace(is_enabled=lambda: True, get_current_playback=AsyncMock(return_value={
        "is_playing": False, "item": {"name": "Song"}, "device": {"id": "pc", "name": "PC"},
    }))
    router.jellyfin_client = SimpleNamespace(is_enabled=lambda: True, get_sessions=AsyncMock(return_value=[{
        "Id": "tv", "NowPlayingItem": {"Name": "Movie"}, "PlayState": {"IsPaused": True},
    }]), set_paused=AsyncMock(), resume_sessions=AsyncMock(), control_session=AsyncMock())
    router.browser_controller = SimpleNamespace(get_playback_candidates=AsyncMock(return_value=[]),
        control_session=AsyncMock(return_value=(True, {"type": "browser_media", "message": "Done"})),
        control=AsyncMock(), restore_after_listening=AsyncMock())
    router._handle_spotify = AsyncMock(return_value=(True, {"type": "spotify"}))
    return router


@pytest.mark.asyncio
async def test_just_open_apps_are_not_playback_candidates():
    router = make_router()
    router.spotify_client.get_current_playback.return_value = {"is_playing": False}
    router.jellyfin_client.get_sessions.return_value = [{"Id": "tv"}]
    success, payload = await router.handle_media_command("pause")
    assert not success
    assert "can't find" in payload["message"]
    router._handle_spotify.assert_not_awaited()
    router.browser_controller.control.assert_not_awaited()


@pytest.mark.asyncio
async def test_music_playing_wins_over_open_paused_jellyfin():
    router = make_router()
    router.spotify_client.get_current_playback.return_value["is_playing"] = True
    assert (await router.handle_media_command("next"))[0]
    router._handle_spotify.assert_awaited_once_with("next", None, None, None, "PC")
    router.jellyfin_client.set_paused.assert_not_awaited()


@pytest.mark.asyncio
async def test_background_youtube_playing_wins_over_paused_spotify():
    router = make_router()
    current = player("youtube", True, "tab-1")
    router.browser_controller.get_playback_candidates.return_value = [current]
    assert (await router.handle_media_command("volume_up"))[0]
    router.browser_controller.control_session.assert_awaited_once_with("volume_up", current, None)
    router._handle_spotify.assert_not_awaited()


@pytest.mark.asyncio
async def test_jellyfin_paused_by_aiden_still_wins_and_user_pause_is_preserved(monkeypatch):
    router = make_router()
    state = {"jellyfin_session_ids": ["tv"], "browser_candidates": []}
    router._listening_context = state
    assert (await router.handle_media_command("pause"))[0]
    assert state["jellyfin_session_ids"] == []
    monkeypatch.setattr("src.media.media_router.get_audio_session_ducker", lambda: SimpleNamespace(restore_after_listening=Mock()))
    await router.restore_after_listening(state)
    router.jellyfin_client.resume_sessions.assert_not_awaited()
    router._handle_spotify.assert_not_awaited()


@pytest.mark.asyncio
async def test_pause_after_followup_capture_cancels_outer_conversation_resume(monkeypatch):
    """Reproduce the live failure: outer duck -> follow-up duck/restore -> Pause."""
    router = make_router()
    ducker = SimpleNamespace(duck_for_listening=lambda: {"muted_sessions": []}, restore_after_listening=Mock())
    monkeypatch.setattr("src.media.media_router.get_audio_session_ducker", lambda: ducker)
    router._duck_spotify_for_listening = AsyncMock(return_value=(False, None))
    router._duck_jellyfin_for_listening = AsyncMock(side_effect=[["tv"], []])
    router.browser_controller.duck_for_listening = AsyncMock(return_value={"toggled_handles": []})

    outer = await router.duck_for_listening()
    followup = await router.duck_for_listening()
    await router.restore_after_listening(followup)
    assert router._listening_context is outer

    success, payload = await router.handle_media_command("pause")
    assert success and payload["message"] == "Jellyfin paused."
    await router.restore_after_listening(outer)

    router.jellyfin_client.resume_sessions.assert_not_awaited()
    assert router._listening_context is None
    assert router._listening_contexts == []


@pytest.mark.asyncio
async def test_pause_overrides_all_outstanding_scopes_not_only_latest(monkeypatch):
    router = make_router()
    outer = {"jellyfin_session_ids": ["tv"]}
    inner = {"jellyfin_session_ids": ["tv"]}
    router._listening_contexts = [outer, inner]
    router._listening_context = inner
    assert (await router.handle_media_command("pause"))[0]
    assert outer["jellyfin_session_ids"] == []
    assert inner["jellyfin_session_ids"] == []
    monkeypatch.setattr("src.media.media_router.get_audio_session_ducker", lambda: SimpleNamespace(restore_after_listening=Mock()))
    await router.restore_after_listening(inner)
    await router.restore_after_listening(outer)
    router.jellyfin_client.resume_sessions.assert_not_awaited()


@pytest.mark.asyncio
async def test_browser_pause_after_followup_cancels_outer_native_resume(monkeypatch):
    router = make_router()
    current = player("youtube", False, "video")
    router.browser_controller.get_playback_candidates.return_value = [current]
    outer = {"browser_candidates": [{**current, "is_playing": True}],
             "browser_media": {"paused_sessions": [current]}}
    inner = {"browser_media": {"toggled_handles": []}}
    router._listening_contexts = [outer, inner]
    router._listening_context = inner
    monkeypatch.setattr("src.media.media_router.get_audio_session_ducker", lambda: SimpleNamespace(restore_after_listening=Mock()))

    await router.restore_after_listening(inner)
    assert (await router.handle_media_command("pause"))[0]
    assert outer["browser_media"]["paused_sessions"] == []
    await router.restore_after_listening(outer)
    assert router.browser_controller.restore_after_listening.call_args.args[0]["paused_sessions"] == []


@pytest.mark.asyncio
async def test_unrelated_followup_still_restores_original_media_once(monkeypatch):
    router = make_router()
    outer = {"jellyfin_session_ids": ["tv"]}
    inner = {"jellyfin_session_ids": []}
    router._listening_contexts = [outer, inner]
    router._listening_context = inner
    monkeypatch.setattr("src.media.media_router.get_audio_session_ducker", lambda: SimpleNamespace(restore_after_listening=Mock()))
    await router.restore_after_listening(inner)
    router.jellyfin_client.resume_sessions.assert_not_awaited()
    await router.restore_after_listening(outer)
    router.jellyfin_client.resume_sessions.assert_awaited_once_with(["tv"])


@pytest.mark.asyncio
async def test_generic_jellyfin_pause_only_affects_the_playing_session():
    router = make_router()
    router.jellyfin_client.get_sessions.return_value.append({
        "Id": "desktop", "NowPlayingItem": {"Name": "Episode"}, "PlayState": {"IsPaused": False},
    })
    assert (await router.handle_media_command("pause"))[0]
    router.jellyfin_client.set_paused.assert_awaited_once_with("desktop", paused=True)


@pytest.mark.asyncio
async def test_browser_pause_during_listen_is_not_toggled_back_on(monkeypatch):
    router = make_router()
    current = player("youtube", False, "tab-1")
    router.browser_controller.get_playback_candidates.return_value = [current]
    state = {"browser_candidates": [{**current, "is_playing": True}],
             "browser_media": {"paused_sessions": [current], "toggled_handles": []}}
    router._listening_context = state
    assert (await router.handle_media_command("pause"))[0]
    assert state["browser_media"]["paused_sessions"] == []
    monkeypatch.setattr("src.media.media_router.get_audio_session_ducker", lambda: SimpleNamespace(restore_after_listening=Mock()))
    await router.restore_after_listening(state)
    assert router.browser_controller.restore_after_listening.call_args.args[0]["paused_sessions"] == []


@pytest.mark.asyncio
async def test_browser_native_controls_are_idempotent_not_keyboard_toggles():
    session = SimpleNamespace(try_pause_async=AsyncMock(return_value=True), try_play_async=AsyncMock(return_value=True),
                              try_skip_next_async=AsyncMock(return_value=True))
    controller = BrowserMediaController()
    candidate = {"native_session": session}
    assert (await controller.control_session("pause", candidate))[0]
    assert (await controller.control_session("resume", candidate))[0]
    assert (await controller.control_session("next", candidate))[0]
    session.try_pause_async.assert_awaited_once()
    session.try_play_async.assert_awaited_once()
    session.try_skip_next_async.assert_awaited_once()


@pytest.mark.asyncio
async def test_native_player_rejection_is_not_reported_as_success():
    controller = BrowserMediaController()
    result = await controller.control_session("next", {"native_session": SimpleNamespace(try_skip_next_async=AsyncMock(return_value=False))})
    assert not result[0]


@pytest.mark.asyncio
async def test_native_duck_restores_only_sessions_it_successfully_paused():
    controller = BrowserMediaController()
    playing = SimpleNamespace(try_pause_async=AsyncMock(return_value=True), try_play_async=AsyncMock(return_value=True))
    paused = SimpleNamespace(try_pause_async=AsyncMock(return_value=True), try_play_async=AsyncMock(return_value=True))
    disappeared = SimpleNamespace(try_pause_async=AsyncMock(side_effect=OSError("closed")))
    controller.get_playback_candidates = AsyncMock(return_value=[
        {"is_playing": True, "native_session": playing},
        {"is_playing": True, "native_session": disappeared},
        {"is_playing": False, "native_session": paused},
    ])
    state = await controller.duck_for_listening()
    await controller.restore_after_listening(state)
    playing.try_play_async.assert_awaited_once()
    paused.try_play_async.assert_not_awaited()
    paused.try_pause_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_skip_keeps_idempotent_native_restore_for_previously_playing_media():
    router = make_router()
    current = player("youtube", False, "tab-1")
    router.browser_controller.get_playback_candidates.return_value = [current]
    state = {"browser_candidates": [{**current, "is_playing": True}],
             "browser_media": {"paused_sessions": [current], "toggled_handles": []}}
    router._listening_context = state
    await router.handle_media_command("next")
    assert state["browser_media"]["paused_sessions"] == [current]


@pytest.mark.asyncio
async def test_native_browser_session_detection_uses_playback_status(monkeypatch):
    module = pytest.importorskip("winrt.windows.media.control")
    status = module.GlobalSystemMediaTransportControlsSessionPlaybackStatus
    def native(source, playback, title):
        return SimpleNamespace(source_app_user_model_id=source,
            get_playback_info=lambda: SimpleNamespace(playback_status=playback),
            try_get_media_properties_async=AsyncMock(return_value=SimpleNamespace(title=title)))
    sessions = [native("Chrome", status.PLAYING, "Current video"),
                native("MSEdge", status.PAUSED, "Paused video"),
                native("Chrome", status.STOPPED, "Idle tab"),
                native("Spotify", status.PLAYING, "Song")]
    monkeypatch.setattr(module, "GlobalSystemMediaTransportControlsSessionManager", SimpleNamespace(
        request_async=AsyncMock(return_value=SimpleNamespace(get_sessions=lambda: sessions))))
    candidates = await BrowserMediaController().get_playback_candidates()
    assert [c["is_playing"] for c in candidates] == [True, False]
    assert [c["title"] for c in candidates] == ["Current video", "Paused video"]


@pytest.mark.asyncio
async def test_relative_spotify_volume_is_clamped_on_selected_device():
    router = MediaRouter.__new__(MediaRouter)
    device = {"id": "pc", "name": "PC", "type": "Computer", "is_active": True, "volume_percent": 95}
    router.spotify_client = SimpleNamespace(is_enabled=lambda: True,
        get_devices=AsyncMock(return_value=[device]), set_volume=AsyncMock())
    router._activate_device = AsyncMock(return_value="pc")
    success, _ = await router._handle_spotify("volume_up", None, None, None, None)
    assert success
    router.spotify_client.set_volume.assert_awaited_once_with(100, device_id="pc")


@pytest.mark.asyncio
async def test_user_command_cancels_background_pause_before_changing_playback():
    router = make_router()
    started, finished = asyncio.Event(), asyncio.Event()
    async def background():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()
    task = asyncio.create_task(background())
    await started.wait()
    router._listening_pause_tasks = {task}
    router.spotify_client.get_current_playback.return_value["is_playing"] = True
    await router.handle_media_command("next")
    assert task.cancelled() and finished.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("action,path,body", [
    ("next", "Playing/NextTrack", None), ("previous", "Playing/PreviousTrack", None),
    ("volume_up", "Command/VolumeUp", None),
    ("set_volume", "Command", {"Name": "SetVolume", "Arguments": {"Volume": "35"}}),
])
async def test_jellyfin_session_command_uses_remote_control_api(monkeypatch, action, path, body):
    from src.media import jellyfin_client as module
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(204)
    client_class = httpx.AsyncClient
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kwargs: client_class(transport=httpx.MockTransport(respond), **kwargs))
    client = JellyfinClient.__new__(JellyfinClient)
    client.settings = SimpleNamespace(app=SimpleNamespace(jellyfin_url="http://jellyfin.test", jellyfin_api_key="test"))
    await client.control_session("tv", action, 35)
    assert requests[0].url.path == f"/Sessions/tv/{path}"
    if body is None:
        assert requests[0].content == b""
    else:
        assert json.loads(requests[0].content) == body
