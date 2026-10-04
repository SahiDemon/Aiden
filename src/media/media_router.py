"""
Media router that routes Spotify, Jellyfin, and browser-based media control.
"""
from __future__ import annotations

import asyncio
from typing import Optional, Tuple

# from src.execution.app_launcher import get_app_launcher  <-- Moved to inside method to avoid circular import
from src.media.audio_session_ducker import get_audio_session_ducker
from src.media.browser_media_controller import get_browser_media_controller
from src.media.jellyfin_client import (
    JellyfinClient,
    JellyfinError,
    JellyfinNotConfiguredError,
    get_jellyfin_client,
)
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

_SPOTIFY_DUCK_DEADLINE_SECONDS = 0.6
# Spotify Connect can take noticeably longer to expose the Windows desktop
# player after a cold launch or OAuth reauthorization. Poll quickly at first,
# then back off while allowing up to 30 seconds for device registration.
_SPOTIFY_DESKTOP_POLL_DELAYS_SECONDS = (1.0, 1.0, 2.0, 2.0, 3.0, 3.0, 4.0, 4.0, 5.0, 5.0)


class MediaRouter:
    """Routes media commands to Spotify, Jellyfin, or browser controllers."""

    def __init__(self):
        self.spotify_client: SpotifyClient = get_spotify_client()
        self.jellyfin_client: JellyfinClient = get_jellyfin_client()
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
        target = target.lower() if target else None
        if target in {"youtube", "youtube_music"}:
            return await self.browser_controller.control(action_alias(action), target, query)
        if target == "spotify":
            return await self._handle_spotify(action, query, entity_type, volume, device_name)
        if target == "jellyfin":
            return await self._handle_jellyfin(action)
        # Generic route: prefer Spotify if actively playing
        if await self._spotify_is_active():
            return await self._handle_spotify(action, query, entity_type, volume, device_name)
        return await self.browser_controller.control(action_alias(action), None)

    async def duck_for_listening(self) -> dict:
        """Best-effort pause of active media without delaying microphone readiness."""
        state = {
            "spotify_was_playing": False,
            "spotify_device_id": None,
            "jellyfin_session_ids": [],
            "browser_media": {"toggled_handles": []},
            "muted_app_sessions": {"muted_sessions": []},
        }

        # Local session enumeration and the Spotify network request can run in
        # parallel. Spotify gets a strict deadline so a slow API never leaves
        # the wake acknowledgement waiting for several seconds.
        loop = asyncio.get_running_loop()
        readiness_started = loop.time()
        spotify_duck_task = asyncio.create_task(self._duck_spotify_for_listening())
        jellyfin_duck_task = asyncio.create_task(self._duck_jellyfin_for_listening())
        browser_controller = getattr(self, "browser_controller", None)
        browser_duck_task = (
            asyncio.create_task(browser_controller.duck_for_listening())
            if browser_controller is not None
            else None
        )

        # Let the Spotify coroutine initiate its request, then perform local
        # COM audio-session work on the owning Windows event-loop thread.
        await asyncio.sleep(0)
        try:
            state["muted_app_sessions"] = get_audio_session_ducker().duck_for_listening()
        except Exception as exc:
            logger.debug(f"App-session ducking skipped: {exc}")

        try:
            remaining = _SPOTIFY_DUCK_DEADLINE_SECONDS - (loop.time() - readiness_started)
            if remaining <= 0:
                spotify_duck_task.cancel()
                try:
                    await spotify_duck_task
                except asyncio.CancelledError:
                    pass
                raise TimeoutError
            spotify_was_playing, spotify_device_id = await asyncio.wait_for(
                spotify_duck_task,
                timeout=remaining,
            )
            state["spotify_was_playing"] = spotify_was_playing
            state["spotify_device_id"] = spotify_device_id
        except TimeoutError:
            logger.debug(
                "Spotify ducking exceeded %.1fs readiness deadline; continuing without it.",
                _SPOTIFY_DUCK_DEADLINE_SECONDS,
            )
        except Exception as exc:
            logger.debug(f"Spotify ducking skipped: {exc}")

        try:
            if jellyfin_duck_task.done():
                state["jellyfin_session_ids"] = jellyfin_duck_task.result()
            else:
                remaining = _SPOTIFY_DUCK_DEADLINE_SECONDS - (loop.time() - readiness_started)
                if remaining <= 0:
                    jellyfin_duck_task.cancel()
                    try:
                        await jellyfin_duck_task
                    except asyncio.CancelledError:
                        pass
                    raise TimeoutError
                state["jellyfin_session_ids"] = await asyncio.wait_for(
                    jellyfin_duck_task,
                    timeout=remaining,
                )
        except TimeoutError:
            logger.debug(
                "Jellyfin ducking exceeded %.1fs readiness deadline; continuing without it.",
                _SPOTIFY_DUCK_DEADLINE_SECONDS,
            )
        except Exception as exc:
            logger.debug(f"Jellyfin ducking skipped: {exc}")

        if browser_duck_task is not None:
            try:
                if browser_duck_task.done():
                    state["browser_media"] = browser_duck_task.result()
                else:
                    remaining = _SPOTIFY_DUCK_DEADLINE_SECONDS - (loop.time() - readiness_started)
                    if remaining <= 0:
                        browser_duck_task.cancel()
                        try:
                            await browser_duck_task
                        except asyncio.CancelledError:
                            pass
                        raise TimeoutError
                    state["browser_media"] = await asyncio.wait_for(
                        browser_duck_task,
                        timeout=remaining,
                    )
            except TimeoutError:
                logger.debug(
                    "Browser media ducking exceeded %.1fs readiness deadline; continuing without it.",
                    _SPOTIFY_DUCK_DEADLINE_SECONDS,
                )
            except Exception as exc:
                logger.debug(f"Browser media ducking skipped: {exc}")

        return state

    async def _duck_spotify_for_listening(self) -> Tuple[bool, Optional[str]]:
        """Pause active Spotify playback and return state needed for restoration."""
        if not self.spotify_client.is_enabled():
            return False, None

        if not self.spotify_client.has_fresh_token():
            self.spotify_client.refresh_token_in_background()
            logger.debug("Spotify token refresh started in background; skipping Spotify duck for this listen.")
            return False, None

        playback = await self.spotify_client.get_current_playback()
        if not playback or not playback.get("is_playing"):
            return False, None

        device = playback.get("device") or {}
        device_id = device.get("id")
        await self.spotify_client.pause(device_id=device_id)
        logger.info("Paused Spotify for STT listening window.")
        return True, device_id

    async def _duck_jellyfin_for_listening(self) -> list[str]:
        """Pause currently playing Jellyfin sessions and retain their exact IDs."""
        jellyfin_client = getattr(self, "jellyfin_client", None)
        if jellyfin_client is None or not jellyfin_client.is_enabled():
            return []
        paused_ids = await jellyfin_client.pause_playing_sessions()
        if paused_ids:
            logger.info("Paused %d Jellyfin session(s) for STT listening window.", len(paused_ids))
        return paused_ids

    async def restore_after_listening(self, state: Optional[dict]) -> None:
        """Restore media playback after STT completes."""
        if not state:
            return

        try:
            get_audio_session_ducker().restore_after_listening(
                state.get("muted_app_sessions") or {}
            )
        except Exception as exc:
            logger.debug(f"App-session restore skipped: {exc}")

        try:
            browser_controller = getattr(self, "browser_controller", None)
            if browser_controller is not None:
                await browser_controller.restore_after_listening(
                    state.get("browser_media") or {}
                )
        except Exception as exc:
            logger.debug(f"Browser media restore skipped: {exc}")

        try:
            jellyfin_session_ids = state.get("jellyfin_session_ids") or []
            jellyfin_client = getattr(self, "jellyfin_client", None)
            if jellyfin_session_ids and jellyfin_client is not None:
                await jellyfin_client.resume_sessions(jellyfin_session_ids)
                logger.info(
                    "Resumed %d Jellyfin session(s) after STT listening window.",
                    len(jellyfin_session_ids),
                )
        except Exception as exc:
            logger.debug(f"Jellyfin restore skipped: {exc}")

        try:
            if state.get("spotify_was_playing"):
                await self.spotify_client.play(device_id=state.get("spotify_device_id"))
                logger.info("Resumed Spotify after STT listening window.")
        except Exception as exc:
            logger.debug(f"Spotify restore skipped: {exc}")

    async def _handle_jellyfin(self, action: str) -> Tuple[bool, dict]:
        """Pause or resume active Jellyfin sessions through the server API."""
        if not self.jellyfin_client.is_enabled():
            return False, {
                "type": "jellyfin",
                "message": "Jellyfin integration is not configured.",
            }

        try:
            if action == "pause":
                session_ids = await self.jellyfin_client.pause_playing_sessions()
                if not session_ids:
                    return False, {
                        "type": "jellyfin",
                        "message": "No active Jellyfin playback session could be paused.",
                    }
                return True, {"type": "jellyfin", "message": "Jellyfin playback paused."}

            if action in {"play", "resume"}:
                session_ids = await self.jellyfin_client.get_paused_session_ids()
                resumed_ids = await self.jellyfin_client.resume_sessions(session_ids)
                if not resumed_ids:
                    return False, {
                        "type": "jellyfin",
                        "message": "No paused Jellyfin playback session could be resumed.",
                    }
                return True, {"type": "jellyfin", "message": "Jellyfin playback resumed."}

            return False, {
                "type": "jellyfin",
                "message": "Jellyfin supports play, resume, and pause commands.",
            }
        except JellyfinNotConfiguredError:
            return False, {
                "type": "jellyfin",
                "message": "Jellyfin integration is not configured.",
            }
        except JellyfinError as exc:
            return False, {
                "type": "jellyfin",
                "message": "I couldn't control Jellyfin playback.",
                "error_detail": str(exc),
            }

    async def _spotify_is_active(self) -> bool:
        if not self.spotify_client.is_enabled():
            return False
        import time
        now = time.time()
        if hasattr(self, "_cached_spotify_active") and (now - getattr(self, "_cached_spotify_active_time", 0)) < 5.0:
            return self._cached_spotify_active
        playback = await self.spotify_client.get_current_playback()
        active = bool(playback and playback.get("is_playing"))
        self._cached_spotify_active = active
        self._cached_spotify_active_time = now
        return active

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
            
            # For transfer action, we need to find the TARGET device, not the active one
            if action == "transfer":
                # Find device by name if specified
                if device_name:
                    from src.media.spotify_utils import find_best_device
                    device = find_best_device(devices, device_name)
                    if not device:
                        # Device not found in initial scan. 
                        # If user requested a specific device (like "PC"), we should try to launch it.
                        found_device, error = await self._ensure_spotify_device(device_name)
                        if found_device:
                            device = found_device
                            # Now try transfer again with the newly found device
                            await self.spotify_client.transfer_playback(device["id"], play=True)
                            return True, {"type": "spotify", "message": f"Spotify playback moved to {device['name']}."}
                        else:
                            return False, error or {"type": "spotify", "message": f"Could not find device matching '{device_name}'."}
                    
                    # Device was found, proceed with transfer
                    await self.spotify_client.transfer_playback(device["id"], play=True)
                    return True, {"type": "spotify", "message": f"Spotify playback moved to {device['name']}."}
                else:
                    return False, {"type": "spotify", "message": "No device name specified for transfer."}
            
            # For all OTHER actions, prefer PC/Computer devices (unless user specified device_name)
            from src.media.spotify_utils import find_best_device
            
            device = None
            
            # If no specific device_name requested, ALWAYS prefer Computer devices (PC)
            if not device_name:
                # Look for Computer-type devices only
                computer_devices = [d for d in devices if str(d.get("type", "")).lower() == "computer"]
                
                if computer_devices:
                    # Found a computer, use it (prefer active one)
                    device = next((d for d in computer_devices if d.get("is_active")), computer_devices[0])
                    logger.info(f"Using computer device: {device['name']}")
                else:
                    # No computer found - launch Spotify on PC and wait for Computer device specifically
                    logger.info("No computer device found - launching Spotify on PC")
                    device, error = await self._ensure_computer_device()
                    if not device:
                        return False, error or {"type": "spotify", "message": "Could not launch Spotify on PC."}
            else:
                # User specified a device, find it by name
                device = find_best_device(devices, device_name)
                if not device:
                    # Try to launch/find the requested device
                    device, error = await self._ensure_spotify_device(device_name)
                    if not device:
                        return False, error or {"type": "spotify", "message": f"Could not find device '{device_name}'."}
            
            device_id = device["id"] if device else None

            if action in ("play", "resume"):
                playback = await self.spotify_client.get_current_playback()
                current_device = (playback or {}).get("device") or {}
                current_device_id = current_device.get("id")
                is_already_playing = bool(
                    playback
                    and playback.get("is_playing")
                    and device
                    and current_device_id
                    and current_device_id == device.get("id")
                )

                if is_already_playing:
                    msg = "Spotify is already playing." if action == "play" else "Spotify playback is already running."
                    return True, {"type": "spotify", "message": msg}

                # If the target device is inactive, transfer_playback(play=True) already starts
                # playback, so calling play() again can trigger a 403 Restriction Violated.
                was_inactive = device and not device.get("is_active")
                device_id = await self._activate_device(device, play=True)
                if not was_inactive:
                    await self.spotify_client.play(device_id=device_id)
                msg = "Spotify playback resumed." if action == "resume" else "Starting Spotify playback."
                return True, {"type": "spotify", "message": msg}

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

            # Transfer action is now handled above, before we get the active device
            # This section should never be reached for transfer action

            if action == "play_liked_songs":
                # Spotify API often fails on "spotify:collection:tracks" for desktop devices, so we just play what is current
                device_id = await self._activate_device(device, play=True)
                await self.spotify_client.play(device_id=device_id)
                return True, {"type": "spotify", "message": "Resuming your music on Spotify."}

            logger.info(f"Checking action '{action}' for get_current_track")
            if action in ("get_current_track", "identify", "what_song"):
                logger.info(f"Action matched! Getting current playback...")
                playback = await self.spotify_client.get_current_playback()
                logger.info(f"Playback data: {playback is not None}")
                if not playback or not playback.get("item"):
                    return False, {"type": "spotify", "message": "No track is currently playing on Spotify."}
                
                track = playback["item"]
                track_name = track.get("name", "Unknown")
                artists = ", ".join(artist.get("name", "") for artist in track.get("artists", []))
                album = track.get("album", {}).get("name", "Unknown Album")
                
                message = f"Currently playing: '{track_name}' by {artists}"
                if album:
                    message += f" from the album '{album}'"
                
                logger.info(f"Returning track info: {message}")
                return True, {
                    "type": "spotify",
                    "message": message,
                    "track_info": {
                        "name": track_name,
                        "artists": artists,
                        "album": album,
                        "uri": track.get("uri"),
                    }
                }

            logger.error(f"Unsupported Spotify action: {action}")
            return False, {"type": "spotify", "message": "Unsupported Spotify action."}
        except SpotifyNotConfiguredError:
            return False, {"type": "spotify", "message": "Spotify credentials are not configured."}
        except SpotifyError as exc:
            error_text = str(exc)
            lowered = error_text.lower()

            if "restriction violated" in lowered:
                message = "Spotify wouldn't allow that playback command on the current device."
            elif "no matching track found" in lowered:
                message = "I couldn't find that track on Spotify."
            elif "no matching playlist found" in lowered:
                message = "I couldn't find that playlist on Spotify."
            elif "request failed: 404" in lowered:
                message = "I couldn't find an active Spotify player to control."
            elif "request failed: 403" in lowered:
                message = "Spotify refused that command on the current device."
            else:
                message = "I couldn't complete that on Spotify."

            return False, {
                "type": "spotify",
                "message": message,
                "error_detail": error_text,
            }

    async def _maybe_launch_spotify_desktop(self) -> bool:
        try:
            launched = await self.app_launcher.launch_app("spotify")
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
            if not device.get("is_active"):
                await self.spotify_client.transfer_playback(device["id"], play=play)
                await asyncio.sleep(0.5)
            return device["id"]

        logger.info("No active device found. Attempting to find or launch Spotify...")
        for attempt in range(1, 4):
            devices = await self.spotify_client.get_devices()
            if devices:
                target_device = devices[0]
                logger.info(f"Found device '{target_device['name']}' on attempt {attempt}.")
                await self.spotify_client.transfer_playback(target_device["id"], play=play)
                await asyncio.sleep(1.5)
                return target_device["id"]
            logger.info(f"No devices found on attempt {attempt}. Waiting...")
            if attempt == 1:
                try:
                    logger.info("Launching Spotify application...")
                    await self.app_launcher.launch_app("spotify")
                except Exception as e:
                    logger.warning(f"Failed to launch Spotify: {e}")
            await asyncio.sleep(1.5)
            
        logger.error("Failed to find any Spotify devices after 3 attempts.")
        return None

    async def _ensure_computer_device(self) -> Tuple[Optional[dict], Optional[dict]]:
        """
        Launch Spotify on PC if needed and wait for a Computer-type device to register.
        Returns (device, error_dict).
        """
        logger.info("Attempting to launch Spotify desktop to ensure a Computer device is available...")
        launched = await self._maybe_launch_spotify_desktop()
        if not launched:
            logger.warning("Failed to launch Spotify desktop application.")
            return None, {"type": "spotify", "message": "Could not launch Spotify on PC."}

        poll_count = len(_SPOTIFY_DESKTOP_POLL_DELAYS_SECONDS)
        elapsed = 0.0
        for attempt, delay in enumerate(_SPOTIFY_DESKTOP_POLL_DELAYS_SECONDS, start=1):
            await asyncio.sleep(delay)
            elapsed += delay
            devices = await self.spotify_client.get_devices()
            computer_devices = [d for d in devices if str(d.get("type", "")).lower() == "computer"]
            if computer_devices:
                device = next((d for d in computer_devices if d.get("is_active")), computer_devices[0])
                logger.info(
                    "Found computer device after %.1fs (attempt %d/%d): %s",
                    elapsed,
                    attempt,
                    poll_count,
                    device["name"],
                )
                return device, None
            logger.info(
                "Waiting for Spotify PC device to register "
                "(%.1fs elapsed, attempt %d/%d)...",
                elapsed,
                attempt,
                poll_count,
            )

        return None, {
            "type": "spotify",
            "message": "Spotify launched on PC, but did not become ready within 30 seconds.",
        }

    async def _ensure_spotify_device(self, device_name: str) -> Tuple[Optional[dict], Optional[dict]]:
        """
        Ensure a specific requested device is found or launched if it is a PC/desktop device.
        Returns (device, error_dict).
        """
        target_lower = device_name.lower()
        is_pc_request = any(kw in target_lower for kw in ("pc", "desktop", "computer", "laptop"))

        if is_pc_request:
            logger.info(f"Requested device '{device_name}' appears to be a PC/computer. Launching Spotify desktop...")
            await self._maybe_launch_spotify_desktop()

        poll_delays = (
            _SPOTIFY_DESKTOP_POLL_DELAYS_SECONDS
            if is_pc_request
            else (1.5,)
        )
        for attempt, delay in enumerate(poll_delays, start=1):
            await asyncio.sleep(delay)
            devices = await self.spotify_client.get_devices()
            device = find_best_device(devices, device_name)
            if device:
                logger.info(f"Found device '{device['name']}' matching '{device_name}' on attempt {attempt}.")
                return device, None
            if not is_pc_request:
                break

        return None, {"type": "spotify", "message": f"Could not find Spotify device matching '{device_name}'."}

    async def _play_track_by_query(self, query: str, device_id: Optional[str]) -> None:
        """Search and play a track on Spotify."""
        results = await self.spotify_client.search(query, types=["track"], limit=1)
        tracks = results.get("tracks", {}).get("items", [])
        if not tracks:
            raise SpotifyError("No matching track found.")
        await self.spotify_client.play(uris=[tracks[0]["uri"]], device_id=device_id)

    async def _play_playlist_by_query(self, query: str, device_id: Optional[str]) -> None:
        """Search and play a playlist on Spotify."""
        results = await self.spotify_client.search(query, types=["playlist"], limit=1)
        playlists = results.get("playlists", {}).get("items", [])
        if not playlists:
            raise SpotifyError("No matching playlist found.")
        await self.spotify_client.play(context_uri=playlists[0]["uri"], device_id=device_id)


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
