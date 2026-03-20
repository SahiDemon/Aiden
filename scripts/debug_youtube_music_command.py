"""
Quick diagnostic for YouTube Music browser command delivery on Windows.

Usage:
  python scripts/debug_youtube_music_command.py --probe
  python scripts/debug_youtube_music_command.py --method appcommand
  python scripts/debug_youtube_music_command.py --method k
  python scripts/debug_youtube_music_command.py --method space
  python scripts/debug_youtube_music_command.py --method space_k

Run this while a YouTube Music tab is visible (title should include "YouTube Music").
"""
from __future__ import annotations

import argparse
import time
from typing import List

from src.media.browser_media_controller import BrowserMediaController, score_window_title


def _print_candidates(controller: BrowserMediaController) -> None:
    windows = controller._enumerate_browser_windows()
    if not windows:
        print("No Chromium browser windows detected.")
        return

    print("Detected browser windows:")
    for window in windows:
        yt_music = score_window_title(window.title, "youtube_music")
        yt = score_window_title(window.title, "youtube")
        print(f"  hwnd={window.handle} | score_music={yt_music} | score_youtube={yt} | title={window.title}")


def _run_method(controller: BrowserMediaController, method: str) -> bool:
    window = controller._find_window("youtube_music")
    if not window:
        print("No YouTube Music window found. Open music.youtube.com first.")
        return False

    print(f"Using window hwnd={window.handle}: {window.title}")
    if not controller._activate_window(window.handle):
        print("Failed to activate YouTube Music window.")
        return False

    time.sleep(0.5)
    if method == "appcommand":
        ok = controller._send_appcommand(window.handle, "play_pause")
        print(f"Sent WM_APPCOMMAND play_pause: {ok}")
        return ok
    if method == "k":
        controller._send_keystroke("K", [])
        print("Sent keystroke: K")
        return True
    if method == "space":
        controller._send_keystroke("SPACE", [])
        print("Sent keystroke: SPACE")
        return True
    if method == "space_k":
        controller._send_keystroke("SPACE", [])
        time.sleep(0.2)
        controller._send_keystroke("K", [])
        print("Sent keystroke sequence: SPACE then K")
        return True

    raise ValueError(f"Unknown method: {method}")


def _probe_all(controller: BrowserMediaController, delay: float) -> None:
    methods: List[str] = ["appcommand", "k", "space", "space_k"]
    for method in methods:
        print(f"\n--- Testing method: {method} ---")
        _run_method(controller, method)
        print(f"Observe YouTube Music now. Waiting {delay:.1f}s before next method...")
        time.sleep(delay)


def main() -> int:
    parser = argparse.ArgumentParser(description="Debug YouTube Music media command delivery.")
    parser.add_argument("--method", choices=["appcommand", "k", "space", "space_k"], default="appcommand")
    parser.add_argument("--probe", action="store_true", help="Run all methods in sequence for comparison.")
    parser.add_argument("--delay", type=float, default=3.0, help="Delay between probe methods in seconds.")
    parser.add_argument("--list", action="store_true", help="Only list detected browser windows and scores.")
    args = parser.parse_args()

    controller = BrowserMediaController()

    _print_candidates(controller)
    if args.list:
        return 0

    if args.probe:
        _probe_all(controller, args.delay)
        return 0

    _run_method(controller, args.method)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
