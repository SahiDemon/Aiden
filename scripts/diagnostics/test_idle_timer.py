"""Watch Aiden's real idle and media checks, then lock after 60 eligible seconds.

This standalone diagnostic does not change saved auto-shutdown settings or
call the shutdown command.
"""

import ctypes
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.check_media_status import check_jellyfin, inspect_audio_devices
from src.utils.media_idle_monitor import MediaIdleMonitor


THRESHOLD_SECONDS = 60.0
TEST_SECONDS = 75


def print_media_blockers() -> None:
    jellyfin_playing, jellyfin_details = check_jellyfin()
    audio_playing, _, audio_triggers = inspect_audio_devices()
    if jellyfin_playing or audio_playing:
        print("Media blockers:", flush=True)
        if jellyfin_playing:
            for detail in jellyfin_details:
                if detail.startswith("Jellyfin Active:"):
                    print(f"  {detail}", flush=True)
        for detail in audio_triggers:
            print(f"  {detail}", flush=True)
    else:
        print("No media blockers detected.", flush=True)


def run_test() -> None:
    monitor = MediaIdleMonitor()
    print("=" * 72)
    print("AIDEN IDLE + MEDIA DIAGNOSTIC: LOCK TEST AT 60 SECONDS")
    print("Leave the mouse and keyboard untouched. The saved 40-minute shutdown")
    print("setting stays as it is. This test can only lock the PC, never shut it down.")
    print("=" * 72, flush=True)
    print_media_blockers()

    previous_idle = monitor.get_idle_time_seconds()
    max_idle = previous_idle
    ever_media_blocked = False
    for elapsed in range(1, TEST_SECONDS + 1):
        time.sleep(1)
        idle = monitor.get_idle_time_seconds()
        media_playing = monitor.is_media_playing()
        max_idle = max(max_idle, idle)
        ever_media_blocked |= media_playing

        if idle < previous_idle - 1.5:
            print(f"RESET: Windows idle time fell from {previous_idle:.1f}s to {idle:.1f}s.", flush=True)

        reason = "media detected" if media_playing else "eligible"
        print(f"[{elapsed:02d}s] Windows idle: {idle:5.1f}s | Aiden: {reason}", flush=True)

        if idle >= THRESHOLD_SECONDS and not media_playing:
            print("60-second idle condition met and no media detected. Locking now.", flush=True)
            if not ctypes.windll.user32.LockWorkStation():
                raise OSError("Windows LockWorkStation failed")
            return
        previous_idle = idle

    print(f"Test ended. Highest idle time: {max_idle:.1f}s.", flush=True)
    if ever_media_blocked:
        print_media_blockers()
    if max_idle < THRESHOLD_SECONDS:
        print("Windows idle time never reached 60 seconds. An input reset prevented the lock.", flush=True)
    elif ever_media_blocked:
        print("Aiden detected media at the threshold, which prevented the lock.", flush=True)


if __name__ == "__main__":
    run_test()
