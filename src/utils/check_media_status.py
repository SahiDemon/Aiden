"""
Aiden Live Media Playback Detection Inspector.
Run this script to see exactly which apps, audio devices, and servers (Jellyfin/VLC/Browser/etc.)
are currently playing media and preventing system auto-shutdown.
"""
import json
import os
import sys
import urllib.request
from typing import List, Tuple

# Add project root to path if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.utils.config import get_settings
from src.utils.logger import get_logger
from src.utils.media_idle_monitor import MediaIdleMonitor, PYCAW_AVAILABLE

logger = get_logger(__name__)

def check_jellyfin() -> Tuple[bool, List[str]]:
    triggers = []
    try:
        settings = get_settings()
        jf_url = getattr(settings.app, "jellyfin_url", "").rstrip("/")
        jf_key = getattr(settings.app, "jellyfin_api_key", "")
        if not jf_url or not jf_key:
            return False, ["Jellyfin API not configured (missing URL or API Key in .env)"]

        req = urllib.request.Request(
            f"{jf_url}/Sessions",
            headers={"X-Emby-Token": jf_key, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            sessions = json.loads(resp.read().decode("utf-8"))
            active_count = 0
            for s in sessions:
                now_playing = s.get("NowPlayingItem")
                if now_playing:
                    is_paused = s.get("PlayState", {}).get("IsPaused", True)
                    title = now_playing.get("Name", "Unknown Title")
                    client = s.get("Client", "Unknown Client")
                    dev_name = s.get("DeviceName", "Unknown Device")
                    status_str = "PAUSED" if is_paused else "PLAYING"
                    info = f'[{status_str}] "{title}" on {client} ({dev_name})'
                    if not is_paused:
                        active_count += 1
                        triggers.append(f"Jellyfin Active: {info}")
                    else:
                        triggers.append(f"Jellyfin Idle: {info}")
            if active_count > 0:
                return True, triggers
            elif len(triggers) == 0:
                return False, ["No active playback sessions found on Jellyfin server"]
            return False, triggers
    except Exception as e:
        return False, [f"Error connecting to Jellyfin API: {e}"]

def inspect_audio_devices() -> Tuple[bool, List[str], List[str]]:
    triggers = []
    output_lines = []
    is_playing = False

    if not PYCAW_AVAILABLE:
        return False, ["pycaw library not available"], triggers

    try:
        from pycaw.pycaw import AudioUtilities, AudioDevice, AudioSession, IAudioMeterInformation
        from pycaw.constants import EDataFlow, DEVICE_STATE, AudioSessionState
        from pycaw.api.audiopolicy import IAudioSessionManager2, IAudioSessionControl2
        from comtypes import CLSCTX_ALL, cast, POINTER

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

        enumerator = AudioUtilities.GetDeviceEnumerator()
        devices = enumerator.EnumAudioEndpoints(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value)
        
        output_lines.append(f"Total Active Sound Output Devices Found: {devices.GetCount()}\n")

        for i in range(devices.GetCount()):
            dev = devices.Item(i)
            try:
                dev_obj = AudioUtilities.CreateDevice(dev)
                dev_name = dev_obj.FriendlyName
            except Exception:
                dev_name = f"Endpoint ID {dev.GetId()[:20]}..."

            output_lines.append(f"  Device [{i}]: {dev_name}")
            try:
                mgr = dev.Activate(IAudioSessionManager2._iid_, CLSCTX_ALL, None)
                mgr2 = cast(mgr, POINTER(IAudioSessionManager2))
                session_enum = mgr2.GetSessionEnumerator()
                
                sess_count = session_enum.GetCount()
                if sess_count == 0:
                    output_lines.append("     (No audio sessions attached)")
                
                for j in range(sess_count):
                    ctl = session_enum.GetSession(j)
                    ctl2 = cast(ctl, POINTER(IAudioSessionControl2))
                    session = AudioSession(ctl2)
                    
                    proc = session.Process
                    proc_name = proc.name() if proc else "System/Unknown"
                    pid = proc.pid if proc else 0
                    
                    state = session.State
                    state_str = "Active" if state == 1 else "Inactive" if state == 0 else "Expired"
                    
                    vol = session.SimpleAudioVolume.GetMasterVolume() if session.SimpleAudioVolume else 0.0
                    mute = session.SimpleAudioVolume.GetMute() if session.SimpleAudioVolume else False
                    
                    peak = 0.0
                    if IAudioMeterInformation:
                        try:
                            meter = session._ctl.QueryInterface(IAudioMeterInformation)
                            peak = meter.GetPeakValue()
                        except Exception:
                            pass

                    proc_lower = proc_name.lower()
                    is_ignored = proc_lower in IGNORE_PROCESSES or any(kw in proc_lower for kw in IGNORE_KEYWORDS)
                    
                    # Evaluate if this session counts as playing media
                    session_triggered = False
                    reason = ""
                    if not is_ignored and pid != os.getpid():
                        if state == 1 and not mute and vol > 0.001:
                            session_triggered = True
                            reason = f"Active State (Vol {vol*100:.0f}%)"
                        elif peak > 0.0001 and not mute and vol > 0.001:
                            session_triggered = True
                            reason = f"Audio Peak Meter ({peak:.4f})"

                    if session_triggered:
                        is_playing = True
                        status_tag = f"=> [TRIGGERED: {reason}]"
                        triggers.append(f"{proc_name} (PID: {pid}) on '{dev_name}' [{reason}]")
                    elif is_ignored:
                        status_tag = "[IGNORED PROCESS]"
                    else:
                        status_tag = "[IDLE]"

                    output_lines.append(
                        f"     - {proc_name:<22} | State: {state_str:<8} | Vol: {vol*100:3.0f}% | "
                        f"Muted: {'Yes' if mute else 'No':<3} | Peak: {peak:.4f} | {status_tag}"
                    )
                output_lines.append("")
            except Exception as e:
                output_lines.append(f"     [Error querying sessions: {e}]\n")

    except Exception as e:
        output_lines.append(f"Error enumerating devices: {e}")

    return is_playing, output_lines, triggers

def main():
    print("=" * 80)
    print("                AIDEN LIVE MEDIA PLAYBACK DETECTION INSPECTOR")
    print("=" * 80)
    print("Checking all audio output devices, browser tabs, media players, and servers...\n")

    # 1. Jellyfin Check
    print("[1/2] Checking Jellyfin Server API...")
    jf_playing, jf_info = check_jellyfin()
    for line in jf_info:
        prefix = "  => [TRIGGERED] " if jf_playing and "PLAYING" in line else "  -> "
        print(f"{prefix}{line}")
    print("")

    # 2. Audio Devices Check
    print("[2/2] Inspecting All Audio Devices & Sessions (WASAPI & Peak Metering)...")
    audio_playing, audio_lines, audio_triggers = inspect_audio_devices()
    for line in audio_lines:
        print(line)

    # 3. Final Summary
    monitor = MediaIdleMonitor()
    final_result = monitor.is_media_playing()

    print("=" * 80)
    if final_result:
        print("  STATUS:  MEDIA PLAYING  (System Auto-Shutdown is PAUSED)")
    else:
        print("  STATUS:  SYSTEM IDLE  (No active media detected)")
    print("=" * 80)

    all_triggers = []
    if jf_playing:
        for t in jf_info:
            if "Jellyfin Active" in t:
                all_triggers.append(t)
    all_triggers.extend(audio_triggers)

    if all_triggers:
        print("\nActive Triggers Preventing Idle Shutdown:")
        for idx, trg in enumerate(all_triggers, 1):
            print(f"  {idx}. {trg}")
    else:
        print("\nNo media triggers currently active.")
    print("=" * 80)

if __name__ == "__main__":
    main()
