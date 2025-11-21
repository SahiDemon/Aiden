"""
Media router that prioritizes Spotify or browser-based media control.
"""
from __future__ import annotations

import asyncio
from typing import Optional, Tuple

# from src.execution.app_launcher import get_app_launcher  <-- Moved to inside method to avoid circular import
from src.media.browser_media_controller import get_browser_media_controller
from src.media.spotify_client import (
    SpotifyClient,
    SpotifyError,
    SpotifyNotConfiguredError,
    get_spotify_client,
)
from src.media.spotify_utils import find_best_device
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MediaRouter:
    """Routes media commands to Spotify or browser controllers."""

    def __init__(self):
        self.spotify_client: SpotifyClient = get_spotify_client()
        self.browser_controller = get_browser_media_controller()
        self.settings = get_settings()
        from src.execution.app_launcher import get_app_launcher
        self.app_launcher = get_app_launcher()

    async def handle_media_command(
        self,
        action: str,
        target: Optional[str] = None,
        query: Optional[str] = None,
        entity_type: Optional[str] = None,
        volume: Optional[int] = None,
        device_name: Optional[str] = None,
    ) -> Tuple[bool, dict]:
        action = action.lower()
        if target in {"youtube", "youtube_music"}:
            return await self.browser_controller.control(action_alias(action), target, query)
        if target == "spotify":
            return await self._handle_spotify(action, query, entity_type, volume, device_name)
        # Generic route: prefer Spotify if actively playing
        if await self._spotify_is_active():
            return await self._handle_spotify(action, query, entity_type, volume, device_name)
        return await self.browser_controller.control(action_alias(action), None)

    async def _spotify_is_active(self) -> bool:
        if not self.spotify_client.is_enabled():
            return False
        playback = await self.spotify_client.get_current_playback()
        return bool(playback and playback.get("is_playing"))

    async def _handle_spotify(
        self,
        action: str,
        query: Optional[str],
        entity_type: Optional[str],
        volume: Optional[int],
        device_name: Optional[str],
    ) -> Tuple[bool, dict]:
        if not self.spotify_client.is_enabled():
            logger.warning("Spotify integration requested but not configured.")
            return False, {"type": "spotify", "message": "Spotify integration is not configured."}

        try:
            # Get available devices
            devices = await self.spotify_client.get_devices()
            device = next((d for d in devices if d["is_active"]), None)
            if not device and devices:
                device = devices[0]
            
            # We pass 'device' (which might be None) to _activate_device, 
            # which will handle launching and retrying if needed.
            device_id = device["id"] if device else None

            if action == "resume":
                device_id = await self._activate_device(device, play=True)
                if not device_id:
                    await self.spotify_client.play()
                return True, {"type": "spotify", "message": "Spotify playback resumed."}

            if action == "play":
                # "Play something" -> Default to Liked Songs
                device_id = await self._activate_device(device, play=False)
                await self.spotify_client.play(context_uri="spotify:collection:tracks", device_id=device_id)
                return True, {"type": "spotify", "message": "Playing your Liked Songs on Spotify."}

            if action == "pause":
                device_id = await self._activate_device(device, play=False)
                await self.spotify_client.pause(device_id=device_id)
                return True, {"type": "spotify", "message": "Spotify paused."}

            if action == "next":
                device_id = await self._activate_device(device, play=False)
                await self.spotify_client.next_track(device_id=device_id)
                return True, {"type": "spotify", "message": "Skipped to the next Spotify track."}

            if action == "previous":
                device_id = await self._activate_device(device, play=False)
                await self.spotify_client.previous_track(device_id=device_id)
                return True, {"type": "spotify", "message": "Returned to the previous Spotify track."}

            if action == "set_volume" and volume is not None:
                device_id = await self._activate_device(device, play=False)
                await self.spotify_client.set_volume(volume, device_id=device_id)
                return True, {"type": "spotify", "message": f"Spotify volume set to {volume}%."}

            if action == "play_track" and query:
                device_id = await self._activate_device(device, play=False)
                await self._play_track_by_query(query, device_id)
                return True, {"type": "spotify", "message": f"Playing '{query}' on Spotify."}

            if action == "play_playlist" and query:
                device_id = await self._activate_device(device, play=False)
                await self._play_playlist_by_query(query, device_id)
                return True, {"type": "spotify", "message": f"Playing playlist '{query}' on Spotify."}

            if action == "transfer":
                if not device:
                    return False, {"type": "spotify", "message": "No Spotify devices available to transfer to."}
                await self.spotify_client.transfer_playback(device["id"], play=True)
                return True, {"type": "spotify", "message": f"Spotify playback moved to {device['name']}."}

            if action == "play_liked_songs":
                device_id = await self._activate_device(device, play=False)
                await self.spotify_client.play(context_uri="spotify:collection:tracks", device_id=device_id)
                return True, {"type": "spotify", "message": "Playing your Liked Songs on Spotify."}

            logger.error(f"Unsupported Spotify action: {action}")
            return False, {"type": "spotify", "message": "Unsupported Spotify action."}
        except SpotifyNotConfiguredError:
            return False, {"type": "spotify", "message": "Spotify credentials are not configured."}
        except SpotifyError as exc:
            return False, {"type": "spotify", "message": f"Spotify error: {exc}"}

    async def _play_track_by_query(self, query: str, device_id: Optional[str]):
        results = await self.spotify_client.search(query, ["track"])
        tracks = (results or {}).get("tracks", {}).get("items", [])
        if not tracks:
            raise SpotifyError("No matching track found.")
        uri = tracks[0]["uri"]
        await self.spotify_client.play(uris=[uri], device_id=device_id)

    async def _play_playlist_by_query(self, query: str, device_id: Optional[str]):
        results = await self.spotify_client.search(query, ["playlist"])
        playlists = (results or {}).get("playlists", {}).get("items", [])
        if not playlists:
            raise SpotifyError("No matching playlist found.")
        uri = playlists[0]["uri"]
        await self.spotify_client.play(context_uri=uri, device_id=device_id)

    async def _ensure_spotify_device(self, requested_device: Optional[str]) -> Tuple[Optional[dict], Optional[dict]]:
        preference = requested_device or self.settings.spotify.default_device_name
        devices = await self.spotify_client.get_devices()
        device = find_best_device(devices, preference)
        if device:
            return device, None

        logger.info("No Spotify devices available; attempting to launch Spotify desktop.")
        if not await self._maybe_launch_spotify_desktop():
            return None, {
                "type": "spotify",
                "message": "Spotify desktop is not running and could not be launched automatically.",
            }

        for attempt in range(6):
            await asyncio.sleep(2)
            devices = await self.spotify_client.get_devices()
            device = find_best_device(devices, preference)
            if device:
                logger.info(f"Spotify device '{device['name']}' became available after auto-launch.")
                return device, None

        return None, {
            "type": "spotify",
            "message": "Spotify started, but no playback devices are available yet. Please open Spotify and try again.",
        }

    async def _maybe_launch_spotify_desktop(self) -> bool:
        try:
            launched = await self.app_launcher.launch("spotify")
            if launched:
                logger.info("Spotify desktop launched to satisfy media request.")
            return launched
        except Exception as exc:
            logger.error(f"Failed to launch Spotify desktop: {exc}")
            return False

    async def _activate_device(self, device: Optional[dict], play: bool = False) -> Optional[str]:
        """
        Ensure a device is active. If no device is provided, try to find one.
        Returns the device ID if one is active/activated, or None.
        """
        if device:
            # If we already have a device, just transfer playback if needed
            if not device.get("is_active"):
                await self.spotify_client.transfer_playback(device["id"], play=play)
                # Allow some time for the transfer to propagate
                await asyncio.sleep(0.5)
            return device["id"]

        # No device provided, try to find one with retries
        logger.info("No active device found. Attempting to find or launch Spotify...")
        
        for attempt in range(1, 6):
            devices = await self.spotify_client.get_devices()
            if devices:
                # Pick the first available device
                target_device = devices[0]
                logger.info(f"Found device '{target_device['name']}' on attempt {attempt}.")
                await self.spotify_client.transfer_playback(target_device["id"], play=play)
                # Allow time for the device to become ready
                await asyncio.sleep(1.5)
                return target_device["id"]
            
            logger.info(f"No devices found on attempt {attempt}. Waiting...")
            if attempt == 1:
                # On first failure, try to launch Spotify via app launcher if possible
                try:
                    logger.info("Launching Spotify application...")
                    await self.app_launcher.launch_app("spotify")
                except Exception as e:
                    logger.warning(f"Failed to launch Spotify: {e}")
            
            # Wait with exponential backoff: 2, 4, 6, 8, 10 seconds
            await asyncio.sleep(attempt * 2)
            
        logger.error("Failed to find any Spotify devices after multiple attempts.")
        return None


def action_alias(action: str) -> str:
    """Translate generic actions to browser controller equivalents."""
    mapping = {
        "play": "play_pause",
        "resume": "play_pause",
        "pause": "play_pause",
        "next": "next",
        "previous": "previous",
        "mute": "mute",
        "unmute": "unmute",
        "seek_forward": "seek_forward",
        "seek_backward": "seek_backward",
        "play_pause": "play_pause",
    }
    return mapping.get(action, action)


# Global instance -------------------------------------------------------------
_media_router: Optional[MediaRouter] = None


def get_media_router() -> MediaRouter:
    global _media_router
    if _media_router is None:
        _media_router = MediaRouter()
    return _media_router
