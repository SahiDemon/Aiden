"""
Aiden Guardian — process watchdog / auto-restart daemon

Run this script INSTEAD of src/main.py.  It will:
  1. Spawn Aiden (src/main.py) as a child process.
  2. Monitor the child; if it dies for any reason other than a clean
     intentional exit, restart it after a short back-off delay.
  3. Stop restarting when a sentinel file is present (written by the
     tray "Exit Aiden" action so the user's deliberate quit is honoured).
  4. Speak status messages through Aiden's voice (Edge TTS + pygame) so
     the user is always informed of crashes and restarts.

Usage (from project root, venv active):
    python src/utils/guardian.py [--debug] [extra args forwarded to main.py…]

The PowerShell launcher (run_aiden.ps1) calls this automatically.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import signal
import subprocess
import argparse
import logging
import tempfile
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Bootstrap: make sure we can find the project root even when called directly
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()
PROJECT_ROOT = _HERE.parent.parent.parent          # Aiden/
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Logging (plain, no-frills — guardian must stay lightweight)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [GUARDIAN] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("guardian")

# ---------------------------------------------------------------------------
# Sentinel file — when this file EXISTS Aiden should NOT be restarted.
# Written by the tray "Exit Aiden" action before killing the process.
# Deleted by the guardian after it reads it (one-shot).
# ---------------------------------------------------------------------------
SENTINEL_PATH = PROJECT_ROOT / "src" / "temp" / ".guardian_stop"

# ---------------------------------------------------------------------------
# PID file — lets external tools (stop_aiden.ps1 etc.) find Aiden's PID
# without having to scan all processes.
# ---------------------------------------------------------------------------
PID_FILE = PROJECT_ROOT / "src" / "temp" / ".aiden.pid"


def signal_guardian_stop() -> None:
    """Write the guardian sentinel file to prevent auto-restart on intentional exit."""
    try:
        SENTINEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        SENTINEL_PATH.touch()
        log.info(f"Guardian sentinel written: {SENTINEL_PATH}")
    except Exception as exc:
        log.warning(f"Could not write guardian sentinel: {exc}")


# ---------------------------------------------------------------------------
# Restart policy
# ---------------------------------------------------------------------------
MIN_UPTIME_SECONDS = 10   # Shorter than this = crash-loop back-off applies
MAX_RESTARTS       = 10   # Give up after this many rapid consecutive crashes
BACKOFF_SECONDS    = [2, 4, 8, 15, 30]  # Progressive delays (last is reused)
CLEAN_EXIT_CODES   = {0}  # Process exit codes treated as "user wanted this"

# ---------------------------------------------------------------------------
# Voice announcements — read .env for the same voice Aiden uses
# ---------------------------------------------------------------------------
_DOTENV = PROJECT_ROOT / ".env"

def _read_env_voice() -> str:
    """Read SPEECH_TTS_VOICE from .env, fall back to Aria."""
    default = "en-US-AriaNeural"
    try:
        if not _DOTENV.exists():
            return default
        for line in _DOTENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("SPEECH_TTS_VOICE="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                return val if val else default
    except Exception:
        pass
    return default


_TTS_VOICE = _read_env_voice()
_PYGAME_INIT_DONE = False


def _ensure_pygame():
    """Lazily initialise pygame mixer once."""
    global _PYGAME_INIT_DONE
    if _PYGAME_INIT_DONE:
        return True
    try:
        import pygame
        pygame.mixer.init()
        _PYGAME_INIT_DONE = True
        return True
    except Exception as exc:
        log.warning(f"Guardian: pygame init failed — voice alerts disabled: {exc}")
        return False


def _speak(text: str) -> None:
    """
    Speak *text* using Edge TTS + pygame, completely independent of Aiden's
    running state.  Runs synchronously (blocks until audio finishes).
    Fails silently so it never blocks the restart loop.
    """
    try:
        import edge_tts
        import pygame

        if not _ensure_pygame():
            return

        # Generate speech to a temp file
        tmp = Path(tempfile.mktemp(suffix=".mp3"))

        async def _gen():
            communicate = edge_tts.Communicate(text, voice=_TTS_VOICE)
            await communicate.save(str(tmp))

        asyncio.run(_gen())

        if not tmp.exists() or tmp.stat().st_size == 0:
            return

        pygame.mixer.music.load(str(tmp))
        pygame.mixer.music.play()

        # Wait until playback finishes
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)

        pygame.mixer.music.unload()
        try:
            tmp.unlink()
        except Exception:
            pass

    except Exception as exc:
        log.debug(f"Guardian speak failed (non-critical): {exc}")


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _sentinel_present() -> bool:
    return SENTINEL_PATH.exists()


def _clear_sentinel() -> None:
    try:
        SENTINEL_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _write_pid(pid: int) -> None:
    try:
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(pid), encoding="utf-8")
    except Exception as exc:
        log.warning(f"Could not write PID file: {exc}")


def _clear_pid() -> None:
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _backoff(attempt: int) -> float:
    idx = min(attempt, len(BACKOFF_SECONDS) - 1)
    return BACKOFF_SECONDS[idx]


def _find_python() -> str:
    return sys.executable


def _build_cmd(debug: bool, extra_args: list[str]) -> list[str]:
    entry = PROJECT_ROOT / "src" / "main.py"
    cmd = [_find_python(), str(entry)]
    if debug:
        cmd.append("--debug")
    cmd.extend(extra_args)
    return cmd


# ---------------------------------------------------------------------------
# Main watchdog loop
# ---------------------------------------------------------------------------

def run_guardian(debug: bool = False, extra_args: list[str] | None = None) -> None:
    extra_args = extra_args or []
    cmd = _build_cmd(debug, extra_args)
    consecutive_crashes = 0
    attempt = 0

    log.info("=" * 60)
    log.info("AIDEN GUARDIAN STARTED")
    log.info(f"  Project root : {PROJECT_ROOT}")
    log.info(f"  Entry point  : {cmd[1]}")
    log.info(f"  Debug mode   : {debug}")
    log.info(f"  Sentinel file: {SENTINEL_PATH}")
    log.info(f"  TTS voice    : {_TTS_VOICE}")
    log.info("=" * 60)

    # Clear any leftover sentinel from a previous session
    _clear_sentinel()

    while True:
        # ----------------------------------------------------------------
        # Pre-launch checks
        # ----------------------------------------------------------------
        if _sentinel_present():
            log.info("Sentinel file present — clean exit requested. Guardian stopping.")
            _clear_sentinel()
            _clear_pid()
            return

        if consecutive_crashes >= MAX_RESTARTS:
            msg = (
                f"Sir, I have crashed {consecutive_crashes} times in a row and cannot "
                "recover automatically. Please check the logs and restart me manually."
            )
            log.error(msg)
            _speak(msg)
            _clear_pid()
            return

        # ----------------------------------------------------------------
        # Launch Aiden
        # ----------------------------------------------------------------
        launch_time = time.monotonic()
        started_at = datetime.now().strftime("%H:%M:%S")
        log.info(
            f"[Attempt {attempt + 1}] Launching Aiden at {started_at} "
            f"(consecutive crashes: {consecutive_crashes})"
        )

        try:
            env = os.environ.copy()
            env["AIDEN_GUARDIAN_PID"] = str(os.getpid())

            proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                env=env,
                # In debug mode let the child inherit the console so its
                # logs appear in the same terminal window as the guardian.
                # In normal mode keep it hidden.
                creationflags=(
                    0 if debug
                    else subprocess.CREATE_NO_WINDOW
                ),
            )
        except Exception as exc:
            log.error(f"Failed to start Aiden: {exc}")
            consecutive_crashes += 1
            delay = _backoff(consecutive_crashes)
            _speak(
                f"Sir, I failed to start. This is attempt {consecutive_crashes}. "
                f"Retrying in {int(delay)} seconds."
            )
            log.info(f"Retrying in {delay}s …")
            time.sleep(delay)
            attempt += 1
            continue

        _write_pid(proc.pid)
        log.info(f"Aiden started — PID {proc.pid}")

        # ----------------------------------------------------------------
        # Wait for Aiden to exit
        # ----------------------------------------------------------------
        proc.wait()
        uptime = time.monotonic() - launch_time
        exit_code = proc.returncode

        _clear_pid()

        log.info(
            f"Aiden exited — PID {proc.pid}, code {exit_code}, "
            f"uptime {uptime:.1f}s"
        )

        # ----------------------------------------------------------------
        # Post-exit decision
        # ----------------------------------------------------------------

        # 1. Did the user ask for a clean stop via sentinel?
        if _sentinel_present():
            log.info("Sentinel file present after exit — honouring clean stop.")
            _clear_sentinel()
            return

        # 2. Was it a deliberate clean exit code?
        if exit_code in CLEAN_EXIT_CODES:
            log.info(f"Exit code {exit_code} is a clean exit. Guardian stopping.")
            return

        # 3. Treat as a crash — announce, back-off, restart
        uptime_str = (
            f"{int(uptime // 60)} minutes and {int(uptime % 60)} seconds"
            if uptime >= 60
            else f"{int(uptime)} seconds"
        )

        if uptime >= MIN_UPTIME_SECONDS:
            # Long-running session crashed — reset consecutive counter
            consecutive_crashes = 0
            delay = 1.5
            log.warning(
                f"Aiden died after {uptime:.1f}s (code {exit_code}). "
                "Restarting immediately…"
            )
            _speak(
                f"Sir, I encountered an unexpected error after running for {uptime_str} "
                "and had to shut down. Restarting now. One moment please."
            )
        else:
            consecutive_crashes += 1
            delay = _backoff(consecutive_crashes)
            log.warning(
                f"Aiden died too quickly ({uptime:.1f}s, code {exit_code}). "
                f"Crash #{consecutive_crashes}. Restarting in {delay}s…"
            )
            _speak(
                f"Sir, I crashed on startup. This is crash number {consecutive_crashes}. "
                f"I will try again in {int(delay)} seconds."
            )

        attempt += 1
        time.sleep(delay)


# ---------------------------------------------------------------------------
# Guardian self-protection: ignore SIGINT so Ctrl+C in the console only
# stops the guardian's interactive session, not the watched child.
# The child handles its own SIGINT separately.
# ---------------------------------------------------------------------------
def _setup_signals() -> None:
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except Exception:
        pass
    if sys.platform != "win32":
        try:
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _parse_args() -> tuple[bool, list[str]]:
    parser = argparse.ArgumentParser(
        description="Aiden Guardian — keeps Aiden alive automatically.",
        add_help=True,
    )
    parser.add_argument(
        "--debug", "-debug",
        action="store_true",
        default=False,
        help="Pass --debug to Aiden and keep the console visible.",
    )
    known, unknown = parser.parse_known_args()
    return known.debug, unknown


if __name__ == "__main__":
    _setup_signals()
    debug_mode, forwarded = _parse_args()
    run_guardian(debug=debug_mode, extra_args=forwarded)
