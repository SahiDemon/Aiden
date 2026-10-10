"""
Browser media controller
Controls YouTube / YouTube Music tabs in Chromium browsers via window discovery.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple
import webbrowser
import urllib.parse
import re
import requests
try:
    from ytmusicapi import YTMusic
    YTMUSIC_AVAILABLE = True
except ImportError:
    YTMUSIC_AVAILABLE = False

try:
    import psutil
except ImportError:  # pragma: no cover - tests without psutil
    psutil = None

try:
    import win32con
    import win32gui
    import win32process
    import win32api

    WIN32_AVAILABLE = True
except ImportError:  # pragma: no cover - non-Windows environments
    WIN32_AVAILABLE = False

try:
    import comtypes
    from comtypes import COMMETHOD, GUID, HRESULT, IUnknown, POINTER
    from ctypes import c_float, c_int

    COMTYPES_AVAILABLE = True
except ImportError:  # pragma: no cover - optional runtime dependency
    COMTYPES_AVAILABLE = False

from src.utils.logger import get_logger

logger = get_logger(__name__)

BROWSER_PROCESS_NAMES = {
    "chrome.exe",
    "msedge.exe",
    "brave.exe",
    "vivaldi.exe",
    "chrome",
    "msedge",
    "brave",
    "vivaldi",
}

TARGET_KEYWORDS = {
    "youtube_music": ["youtube music"],
    "youtube": ["youtube"],
}

TARGET_URLS = {
    "youtube_music": "https://music.youtube.com/",
    "youtube": "https://www.youtube.com/",
}

ACTION_KEYMAP = {
    "play_pause": ("K", []),
    "pause": ("K", []),
    "resume": ("K", []),
    "next": ("N", ["SHIFT"]),
    "previous": ("P", ["SHIFT"]),
    "seek_forward": ("L", []),
    "seek_backward": ("J", []),
    "mute": ("M", []),
    "unmute": ("M", []),  # toggle
}

if WIN32_AVAILABLE:
    KEY_VK = {
        "SPACE": win32con.VK_SPACE,
        "K": ord("K"),
        "J": ord("J"),
        "L": ord("L"),
        "M": ord("M"),
        "N": ord("N"),
        "P": ord("P"),
        "SHIFT": win32con.VK_SHIFT,
    }
else:  # pragma: no cover - not expected on Windows
    KEY_VK = {}


@dataclass
class BrowserWindow:
    handle: int
    title: str
    process_name: str
    process_id: int


if COMTYPES_AVAILABLE:
    class IMMDevice(IUnknown):
        _iid_ = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Activate",
                      (["in"], POINTER(GUID), "iid"),
                      (["in"], c_int, "dwClsCtx"),
                      (["in"], POINTER(IUnknown), "pActivationParams"),
                      (["out", "retval"], POINTER(POINTER(IUnknown)), "ppInterface")),
        ]


    class IMMDeviceEnumerator(IUnknown):
        _iid_ = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
        _methods_ = [
            COMMETHOD([], HRESULT, "EnumAudioEndpoints"),
            COMMETHOD([], HRESULT, "GetDefaultAudioEndpoint",
                      (["in"], c_int, "dataFlow"),
                      (["in"], c_int, "role"),
                      (["out", "retval"], POINTER(POINTER(IMMDevice)), "ppEndpoint")),
        ]


    class IAudioMeterInformation(IUnknown):
        _iid_ = GUID("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetPeakValue",
                      (["out", "retval"], POINTER(c_float), "pfPeak")),
        ]


    class IAudioSessionControl(IUnknown):
        _iid_ = GUID("{F4B1A599-7266-4319-A8CA-E70ACB11E8CD}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetState",
                      (["out", "retval"], POINTER(c_int), "pRetVal")),
        ]


    class IAudioSessionControl2(IAudioSessionControl):
        _iid_ = GUID("{BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D}")
        _methods_ = IAudioSessionControl._methods_ + [
            COMMETHOD([], HRESULT, "GetDisplayName"),
            COMMETHOD([], HRESULT, "SetDisplayName"),
            COMMETHOD([], HRESULT, "GetIconPath"),
            COMMETHOD([], HRESULT, "SetIconPath"),
            COMMETHOD([], HRESULT, "GetGroupingParam"),
            COMMETHOD([], HRESULT, "SetGroupingParam"),
            COMMETHOD([], HRESULT, "RegisterAudioSessionNotification"),
            COMMETHOD([], HRESULT, "UnregisterAudioSessionNotification"),
            COMMETHOD([], HRESULT, "GetSessionIdentifier"),
            COMMETHOD([], HRESULT, "GetSessionInstanceIdentifier"),
            COMMETHOD([], HRESULT, "GetProcessId",
                      (["out", "retval"], POINTER(c_int), "pRetVal")),
            COMMETHOD([], HRESULT, "IsSystemSoundsSession"),
            COMMETHOD([], HRESULT, "SetDuckingPreference"),
        ]


    class IAudioSessionEnumerator(IUnknown):
        _iid_ = GUID("{E2F5BB11-0570-40CA-ACDD-3AA01277DEE8}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetCount",
                      (["out", "retval"], POINTER(c_int), "SessionCount")),
            COMMETHOD([], HRESULT, "GetSession",
                      (["in"], c_int, "SessionCount"),
                      (["out", "retval"], POINTER(POINTER(IAudioSessionControl)), "Session")),
        ]


    class IAudioSessionManager2(IUnknown):
        _iid_ = GUID("{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetAudioSessionControl"),
            COMMETHOD([], HRESULT, "GetSimpleAudioVolume"),
            COMMETHOD([], HRESULT, "GetSessionEnumerator",
                      (["out", "retval"], POINTER(POINTER(IAudioSessionEnumerator)), "SessionEnum")),
            COMMETHOD([], HRESULT, "RegisterSessionNotification"),
            COMMETHOD([], HRESULT, "UnregisterSessionNotification"),
            COMMETHOD([], HRESULT, "RegisterDuckNotification"),
            COMMETHOD([], HRESULT, "UnregisterDuckNotification"),
        ]


    CLSID_MMDeviceEnumerator = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
    E_RENDER = 0
    E_MULTIMEDIA = 1
    AUDIO_SESSION_STATE_ACTIVE = 1
    AUDIO_ACTIVITY_THRESHOLD = 0.0005


def score_window_title(title: str, target: Optional[str]) -> int:
    """Score a window title for how well it matches the requested target."""
    if not title:
        return 0
    lower = title.lower()
    score = 0
    if "incognito" in lower:
        score -= 1
        
    if target == "youtube_music":
        if "youtube music" in lower:
            score += 5
        else:
            return 0  # Do not match regular YouTube when YouTube Music is explicitly requested
            
    elif target == "youtube":
        if "youtube music" in lower:
            return 0
        if " - youtube" in lower or lower.endswith("youtube"):
            score += 4
            
    if "youtube" in lower and target != "youtube_music":
        score += 2
    if "music" in lower and target != "youtube_music":
        score += 1
    return score


class _SearchSession(requests.Session):
    """Bound public search requests so a failed provider cannot hang a command."""

    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", (3, 8))
        return super().request(method, url, **kwargs)


class BrowserMediaController:
    """Controls media playback for YouTube / YouTube Music in Chromium browsers."""

    def __init__(self):
        pass

    async def control(self, action: str, target: Optional[str] = None, query: Optional[str] = None) -> Tuple[bool, dict]:
        """Execute a media action (play/pause/etc.) for the target browser tab."""
        return await asyncio.to_thread(self._control_sync, action.lower(), target, query)

    async def duck_for_listening(self) -> dict:
        """Best-effort pause of active browser media while STT is listening."""
        return await asyncio.to_thread(self._duck_for_listening_sync)

    async def restore_after_listening(self, state: Optional[dict]) -> None:
        """Resume browser media that we paused for STT."""
        await asyncio.to_thread(self._restore_after_listening_sync, state or {})

    def _control_sync(self, action: str, target: Optional[str], query: Optional[str] = None) -> Tuple[bool, dict]:
        if not WIN32_AVAILABLE:
            return False, {"type": "browser_media", "message": "Browser media control is only available on Windows."}
        if not psutil:
            return False, {"type": "browser_media", "message": "psutil is required for browser media control."}

        if query and action in {"play", "resume", "play_pause", "play_track", "play_playlist"}:
            return self._open_search_selection(target or "youtube", query, action == "play_playlist")
        if action in {"play_track", "play_playlist"}:
            return False, {"type": "browser_media", "message": "What song or playlist should I play?"}

        if action not in ACTION_KEYMAP:
            logger.error(f"Unsupported browser media action: {action}")
            return False, {"type": "browser_media", "message": "Unsupported browser media action."}

        window = self._find_window(target)
        if not window and target:
            logger.warning(f"No {target} window found")
            self._maybe_open_target(target)
            return True, {
                "type": "browser_media",
                "playback_confirmed": False,
                "message": f"Opened {target.replace('_', ' ')}. Choose something to play, or tell me a song or mood to search for.",
            }
        if not window:
            logger.warning("No YouTube/YouTube Music window detected")
            return False, {"type": "browser_media", "message": "No YouTube tab found to control."}

        if not self._activate_window(window.handle):
            self._maybe_open_target(target or "youtube")
            window = self._wait_for_window(target or "youtube", timeout=8)
            if not window or not self._activate_window(window.handle):
                return False, {
                    "type": "browser_media",
                    "message": "I couldn't bring the YouTube tab to the front. I opened a new tab—please bring it forward and try again.",
                }

        # YouTube Music is most reliable with SPACE on this setup.
        if target == "youtube_music" and action in {"play_pause", "resume", "pause"}:
            self._send_keystroke("SPACE", [])
            action_desc = action.replace("_", " ")
            return True, {
                "type": "browser_media",
                "message": f"{action_desc.title()} command sent to Youtube Music tab.",
            }

        key, modifiers = ACTION_KEYMAP[action]
        self._send_keystroke(key, modifiers)
        action_desc = action.replace("_", " ")
        target_desc = (target or "YouTube").replace("_", " ")
        return True, {
            "type": "browser_media",
            "message": f"{action_desc.title()} command sent to {target_desc.title()} tab.",
        }

    def _open_search_selection(self, target: str, query: str, playlist: bool = False) -> Tuple[bool, dict]:
        """Resolve a public result and open its player; never toggle autoplay blindly."""
        provider = "YouTube Music" if target == "youtube_music" else "YouTube"
        base = TARGET_URLS.get(target, TARGET_URLS["youtube"]).rstrip("/")
        query = query.strip()
        url, title, direct = None, query, False
        if YTMUSIC_AVAILABLE:
            try:
                with _SearchSession() as session:
                    yt = YTMusic(requests_session=session)
                    category = "playlists" if playlist else "songs" if target == "youtube_music" else "videos"
                    results = yt.search(query, filter=category, limit=5)
                    for result in results:
                        video_id = result.get("videoId")
                        list_id = str(result.get("browseId") or "").removeprefix("VL") if playlist else None
                        if playlist and list_id and re.fullmatch(r"[A-Za-z0-9_-]+", list_id):
                            tracks = yt.get_playlist(list_id, limit=1).get("tracks", [])
                            video_id = next((track.get("videoId") for track in tracks if track.get("videoId")), None)
                        if video_id and re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
                            params = {"v": video_id, "autoplay": "1"}
                            if list_id:
                                params["list"] = list_id
                            url = f"{base}/watch?{urllib.parse.urlencode(params)}"
                            title = result.get("title") or query
                            direct = True
                            break
            except Exception as exc:
                logger.warning("YouTube search resolution failed: %s", exc)
        if not url:
            path, param = ("search", "q") if target == "youtube_music" else ("results", "search_query")
            url = f"{base}/{path}?{urllib.parse.urlencode({param: query})}"
        try:
            if not webbrowser.open(url, new=2):
                return False, {"type": "browser_media", "message": f"I couldn't open {provider} in your browser."}
        except Exception as exc:
            logger.warning("Could not open browser player: %s", exc)
            return False, {"type": "browser_media", "message": f"I couldn't open {provider} in your browser."}
        message = (
            f"Opened '{title}' on {provider} with autoplay requested. If it doesn't start, press Play in the tab."
            if direct else f"Opened search results for '{query}' on {provider}. Select a result to start playback."
        )
        return True, {"type": "browser_media", "message": message, "url": url,
                      "playback_confirmed": False, "autoplay_requested": direct}

    def _duck_for_listening_sync(self) -> dict:
        if not WIN32_AVAILABLE or not psutil:
            return {"toggled_handles": []}

        toggled_handles: List[int] = []
        for window in self._get_duck_candidates():
            if self._send_appcommand(window.handle, "play_pause"):
                logger.info(f"Paused browser media for STT: {window.title}")
                toggled_handles.append(window.handle)

        return {"toggled_handles": toggled_handles}

    def _restore_after_listening_sync(self, state: dict) -> None:
        if not WIN32_AVAILABLE:
            return

        for handle in state.get("toggled_handles", []):
            try:
                if win32gui.IsWindow(handle):
                    if self._send_appcommand(handle, "play_pause"):
                        logger.info(f"Restored browser media after STT for window {handle}")
            except Exception as exc:
                logger.debug(f"Skipping browser media restore for window {handle}: {exc}")

    def _get_duck_candidates(self) -> List[BrowserWindow]:
        """Choose the most likely active browser media windows to pause/resume."""
        windows = self._enumerate_browser_windows()
        active_audio_pids = self._get_active_browser_audio_pids()
        if not active_audio_pids:
            logger.debug("No active browser audio sessions detected; skipping browser ducking.")
            return []

        windows = [window for window in windows if window.process_id in active_audio_pids]
        candidates: List[BrowserWindow] = []
        seen_handles: set[int] = set()

        for target in ("youtube_music", "youtube"):
            scored = self._score_windows(windows, target)
            if not scored:
                continue
            window = scored[0][1]
            if window.handle not in seen_handles:
                seen_handles.add(window.handle)
                candidates.append(window)

        return candidates

    def _get_active_browser_audio_pids(self) -> set[int]:
        """Return browser process IDs that are actively producing audible output."""
        if not COMTYPES_AVAILABLE or not psutil:
            logger.debug("Browser audio-session detection unavailable.")
            return set()

        active_pids: set[int] = set()

        try:
            from pycaw.pycaw import AudioUtilities
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                try:
                    process = session.Process
                    if not process:
                        continue

                    pid = int(process.pid)
                    if not pid:
                        continue

                    try:
                        process_name = process.name().lower()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                    if process_name not in BROWSER_PROCESS_NAMES:
                        continue

                    peak = 0.0
                    try:
                        meter = session._ctl.QueryInterface(IAudioMeterInformation)
                        peak = float(meter.GetPeakValue())
                    except Exception:
                        peak = 0.0

                    if peak > AUDIO_ACTIVITY_THRESHOLD:
                        active_pids.add(pid)
                except Exception as exc:
                    logger.debug(f"Skipping browser audio session during inspection: {exc}")
        except Exception as exc:
            logger.debug(f"Browser audio session inspection failed: {exc}")

        return active_pids

    def _find_window(self, target: Optional[str]) -> Optional[BrowserWindow]:
        windows = self._enumerate_browser_windows()
        if target:
            candidates = self._score_windows(windows, target)
            if candidates:
                return candidates[0][1]
            return None  # Do not fallback if a target is explicitly provided.
        # No explicit target - fallback preference: YouTube Music -> YouTube
        for fallback in ("youtube_music", "youtube"):
            candidates = self._score_windows(windows, fallback)
            if candidates:
                return candidates[0][1]
        return None

    def _score_windows(self, windows: List[BrowserWindow], target: str) -> List[Tuple[int, BrowserWindow]]:
        scored = []
        for window in windows:
            score = score_window_title(window.title, target)
            if score > 0:
                scored.append((score, window))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored

    def _enumerate_browser_windows(self) -> List[BrowserWindow]:
        if not WIN32_AVAILABLE or not psutil:
            return []
        results: List[BrowserWindow] = []

        def callback(hwnd, extra):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            length = win32gui.GetWindowTextLength(hwnd)
            if length == 0:
                return True
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return True

            _, process_id = win32process.GetWindowThreadProcessId(hwnd)
            try:
                process = psutil.Process(process_id)
                name = process.name().lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return True

            if name not in BROWSER_PROCESS_NAMES:
                return True

            results.append(BrowserWindow(handle=hwnd, title=title, process_name=name, process_id=process_id))
            return True

        win32gui.EnumWindows(callback, None)
        return results

    def _wait_for_window(self, target: Optional[str], timeout: int = 6) -> Optional[BrowserWindow]:
        if not target:
            return None
        end_time = time.time() + timeout
        while time.time() < end_time:
            window = self._find_window(target)
            if window:
                return window
            time.sleep(0.5)
        return None

    def _activate_window(self, hwnd: int) -> bool:
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        except Exception:
            pass

        for attempt in range(2):
            try:
                win32gui.SetForegroundWindow(hwnd)
                win32gui.BringWindowToTop(hwnd)
                time.sleep(0.1)
                return True
            except Exception:
                if attempt == 0:
                    # ALT keypress is a known workaround for foreground-lock restrictions.
                    try:
                        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
                        time.sleep(0.02)
                        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
                        time.sleep(0.05)
                    except Exception:
                        pass

        try:
            win32gui.SetActiveWindow(hwnd)
            time.sleep(0.05)
            return True
        except Exception as e:
            logger.error(f"Failed to activate window {hwnd}: {e}")
            return False

    def _send_keystroke(self, key: str, modifiers: List[str]) -> None:
        vk = KEY_VK.get(key.upper())
        if not vk:
            logger.error(f"Unknown virtual key for '{key}'")
            return

        for mod in modifiers:
            vk_mod = KEY_VK.get(mod.upper())
            if vk_mod:
                win32api.keybd_event(vk_mod, 0, 0, 0)
                time.sleep(0.01)

        win32api.keybd_event(vk, 0, 0, 0)
        time.sleep(0.05)
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)

        for mod in reversed(modifiers):
            vk_mod = KEY_VK.get(mod.upper())
            if vk_mod:
                time.sleep(0.01)
                win32api.keybd_event(vk_mod, 0, win32con.KEYEVENTF_KEYUP, 0)

    def _start_youtube_music_after_open(self, window: BrowserWindow) -> None:
        """Start playback on a newly opened YouTube Music tab with guarded retries."""
        if not self._activate_window(window.handle):
            return

        # Give initial page scripts/player controls time to initialize.
        time.sleep(2.8)

        # Re-activate before the first key to avoid focus drift after load.
        self._activate_window(window.handle)

        # Primary attempt.
        self._send_keystroke("SPACE", [])
        time.sleep(1.0)

        # If still on the generic page title, retry once.
        try:
            current_title = win32gui.GetWindowText(window.handle).lower()
        except Exception:
            current_title = window.title.lower()

        if " | youtube music" not in current_title:
            self._activate_window(window.handle)
            time.sleep(0.4)
            self._send_keystroke("SPACE", [])

        time.sleep(0.6)

    def _send_appcommand(self, hwnd: int, command: str) -> bool:
        if not WIN32_AVAILABLE:
            return False

        command_map = {
            "play_pause": 14,
            "next": 11,
            "previous": 12,
            "mute": 8,
        }
        app_cmd = command_map.get(command)
        if app_cmd is None:
            return False

        try:
            lparam = app_cmd << 16
            wm_appcommand = getattr(win32con, "WM_APPCOMMAND", 0x0319)
            win32gui.SendMessage(hwnd, wm_appcommand, hwnd, lparam)
            time.sleep(0.05)
            return True
        except Exception as exc:
            logger.warning(f"Failed WM_APPCOMMAND '{command}' for window {hwnd}: {exc}")
            return False

    def _maybe_open_target(self, target: Optional[str]) -> None:
        if not target:
            return
        url = TARGET_URLS.get(target)
        if not url:
            return
        try:
            webbrowser.open(url, new=2)
            logger.info(f"Opened browser URL for {target}: {url}")
        except Exception as exc:
            logger.error(f"Failed to open browser URL {url}: {exc}")


# Global instance -------------------------------------------------------------
_browser_media_controller: Optional[BrowserMediaController] = None


def get_browser_media_controller() -> BrowserMediaController:
    global _browser_media_controller
    if _browser_media_controller is None:
        _browser_media_controller = BrowserMediaController()
    return _browser_media_controller
