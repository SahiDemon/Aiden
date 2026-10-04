import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, call, patch

from src.media.media_router import MediaRouter, _select_jellyfin_title
from src.media.spotify_client import SpotifyError


class MediaRouterDevicesTests(unittest.IsolatedAsyncioTestCase):
    async def test_jellyfin_pause_and_resume_active_session(self):
        router = MediaRouter()
        router.jellyfin_client.is_enabled = MagicMock(return_value=True)
        router.jellyfin_client.get_sessions = AsyncMock(return_value=[
            {"Id": "living-room", "NowPlayingItem": {"Name": "Movie"}, "PlayState": {"IsPaused": False}}
        ])
        router.jellyfin_client.set_paused = AsyncMock()

        success, payload = await router.handle_media_command("pause", target="jellyfin")

        self.assertTrue(success)
        self.assertEqual(payload["message"], "Jellyfin paused.")
        router.jellyfin_client.set_paused.assert_awaited_once_with("living-room", paused=True)

    async def test_jellyfin_duck_restores_only_previously_playing_session(self):
        router = MediaRouter()
        router.jellyfin_client.is_enabled = MagicMock(return_value=True)
        router.jellyfin_client.get_sessions = AsyncMock(return_value=[
            {"Id": "playing", "NowPlayingItem": {"Name": "Movie"}, "PlayState": {"IsPaused": False}},
            {"Id": "paused", "NowPlayingItem": {"Name": "Episode"}, "PlayState": {"IsPaused": True}},
        ])
        router.jellyfin_client.set_paused = AsyncMock()

        state = await router._duck_jellyfin_for_listening()
        await router.restore_after_listening({"jellyfin_session_ids": state})

        self.assertEqual(state, ["playing"])
        self.assertEqual(
            router.jellyfin_client.set_paused.await_args_list,
            [call("playing", paused=True), call("playing", paused=False)],
        )

    async def test_jellyfin_plays_matching_movie_on_connected_player(self):
        router = MediaRouter()
        router.jellyfin_client.is_enabled = MagicMock(return_value=True)
        router.jellyfin_client.get_sessions = AsyncMock(return_value=[
            {"Id": "tv", "SupportsRemoteControl": True}
        ])
        router.jellyfin_client.search_titles = AsyncMock(return_value=[
            {"Id": "movie-id", "Type": "Movie", "Name": "Arrival", "ProductionYear": 2016}
        ])
        router.jellyfin_client.list_titles = AsyncMock()
        router.jellyfin_client.play_item = AsyncMock()

        success, payload = await router.handle_media_command("play_track", target="jellyfin", query="Arrival")

        self.assertTrue(success)
        self.assertEqual(payload["message"], "Playing Arrival (2016) on Jellyfin.")
        router.jellyfin_client.play_item.assert_awaited_once_with("tv", "movie-id")
        router.jellyfin_client.list_titles.assert_not_awaited()

    async def test_jellyfin_exact_movie_wins_over_partial_sequel(self):
        router = MediaRouter()
        router.jellyfin_client.is_enabled = MagicMock(return_value=True)
        router.jellyfin_client.get_sessions = AsyncMock(return_value=[{"Id": "tv", "UserId": "viewer"}])
        router.jellyfin_client.search_titles = AsyncMock(return_value=[
            {"Id": "sequel", "Type": "Movie", "Name": "Blade Runner 2049"},
            {"Id": "original", "Type": "Movie", "Name": "Blade Runner"},
        ])
        router.jellyfin_client.play_item = AsyncMock()

        success, _ = await router.handle_media_command("play_title", target="jellyfin", query="Blade Runner")

        self.assertTrue(success)
        router.jellyfin_client.play_item.assert_awaited_once_with("tv", "original")

    async def test_jellyfin_small_typo_uses_clear_catalog_match(self):
        router = MediaRouter()
        router.jellyfin_client.is_enabled = MagicMock(return_value=True)
        router.jellyfin_client.get_sessions = AsyncMock(return_value=[{"Id": "tv"}])
        router.jellyfin_client.search_titles = AsyncMock(return_value=[])
        router.jellyfin_client.list_titles = AsyncMock(return_value=[
            {"Id": "original", "Type": "Movie", "Name": "Blade Runner"},
            {"Id": "sequel", "Type": "Movie", "Name": "Blade Runner 2049"},
        ])
        router.jellyfin_client.play_item = AsyncMock()

        success, _ = await router.handle_media_command("play_title", target="jellyfin", query="Blad Runner")

        self.assertTrue(success)
        router.jellyfin_client.play_item.assert_awaited_once_with("tv", "original")

    async def test_jellyfin_friends_uses_next_up_before_an_older_partial_episode(self):
        router = MediaRouter()
        router.jellyfin_client.is_enabled = MagicMock(return_value=True)
        router.jellyfin_client.get_sessions = AsyncMock(return_value=[{"Id": "tv", "UserId": "viewer"}])
        router.jellyfin_client.search_titles = AsyncMock(return_value=[
            {"Id": "wrong-movie", "Type": "Movie", "Name": "My Friends Hot Mom"},
            {"Id": "friends-series", "Type": "Series", "Name": "Friends"},
            {"Id": "duplicate-friends-series", "Type": "Series", "Name": "Friends"},
        ])
        router.jellyfin_client.list_titles = AsyncMock(return_value=[
            {"Id": "friends-series", "Type": "Series", "Name": "Friends"},
        ])
        router.jellyfin_client.get_resume_episodes = AsyncMock(return_value=[
            {"Id": "episode", "SeriesId": "friends-series", "ParentIndexNumber": 3, "IndexNumber": 12,
             "UserData": {"PlaybackPositionTicks": 123456, "Played": False, "LastPlayedDate": "2026-09-22"}},
        ])
        router.jellyfin_client.get_next_up_episode = AsyncMock(return_value={
            "Id": "next-up", "SeriesId": "friends-series", "ParentIndexNumber": 7, "IndexNumber": 19,
        })
        router.jellyfin_client.play_item = AsyncMock()

        success, payload = await router.handle_media_command("play_title", target="jellyfin", query="Friends")

        self.assertTrue(success)
        self.assertEqual(payload["message"], "Playing Friends S7 E19 on Jellyfin.")
        router.jellyfin_client.play_item.assert_awaited_once_with("tv", "next-up")

    async def test_jellyfin_falls_back_to_a_partial_episode_when_next_up_is_unavailable(self):
        router = MediaRouter()
        router.jellyfin_client.is_enabled = MagicMock(return_value=True)
        router.jellyfin_client.get_sessions = AsyncMock(return_value=[{"Id": "tv", "UserId": "viewer"}])
        router.jellyfin_client.search_titles = AsyncMock(return_value=[
            {"Id": "friends-series", "Type": "Series", "Name": "Friends"},
        ])
        router.jellyfin_client.get_next_up_episode = AsyncMock(return_value=None)
        router.jellyfin_client.get_resume_episodes = AsyncMock(return_value=[
            {"Id": "episode", "SeriesId": "friends-series", "ParentIndexNumber": 3, "IndexNumber": 12,
             "UserData": {"PlaybackPositionTicks": 123456, "Played": False, "LastPlayedDate": "2026-09-22"}},
        ])
        router.jellyfin_client.play_item = AsyncMock()

        success, payload = await router.handle_media_command("play_title", target="jellyfin", query="Friends")

        self.assertTrue(success)
        self.assertEqual(payload["message"], "Resuming Friends S3 E12 on Jellyfin.")
        router.jellyfin_client.play_item.assert_awaited_once_with("tv", "episode", start_position_ticks=123456)

    async def test_jellyfin_friends_uses_next_up_when_no_episode_is_in_progress(self):
        router = MediaRouter()
        router.jellyfin_client.is_enabled = MagicMock(return_value=True)
        router.jellyfin_client.get_sessions = AsyncMock(return_value=[{"Id": "tv", "UserId": "viewer"}])
        router.jellyfin_client.search_titles = AsyncMock(return_value=[
            {"Id": "series", "Type": "Series", "Name": "Friends"},
        ])
        router.jellyfin_client.get_resume_episodes = AsyncMock(return_value=[])
        router.jellyfin_client.get_next_up_episode = AsyncMock(return_value={
            "Id": "next-episode", "SeriesId": "series", "ParentIndexNumber": 2, "IndexNumber": 5,
        })
        router.jellyfin_client.play_item = AsyncMock()

        success, payload = await router.handle_media_command("play_title", target="jellyfin", query="Friends")

        self.assertTrue(success)
        self.assertEqual(payload["message"], "Playing Friends S2 E5 on Jellyfin.")
        router.jellyfin_client.play_item.assert_awaited_once_with("tv", "next-episode")

    async def test_jellyfin_series_opens_player_before_looking_up_progress(self):
        router = MediaRouter()
        router.jellyfin_client.is_enabled = MagicMock(return_value=True)
        router.jellyfin_client.get_sessions = AsyncMock(side_effect=[
            [], [{"Id": "desktop-player", "UserId": "viewer", "SupportsRemoteControl": True}],
        ])
        router.jellyfin_client.search_titles = AsyncMock(return_value=[
            {"Id": "friends", "Type": "Series", "Name": "Friends"},
        ])
        router.jellyfin_client.get_resume_episodes = AsyncMock(return_value=[])
        router.jellyfin_client.get_next_up_episode = AsyncMock(return_value={
            "Id": "episode", "SeriesId": "friends", "ParentIndexNumber": 1, "IndexNumber": 1,
        })
        router.jellyfin_client.play_item = AsyncMock()
        router.app_launcher.launch_app = AsyncMock(return_value=True)

        with patch("src.media.media_router.asyncio.sleep", new=AsyncMock()):
            success, payload = await router.handle_media_command("play_title", target="jellyfin", query="Friends")

        self.assertTrue(success)
        self.assertEqual(payload["message"], "Playing Friends S1 E1 on Jellyfin.")
        router.app_launcher.launch_app.assert_awaited_once_with("jellyfin")
        router.jellyfin_client.play_item.assert_awaited_once_with("desktop-player", "episode")

    async def test_jellyfin_unclear_partial_title_never_opens_player(self):
        router = MediaRouter()
        router.jellyfin_client.is_enabled = MagicMock(return_value=True)
        router.jellyfin_client.get_sessions = AsyncMock(return_value=[])
        router.jellyfin_client.search_titles = AsyncMock(return_value=[
            {"Id": "wrong-movie", "Type": "Movie", "Name": "My Friends Hot Mom"},
        ])
        router.jellyfin_client.list_titles = AsyncMock(return_value=[
            {"Id": "wrong-movie", "Type": "Movie", "Name": "My Friends Hot Mom"},
        ])
        router.app_launcher.launch_app = AsyncMock()

        success, _ = await router.handle_media_command("play_title", target="jellyfin", query="Friends")

        self.assertFalse(success)
        router.app_launcher.launch_app.assert_not_awaited()

    def test_jellyfin_rejects_ambiguous_similar_titles(self):
        candidates = [
            {"Id": "one", "Type": "Movie", "Name": "The Friend"},
            {"Id": "two", "Type": "Movie", "Name": "A Friend"},
        ]
        self.assertIsNone(_select_jellyfin_title("Frend", candidates, {"Movie"}))

    async def test_jellyfin_launches_player_when_no_session_exists(self):
        router = MediaRouter()
        router.app_launcher.launch_app = AsyncMock(return_value=True)
        router.jellyfin_client.get_sessions = AsyncMock(side_effect=[
            [], [{"Id": "desktop-player", "SupportsRemoteControl": True}]
        ])

        with patch("src.media.media_router.asyncio.sleep", new=AsyncMock()):
            player, sessions = await router._ensure_jellyfin_player([])

        self.assertEqual(player["Id"], "desktop-player")
        self.assertEqual(len(sessions), 1)
        router.app_launcher.launch_app.assert_awaited_once_with("jellyfin")

    async def test_ensure_computer_device_found(self):
        router = MediaRouter()
        router._maybe_launch_spotify_desktop = AsyncMock(return_value=True)
        router.spotify_client.get_devices = AsyncMock(return_value=[
            {"name": "DESKTOP-PC", "id": "pc1", "type": "Computer", "is_active": True}
        ])

        with patch("src.media.media_router.asyncio.sleep", new=AsyncMock()):
            device, err = await router._ensure_computer_device()
        self.assertIsNotNone(device)
        self.assertEqual(device["id"], "pc1")
        self.assertIsNone(err)

    async def test_ensure_computer_device_waits_for_delayed_registration(self):
        router = MediaRouter()
        router._maybe_launch_spotify_desktop = AsyncMock(return_value=True)
        computer = {
            "name": "DESKTOP-PC",
            "id": "pc1",
            "type": "Computer",
            "is_active": False,
        }
        router.spotify_client.get_devices = AsyncMock(
            side_effect=[[], [], [], [computer]]
        )

        sleep = AsyncMock()
        with patch("src.media.media_router.asyncio.sleep", new=sleep):
            device, err = await router._ensure_computer_device()

        self.assertEqual(device, computer)
        self.assertIsNone(err)
        self.assertEqual(router.spotify_client.get_devices.await_count, 4)
        self.assertEqual(
            [call.args[0] for call in sleep.await_args_list],
            [1.0, 1.0, 2.0, 2.0],
        )

    async def test_ensure_computer_device_not_found_after_launch(self):
        router = MediaRouter()
        router._maybe_launch_spotify_desktop = AsyncMock(return_value=True)
        router.spotify_client.get_devices = AsyncMock(return_value=[])

        sleep = AsyncMock()
        with patch("src.media.media_router.asyncio.sleep", new=sleep):
            device, err = await router._ensure_computer_device()
        self.assertIsNone(device)
        self.assertIsNotNone(err)
        self.assertIn("did not become ready within 30 seconds", err["message"])
        self.assertEqual(sum(call.args[0] for call in sleep.await_args_list), 30.0)

    async def test_ensure_spotify_device_found(self):
        router = MediaRouter()
        router._maybe_launch_spotify_desktop = AsyncMock(return_value=True)
        router.spotify_client.get_devices = AsyncMock(return_value=[
            {"name": "Living Room TV", "id": "tv1", "type": "TV", "is_active": False}
        ])

        with patch("src.media.media_router.asyncio.sleep", new=AsyncMock()):
            device, err = await router._ensure_spotify_device("Living Room TV")
        self.assertIsNotNone(device)
        self.assertEqual(device["id"], "tv1")
        self.assertIsNone(err)

    async def test_play_track_by_query_raises_when_no_match(self):
        router = MediaRouter()
        router.spotify_client.search = AsyncMock(return_value={"tracks": {"items": []}})

        with self.assertRaises(SpotifyError):
            await router._play_track_by_query("unknown track", None)


if __name__ == "__main__":
    unittest.main()
