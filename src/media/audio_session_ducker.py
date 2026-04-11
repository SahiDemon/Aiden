"""
Per-application audio session muting for STT listening windows.
"""
from __future__ import annotations

import os
from typing import List, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from pycaw.pycaw import AudioUtilities
    from pycaw.constants import AudioSessionState

    PYCAW_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    AudioUtilities = None
    AudioSessionState = None
    PYCAW_AVAILABLE = False


class AudioSessionDucker:
    """Mute active non-whitelisted app sessions while STT is listening."""

    def __init__(self):
        self._current_pid = os.getpid()
        self._excluded_processes = {
            "python.exe",
            "pythonw.exe",
            "discord.exe",
            "spotify.exe",
            "signalrgb.exe",
        }

    def duck_for_listening(self) -> dict:
        """Mute active app sessions and return enough state to restore them."""
        if not PYCAW_AVAILABLE:
            logger.debug("pycaw not installed; audio-session ducking unavailable.")
            return {"muted_sessions": []}

        muted_sessions: List[dict] = []

        for session in AudioUtilities.GetAllSessions():
            process = session.Process
            if not process:
                continue

            try:
                process_name = process.name().lower()
                process_id = int(process.pid)
            except Exception:
                continue

            if process_id == self._current_pid:
                continue
            if process_name in self._excluded_processes:
                continue

            try:
                if session.State != AudioSessionState.Active:
                    continue
            except Exception:
                continue

            try:
                simple_volume = session.SimpleAudioVolume
                was_muted = bool(simple_volume.GetMute())
            except Exception:
                continue

            if was_muted:
                continue

            try:
                simple_volume.SetMute(1, None)
                muted_sessions.append(
                    {
                        "process_id": process_id,
                        "process_name": process_name,
                    }
                )
                logger.info(f"Muted active app audio for STT: {process_name} ({process_id})")
            except Exception as exc:
                logger.debug(f"Failed to mute app audio session {process_name} ({process_id}): {exc}")

        return {"muted_sessions": muted_sessions}

    def restore_after_listening(self, state: Optional[dict]) -> None:
        """Unmute only the app sessions we muted during duck_for_listening."""
        if not PYCAW_AVAILABLE or not state:
            return

        muted_sessions = state.get("muted_sessions") or []
        if not muted_sessions:
            return

        target_keys = {
            (int(item.get("process_id", 0)), str(item.get("process_name", "")).lower())
            for item in muted_sessions
            if item.get("process_id")
        }
        if not target_keys:
            return

        for session in AudioUtilities.GetAllSessions():
            process = session.Process
            if not process:
                continue

            try:
                process_name = process.name().lower()
                process_id = int(process.pid)
            except Exception:
                continue

            if (process_id, process_name) not in target_keys:
                continue

            try:
                simple_volume = session.SimpleAudioVolume
                if simple_volume.GetMute():
                    simple_volume.SetMute(0, None)
                    logger.info(f"Restored app audio after STT: {process_name} ({process_id})")
            except Exception as exc:
                logger.debug(f"Failed to restore app audio session {process_name} ({process_id}): {exc}")


_audio_session_ducker: Optional[AudioSessionDucker] = None


def get_audio_session_ducker() -> AudioSessionDucker:
    global _audio_session_ducker
    if _audio_session_ducker is None:
        _audio_session_ducker = AudioSessionDucker()
    return _audio_session_ducker
