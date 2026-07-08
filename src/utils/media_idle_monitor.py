"""
Media Idle Monitor - Automatically shuts down PC when media is paused/stopped and system is idle.
Useful for overnight movie watching (VLC, Jellyfin, browsers, etc.) to prevent running PC all night.
"""
import asyncio
import ctypes
import json
import os
import platform
import subprocess
import urllib.request
from ctypes import Structure, c_uint, sizeof
from typing import Optional

from src.speech.tts import get_tts_engine
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
    from pycaw.constants import AudioSessionState
    PYCAW_AVAILABLE = True
except ImportError:
    AudioUtilities = None
    IAudioMeterInformation = None
    AudioSessionState = None
    PYCAW_AVAILABLE = False



class LASTINPUTINFO(Structure):
    _fields_ = [
        ("cbSize", c_uint),
        ("dwTime", c_uint),
    ]


class MediaIdleMonitor:
    """
    Monitors media audio playback and Windows user idle time (mouse/keyboard).
    When enabled in settings, shuts down PC if media is stopped/paused and PC is idle for N minutes.
    """

    def __init__(self, polling_interval: float = 30.0):
        self.polling_interval = polling_interval
        self.running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._warning_triggered = False
        self._current_pid = os.getpid()

        logger.info("Media Idle Monitor initialized")

    def start(self):
        """Start the async monitoring loop."""
        if self.running:
            logger.warning("Media Idle Monitor is already running")
            return

        if platform.system() != "Windows":
            logger.warning("Media Idle Monitor is only supported on Windows")
            return

        self.running = True
        self._warning_triggered = False
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("✅ Media Idle Monitor started")

    def stop(self):
        """Stop the monitoring loop."""
        self.running = False
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
        logger.info("Media Idle Monitor stopped")

    def get_idle_time_seconds(self) -> float:
        """Get user inactivity (mouse/keyboard idle) duration in seconds."""
        if platform.system() != "Windows":
            return 0.0
        try:
            lii = LASTINPUTINFO()
            lii.cbSize = sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                tick_count = ctypes.windll.kernel32.GetTickCount()
                millis = (tick_count - lii.dwTime) & 0xFFFFFFFF
                return max(0.0, millis / 1000.0)
        except Exception as e:
            logger.debug(f"Failed to get system idle time: {e}")
        return 0.0

    def _check_jellyfin_playback(self) -> bool:
        """Query Jellyfin REST API to check if any active session is currently playing media."""
        try:
            settings = get_settings()
            jf_url = getattr(settings.app, "jellyfin_url", "").rstrip("/")
            jf_key = getattr(settings.app, "jellyfin_api_key", "")
            if not jf_url or not jf_key:
                return False

            req = urllib.request.Request(
                f"{jf_url}/Sessions",
                headers={"X-Emby-Token": jf_key, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                sessions = json.loads(resp.read().decode("utf-8"))
                for s in sessions:
                    now_playing = s.get("NowPlayingItem")
                    if now_playing:
                        is_paused = s.get("PlayState", {}).get("IsPaused", True)
                        if not is_paused:
                            return True
        except Exception as e:
            logger.debug(f"Error checking Jellyfin API: {e}")
    def _get_all_audio_sessions(self) -> list:
        """Enumerate audio sessions across ALL active sound output devices (speakers, headphones, DACs, HDMI, etc.)."""
        sessions = []
        if not PYCAW_AVAILABLE or not AudioUtilities:
            return sessions

        enumerator = None
        devices = None
        dev = None
        mgr = None
        mgr2 = None
        session_enum = None
        ctl = None
        ctl2 = None

        try:
            from pycaw.constants import EDataFlow, DEVICE_STATE
            from pycaw.api.audiopolicy import IAudioSessionManager2, IAudioSessionControl2
            from pycaw.pycaw import AudioSession
            from comtypes import CLSCTX_ALL, cast, POINTER

            enumerator = AudioUtilities.GetDeviceEnumerator()
            if not enumerator:
                return sessions
            devices = enumerator.EnumAudioEndpoints(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value)
            if not devices:
                return sessions
            for i in range(devices.GetCount()):
                try:
                    dev = devices.Item(i)
                    if not dev:
                        continue
                    mgr = dev.Activate(IAudioSessionManager2._iid_, CLSCTX_ALL, None)
                    if not mgr:
                        continue
                    mgr2 = cast(mgr, POINTER(IAudioSessionManager2))
                    if not mgr2:
                        continue
                    session_enum = mgr2.GetSessionEnumerator()
                    if not session_enum:
                        continue
                    for j in range(session_enum.GetCount()):
                        try:
                            ctl = session_enum.GetSession(j)
                            if not ctl:
                                continue
                            ctl2 = cast(ctl, POINTER(IAudioSessionControl2))
                            if not ctl2:
                                continue
                            sessions.append(AudioSession(ctl2))
                        except Exception:
                            pass
                        finally:
                            ctl = None
                            ctl2 = None
                except Exception:
                    continue
                finally:
                    dev = None
                    mgr = None
                    mgr2 = None
                    session_enum = None
        except Exception as e:
            logger.debug(f"Error enumerating all device sessions, falling back to default: {e}")
            try:
                sessions = AudioUtilities.GetAllSessions()
            except Exception:
                pass
        finally:
            enumerator = None
            devices = None

        return sessions

    def is_media_playing(self) -> bool:
        """Check if any application (VLC, Jellyfin, browser, etc.) is currently playing audio/video."""
        # 1. Check Jellyfin server API directly (accurate for Jellyfin Media Player / MPV bitstreaming)
        if self._check_jellyfin_playback():
            return True

        if not PYCAW_AVAILABLE or not AudioUtilities:
            return False

        import comtypes
        try:
            comtypes.CoInitialize()
        except Exception:
            pass

        sessions = []
        result = False

        # Lowercase process names to ignore (non-media or background apps)
        IGNORE_PROCESSES = {
            "signalrgb.exe",
            "discord.exe",
            "steamwebhelper.exe",
            "steam.exe",
            "wallpaper64.exe",
            "obs64.exe",
            "python.exe",
            "audiodg.exe",
            "nvsphelper64.exe",
            "nvidia share.exe",
            "nvcontainer.exe",
        }
        IGNORE_KEYWORDS = (
            "nvcontainer",
            "nvdisplay",
            "nvsphelper",
            "nvidia",
            "geforce",
            "steam",
            "discord",
            "signalrgb",
            "wallpaper",
            "obs",
            "python",
            "audiodg",
            "voicemeeter",
            "fxsound",
            "steelseries",
            "sonar",
            "icue",
            "razer",
            "logioptions",
            "lghub",
            "epicgames",
            "ubisoft",
            "eadesktop",
            "battle.net",
            "cortana",
            "searchapp",
            "explorer",
            "shellexperiencehost",
            "startmenuexperiencehost",
            "textinputhost",
            "systemsettings",
            "taskmgr",
            "svchost",
        )

        try:
            sessions = self._get_all_audio_sessions()
            for session in sessions:
                process = session.Process
                if not process:
                    continue

                try:
                    proc_name = process.name().lower()
                    if proc_name in IGNORE_PROCESSES or any(kw in proc_name for kw in IGNORE_KEYWORDS):
                        continue

                    pid = int(process.pid)
                    if pid == self._current_pid:
                        continue
                except Exception:
                    continue

                try:
                    # Check WASAPI active state (catches YouTube, browsers, VLC, Spotify, etc.)
                    if session.State == AudioSessionState.Active:
                        simple_volume = session.SimpleAudioVolume
                        if not simple_volume.GetMute() and simple_volume.GetMasterVolume() > 0.001:
                            result = True
                            break

                    # Check IAudioMeterInformation peak level (catches direct streams or apps with State=0)
                    if IAudioMeterInformation:
                        try:
                            meter = session._ctl.QueryInterface(IAudioMeterInformation)
                            if meter.GetPeakValue() > 0.0001:
                                result = True
                                break
                        except Exception:
                            pass
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Error checking active audio sessions: {e}")
        finally:
            # Cleanly release all COM interface references in returned objects
            for s in sessions:
                try:
                    s._ctl = None
                except Exception:
                    pass
            sessions = []
            
            # Clean up local references
            session = None
            process = None
            simple_volume = None
            meter = None

        return result

    async def _monitor_loop(self):
        """Main background checking loop."""
        try:
            while self.running:
                await asyncio.sleep(self.polling_interval)
                await self._check_idle_state()
        except asyncio.CancelledError:
            logger.info("Media Idle Monitor loop cancelled")
        except Exception as e:
            logger.error(f"Error in Media Idle Monitor loop: {e}", exc_info=True)
            self.running = False

    async def _check_idle_state(self):
        """Check if condition for auto-shutdown is met."""
        settings = get_settings()
        if not getattr(settings.app, "media_idle_shutdown_enabled", False):
            self._warning_triggered = False
            return

        timeout_minutes = getattr(settings.app, "media_idle_timeout_minutes", 15)
        timeout_seconds = max(1, timeout_minutes) * 60

        is_playing = self.is_media_playing()
        idle_seconds = self.get_idle_time_seconds()

        if is_playing:
            # Media is playing (film is on), hold idle timer
            if self._warning_triggered:
                logger.info("Media playback resumed; aborting pending idle shutdown.")
                self._warning_triggered = False
            return

        # Media is NOT playing (paused or stopped)
        if idle_seconds >= timeout_seconds and not self._warning_triggered:
            self._warning_triggered = True
            logger.warning(
                f"💤 Media stopped/paused and system idle for {idle_seconds/60:.1f} mins "
                f"(threshold: {timeout_minutes} mins). Initiating auto-shutdown sequence."
            )
            await self._trigger_shutdown_sequence(timeout_minutes)

    async def _trigger_shutdown_sequence(self, timeout_minutes: int):
        """Announce warning and execute shutdown if idle state persists."""
        tts = get_tts_engine()
        await tts.play_sound("warning")
        message = (
            f"Sir, the system has been idle for {timeout_minutes} minutes. "
            "Initiating automatic power-saving shutdown in 15 seconds. Move your mouse or press any key to abort."
        )
        await tts.speak(message)

        # Wait 15 seconds to allow user to abort by moving mouse/keyboard
        await asyncio.sleep(15.0)

        if not self.running or not getattr(get_settings().app, "media_idle_shutdown_enabled", False):
            logger.info("Idle shutdown aborted: monitor stopped or disabled.")
            self._warning_triggered = False
            return

        # Re-check idle time; if it dropped significantly (< 10 seconds), user interacted!
        current_idle = self.get_idle_time_seconds()
        if current_idle < 15.0:
            logger.info(f"Idle shutdown aborted by user activity (current idle: {current_idle:.1f}s).")
            await tts.play_sound("success")
            await tts.speak("Shutdown aborted, Sir. Resuming normal operations.")
            self._warning_triggered = False
            return

        logger.critical("💤 EXECUTING MEDIA IDLE AUTO-SHUTDOWN")
        await tts.speak("Shutting down now. Goodnight, Sir.")
        await asyncio.sleep(1.0)

        try:
            subprocess.run(["shutdown", "/s", "/f", "/t", "0"], check=False)
        except Exception as e:
            logger.error(f"Failed to execute shutdown command: {e}", exc_info=True)


# Global instance
_media_idle_monitor: Optional[MediaIdleMonitor] = None


def get_media_idle_monitor() -> MediaIdleMonitor:
    """Get or create the global MediaIdleMonitor instance."""
    global _media_idle_monitor
    if _media_idle_monitor is None:
        _media_idle_monitor = MediaIdleMonitor()
    return _media_idle_monitor
