import asyncio
import sys
import os
import platform
import time
import pygame

# Ensure src is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.utils.media_idle_monitor import MediaIdleMonitor, PYCAW_AVAILABLE
if PYCAW_AVAILABLE:
    from pycaw.pycaw import AudioUtilities

async def run_diagnostics():
    print("=" * 60)
    print("      AIDEN AUTO-SHUTDOWN SYSTEM DIAGNOSTICS")
    print("=" * 60)
    
    # Reload monitor to pick up pycaw
    import importlib
    import src.utils.media_idle_monitor
    importlib.reload(src.utils.media_idle_monitor)
    from src.utils.media_idle_monitor import MediaIdleMonitor, PYCAW_AVAILABLE
    
    monitor = MediaIdleMonitor()
    
    # 1. Check Platform
    print(f"OS Platform: {platform.system()}")
    
    # 2. Check pycaw availability
    print(f"Pycaw Available: {PYCAW_AVAILABLE}")
    if PYCAW_AVAILABLE:
        print("\n--- Active Audio Sessions Across All Devices ---")
        try:
            sessions = monitor._get_all_audio_sessions()
            count = 0
            for session in sessions:
                proc = session.Process
                if proc:
                    count += 1
                    state = session.State # 0=Inactive, 1=Active, 2=Expired
                    state_str = "Active" if state == 1 else "Inactive" if state == 0 else "Expired"
                    vol = session.SimpleAudioVolume.GetMasterVolume()
                    mute = session.SimpleAudioVolume.GetMute()
                    print(f"  - Process: {proc.name()} (PID: {proc.pid})")
                    print(f"    State: {state_str}, Volume: {vol:.2f}, Muted: {mute}")
            if count == 0:
                print("  No active audio sessions with processes found.")
        except Exception as e:
            print(f"  Error reading audio sessions: {e}")
    
    print(f"\nis_media_playing() returned: {monitor.is_media_playing()}")
    
    # 3. Check Game Controllers / Joysticks using Pygame
    print("\n--- Game Controller Check ---")
    try:
        pygame.init()
        pygame.joystick.init()
        joystick_count = pygame.joystick.get_count()
        print(f"Detected Joysticks/Controllers: {joystick_count}")
        for i in range(joystick_count):
            js = pygame.joystick.Joystick(i)
            js.init()
            print(f"  - Joystick {i}: {js.get_name()}")
            print(f"    Axes: {js.get_numaxes()}, Buttons: {js.get_numbuttons()}, Hats: {js.get_numhats()}")
            
            # Print current state of axes
            axes_vals = []
            for a in range(js.get_numaxes()):
                val = js.get_axis(a)
                if abs(val) > 0.05:  # Log significant drift
                    axes_vals.append(f"Axis {a}={val:.3f}")
            if axes_vals:
                print(f"    ⚠️ ACTIVE DRIFT DETECTED: {', '.join(axes_vals)}")
            else:
                print("    Axes are centered (no significant drift detected).")
    except Exception as e:
        print(f"  Error checking gamepads: {e}")
    
    print("\n--- Monitoring Idle Time for 15 seconds ---")
    print("Please do NOT touch the mouse or keyboard during this test...")
    for i in range(15):
        idle = monitor.get_idle_time_seconds()
        print(f"  [{i+1}/15] Current Idle Time: {idle:.2f} seconds")
        await asyncio.sleep(1.0)
        
    print("\nDiagnostics completed!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
