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
    if target == "youtube":
        if " - youtube" in lower or lower.endswith("youtube"):
            score += 4
    if "youtube" in lower:
        score += 2
    if "music" in lower:
        score += 1
    return score


class BrowserMediaController:
    """Controls media playback for YouTube / YouTube Music in Chromium browsers."""

    def __init__(self):
        self._loop = asyncio.get_event_loop()

    async def control(self, action: str, target: Optional[str] = None, query: Optional[str] = None) -> Tuple[bool, dict]:
        """Execute a media action (play/pause/etc.) for the target browser tab."""
        return await asyncio.to_thread(self._control_sync, action.lower(), target, query)

    def _control_sync(self, action: str, target: Optional[str], query: Optional[str] = None) -> Tuple[bool, dict]:
        if not WIN32_AVAILABLE:
            return False, {"type": "browser_media", "message": "Browser media control is only available on Windows."}
        if not psutil:
            return False, {"type": "browser_media", "message": "psutil is required for browser media control."}

        if action == "play_track" and query:
            target_url = TARGET_URLS.get(target or "youtube", TARGET_URLS["youtube"])
            
            # Try direct playback with ytmusicapi for YouTube Music
            if "music.youtube.com" in target_url and YTMUSIC_AVAILABLE:
                try:
                    yt = YTMusic()
                    results = yt.search(query, filter='songs')
                    if results:
                        video_id = results[0]['videoId']
                        # Open directly in watch mode which usually auto-plays
                        watch_url = f"https://music.youtube.com/watch?v={video_id}"
                        webbrowser.open(watch_url, new=2)
                        return True, {
                            "type": "browser_media", 
                            "message": f"Playing '{query}' on YouTube Music."
                        }
                except Exception as e:
                    logger.error(f"ytmusicapi search failed: {e}")
                    # Fallback to standard search below
            
            # Fallback to search results
            if "music.youtube.com" in target_url:
                search_url = f"https://music.youtube.com/search?q={urllib.parse.quote(query)}"
            else:
                search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
            
            webbrowser.open(search_url, new=2)
            return True, {
                "type": "browser_media", 
                "message": f"Opened search for '{query}' on {(target or 'YouTube').replace('_', ' ')}."
            }

        if action == "play_playlist" and query:
            target_url = TARGET_URLS.get(target or "youtube", TARGET_URLS["youtube"])
            
            # Try direct playback with ytmusicapi for YouTube Music
            if "music.youtube.com" in target_url and YTMUSIC_AVAILABLE:
                try:
                    yt = YTMusic()
                    results = yt.search(query, filter='playlists')
                    if results:
                        playlist_id = results[0]['browseId']
                        # Playlist URL
                        watch_url = f"https://music.youtube.com/playlist?list={playlist_id}"
                        webbrowser.open(watch_url, new=2)
                        return True, {
                            "type": "browser_media", 
                            "message": f"Playing playlist '{query}' on YouTube Music."
                        }
                except Exception as e:
                    logger.error(f"ytmusicapi playlist search failed: {e}")
            
            # Fallback to search results
            if "music.youtube.com" in target_url:
                search_url = f"https://music.youtube.com/search?q={urllib.parse.quote(query)}"
            else:
                search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
            
            webbrowser.open(search_url, new=2)
            return True, {
                "type": "browser_media", 
                "message": f"Opened search for playlist '{query}' on {(target or 'YouTube').replace('_', ' ')}."
            }

        if action not in ACTION_KEYMAP:
            logger.error(f"Unsupported browser media action: {action}")
            return False, {"type": "browser_media", "message": "Unsupported browser media action."}

        window = self._find_window(target)
        if not window and target:
            logger.warning(f"No {target} window found")
            self._maybe_open_target(target)
            window = self._wait_for_window(target, timeout=8)
            if not window:
                return False, {
                    "type": "browser_media",
                    "message": f"No {target.replace('_', ' ')} tab found. Opening {target.replace('_', ' ')} in your browser—please try again once it loads.",
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

        key, modifiers = ACTION_KEYMAP[action]
        self._send_keystroke(key, modifiers)
        action_desc = action.replace("_", " ")
        target_desc = (target or "YouTube").replace("_", " ")
        return True, {
            "type": "browser_media",
            "message": f"{action_desc.title()} command sent to {target_desc.title()} tab.",
        }

    def _find_window(self, target: Optional[str]) -> Optional[BrowserWindow]:
        windows = self._enumerate_browser_windows()
        if target:
            candidates = self._score_windows(windows, target)
            if candidates:
                return candidates[0][1]
        # No explicit target or no match - fallback preference: YouTube Music -> YouTube
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

            results.append(BrowserWindow(handle=hwnd, title=title, process_name=name))
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
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
            time.sleep(0.1)
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
