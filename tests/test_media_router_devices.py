import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.media.media_router import MediaRouter
from src.media.spotify_client import SpotifyError


class MediaRouterDevicesTests(unittest.IsolatedAsyncioTestCase):
    async def test_ensure_computer_device_found(self):
        router = MediaRouter()
        router._maybe_launch_spotify_desktop = AsyncMock(return_value=True)
        router.spotify_client.get_devices = AsyncMock(return_value=[
            {"name": "DESKTOP-PC", "id": "pc1", "type": "Computer", "is_active": True}
        ])

        device, err = await router._ensure_computer_device()
        self.assertIsNotNone(device)
        self.assertEqual(device["id"], "pc1")
        self.assertIsNone(err)

    async def test_ensure_computer_device_not_found_after_launch(self):
        router = MediaRouter()
        router._maybe_launch_spotify_desktop = AsyncMock(return_value=True)
        router.spotify_client.get_devices = AsyncMock(return_value=[])

        device, err = await router._ensure_computer_device()
        self.assertIsNone(device)
        self.assertIsNotNone(err)
        self.assertIn("could not connect to desktop player yet", err["message"])

    async def test_ensure_spotify_device_found(self):
        router = MediaRouter()
        router._maybe_launch_spotify_desktop = AsyncMock(return_value=True)
        router.spotify_client.get_devices = AsyncMock(return_value=[
            {"name": "Living Room TV", "id": "tv1", "type": "TV", "is_active": False}
        ])

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
