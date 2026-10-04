"""
Media router that prioritizes Spotify or browser-based media control.
"""
from __future__ import annotations

import asyncio
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Optional, Tuple

# from src.execution.app_launcher import get_app_launcher  <-- Moved to inside method to avoid circular import
from src.media.audio_session_ducker import get_audio_session_ducker
from src.media.browser_media_controller import get_browser_media_controller
from src.media.jellyfin_client import JellyfinClient, JellyfinError, get_jellyfin_client
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
_JELLYFIN_PLAYER_POLL_DELAYS_SECONDS = (1.0, 1.0, 2.0, 2.0, 3.0, 3.0)


def _normalized_jellyfin_title(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    normalized = " ".join(re.findall(r"[a-z0-9]+", ascii_text.casefold()))
    return re.sub(r"^(?:the|a|an) ", "", normalized)


def _select_jellyfin_title(query: str, candidates: list[dict], allowed_types: set[str]) -> Optional[dict]:
    """Prefer the named title; use a typo match only when it is unambiguous."""
    wanted = _normalized_jellyfin_title(query)
    eligible = [item for item in candidates if item.get("Id") and item.get("Type") in allowed_types]
    exact = [item for item in eligible if _normalized_jellyfin_title(item.get("Name", "")) == wanted]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None

    ranked = sorted(
        ((SequenceMatcher(None, wanted, _normalized_jellyfin_title(item.get("Name", ""))).ratio(), item)
         for item in eligible),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if not ranked or ranked[0][0] < 0.86:
        return None
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.08:
        return None
    return ranked[0][1]


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
        if target in {"youtube", "youtube_music"}:
            return await self.browser_controller.control(action_alias(action), target, query)
        if target == "spotify":
            return await self._handle_spotify(action, query, entity_type, volume, device_name)
        if target == "jellyfin":
            return await self._handle_jellyfin(action, query)
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
                state["jellyfin_session_ids"] = await asyncio.wait_for(jellyfin_duck_task, timeout=remaining)
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
        client = getattr(self, "jellyfin_client", None)
        if client is None or not client.is_enabled():
            return []
        return await client.pause_playing_sessions()

    @staticmethod
    def _find_jellyfin_player(sessions: list[dict]) -> Optional[dict]:
        return next(
            (session for session in sessions if session.get("Id") and session.get("SupportsRemoteControl", True)),
            None,
        )

    async def _ensure_jellyfin_player(self, sessions: list[dict]) -> tuple[Optional[dict], list[dict]]:
        """Launch the desktop player and wait for it to register with Jellyfin."""
        player = self._find_jellyfin_player(sessions)
        if player:
            return player, sessions

        try:
            launched = await self.app_launcher.launch_app("jellyfin")
        except Exception as exc:
            logger.debug("Could not launch Jellyfin Media Player: %s", exc)
            launched = False
        if not launched:
            return None, sessions

        for delay in _JELLYFIN_PLAYER_POLL_DELAYS_SECONDS:
            await asyncio.sleep(delay)
            try:
                sessions = await self.jellyfin_client.get_sessions()
            except JellyfinError:
                continue
            player = self._find_jellyfin_player(sessions)
            if player:
                logger.info("Jellyfin Media Player connected after launch.")
                return player, sessions
        return None, sessions

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
            session_ids = state.get("jellyfin_session_ids") or []
            if session_ids:
                await self.jellyfin_client.resume_sessions(session_ids)
            if state.get("jellyfin_session_ids"):
                logger.info("Resumed Jellyfin after voice interaction.")
        except Exception as exc:
            logger.debug(f"Jellyfin restore skipped: {exc}")

        try:
            if state.get("spotify_was_playing"):
                await self.spotify_client.play(device_id=state.get("spotify_device_id"))
                logger.info("Resumed Spotify after STT listening window.")
        except Exception as exc:
            logger.debug(f"Spotify restore skipped: {exc}")

    async def _handle_jellyfin(self, action: str, query: Optional[str] = None) -> Tuple[bool, dict]:
        if not self.jellyfin_client.is_enabled():
            return False, {"type": "jellyfin", "message": "Jellyfin isn't set up yet."}
        # The general command schema uses play_track for a titled media item.
        if action == "play_track":
            action = "play_title"
        if action not in {"pause", "play", "resume", "play_title", "play_movie", "play_series"}:
            return False, {"type": "jellyfin", "message": "I can play movies or shows, or pause and resume Jellyfin."}
        try:
            sessions = await self.jellyfin_client.get_sessions()
            if action in {"play_title", "play_movie", "play_series"}:
                if not query:
                    return False, {"type": "jellyfin", "message": "Tell me which title to play on Jellyfin."}
                allowed_types = {"Movie", "Series"} if action == "play_title" else {"Movie" if action == "play_movie" else "Series"}
                types = tuple(sorted(allowed_types))
                candidates = await self.jellyfin_client.search_titles(query, item_types=types)
                title = _select_jellyfin_title(query, candidates, allowed_types)
                if title is None or _normalized_jellyfin_title(title.get("Name", "")) != _normalized_jellyfin_title(query):
                    # SearchTerm can rank partial matches ahead of an exact
                    # library title, and sometimes returns duplicate series.
                    # Compare against the catalog before trusting a typo hit.
                    catalog = await self.jellyfin_client.list_titles(item_types=types)
                    title = _select_jellyfin_title(query, catalog, allowed_types)
                if title is None:
                    return False, {"type": "jellyfin", "message": f"I couldn't find {query} in Jellyfin."}

                item = title
                resume_ticks = 0
                resuming = False

                # A series needs a signed-in Jellyfin window to find its next
                # episode.  Previously this check happened first, which meant
                # a request could fail without even opening Jellyfin.
                player, sessions = await self._ensure_jellyfin_player(sessions)
                if not player:
                    return False, {"type": "jellyfin", "message": "Jellyfin isn't ready yet. Open it, then try again."}

                if title["Type"] == "Series":
                    viewer = player.get("UserId") or next(
                        (session.get("UserId") for session in sessions if session.get("UserId")),
                        None,
                    )
                    # Next Up is Jellyfin's own answer for "what should I
                    # watch next?"  A partially watched older episode is only
                    # a fallback, since it can otherwise override the user's
                    # current place in a series.
                    if viewer:
                        item = await self.jellyfin_client.get_next_up_episode(viewer, title["Id"])
                    if item is None or item is title:
                        resume_items = (
                            await self.jellyfin_client.get_resume_episodes(viewer, title["Id"])
                            if viewer else []
                        )
                        in_progress = [
                            episode for episode in resume_items
                            if episode.get("Id") and episode.get("SeriesId") == title["Id"]
                            and not (episode.get("UserData") or {}).get("Played")
                            and int((episode.get("UserData") or {}).get("PlaybackPositionTicks") or 0) > 0
                        ]
                        if in_progress:
                            item = max(in_progress, key=lambda episode: (episode.get("UserData") or {}).get("LastPlayedDate") or "")
                            resume_ticks = int((item.get("UserData") or {}).get("PlaybackPositionTicks") or 0)
                            resuming = True
                    if item is None or item is title:
                        item = await self.jellyfin_client.get_first_episode(viewer, title["Id"])
                    if item is None:
                        return False, {"type": "jellyfin", "message": f"I found {title['Name']}, but I couldn't find an episode to start."}
                if resuming:
                    await self.jellyfin_client.play_item(player["Id"], item["Id"], start_position_ticks=resume_ticks)
                else:
                    await self.jellyfin_client.play_item(player["Id"], item["Id"])

                if title["Type"] == "Series":
                    season = item.get("ParentIndexNumber")
                    number = item.get("IndexNumber")
                    episode_label = f"S{season} E{number}" if season is not None and number is not None else item.get("Name", "an episode")
                    verb = "Resuming" if resuming else "Playing"
                    return True, {"type": "jellyfin", "message": f"{verb} {title['Name']} {episode_label} on Jellyfin."}
                year = title.get("ProductionYear")
                label = f"{title['Name']} ({year})" if year else title["Name"]
                return True, {"type": "jellyfin", "message": f"Playing {label} on Jellyfin."}
            targets = [s for s in sessions if s.get("NowPlayingItem") and s.get("Id")]
            if not targets:
                return False, {"type": "jellyfin", "message": "I can't find anything playing in Jellyfin right now."}
            paused = action == "pause"
            for session in targets:
                if bool(session.get("PlayState", {}).get("IsPaused", False)) != paused:
                    await self.jellyfin_client.set_paused(session["Id"], paused=paused)
            message = "Jellyfin paused." if paused else "Jellyfin playback resumed."
            return True, {"type": "jellyfin", "message": message}
        except JellyfinError as exc:
            logger.warning("Jellyfin request failed: %s", exc)
            return False, {"type": "jellyfin", "message": "I couldn't reach Jellyfin just now. Please try again."}

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
