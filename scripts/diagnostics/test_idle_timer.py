import time
import ctypes
from ctypes import Structure, c_uint, sizeof

class LASTINPUTINFO(Structure):
    _fields_ = [
        ("cbSize", c_uint),
        ("dwTime", c_uint),
    ]

def get_idle_time_seconds() -> float:
    try:
        lii = LASTINPUTINFO()
        lii.cbSize = sizeof(LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            # Handle potential signed/unsigned difference
            tick_count = ctypes.windll.kernel32.GetTickCount()
            # Unsigned 32-bit subtraction to handle wrap-around
            millis = (tick_count - lii.dwTime) & 0xFFFFFFFF
            return max(0.0, millis / 1000.0)
    except Exception as e:
        print(f"Error: {e}")
    return 0.0

def run_test():
    print("=" * 65)
    print("         AIDEN IDLE TIMER DIAGNOSTIC RUNNER (1 MINUTE)")
    print("=" * 65)
    print("Instructions:")
    print("  1. Leave your mouse and keyboard completely untouched.")
    print("  2. Watch the timer go up to 60 seconds.")
    print("  3. If it resets back to 0, something on your PC is simulating input.")
    print("=" * 65)
    
    max_idle = 0.0
    previous_idle = 0.0
    
    for sec in range(1, 75): # Go up to 75 seconds
        time.sleep(1.0)
        idle = get_idle_time_seconds()
        
        # Track max idle time reached
        if idle > max_idle:
            max_idle = idle
            
        # Detect resets
        if idle < previous_idle and previous_idle > 1.5:
            print(f"⚠️ [RESET DETECTED] Timer fell from {previous_idle:.1f}s to {idle:.1f}s!")
            print("   -> This means Windows detected mouse/keyboard/joystick activity.")
            
        print(f"  [{sec:02d}s elapsed] Current Idle Time: {idle:.1f} seconds")
        
        if idle >= 60.0:
            print("\n🎉 [SUCCESS] You have successfully stayed idle for 60 seconds!")
            print("    Aiden's auto-shutdown would trigger now.")
            break
            
        previous_idle = idle
    else:
        print(f"\n❌ [FAIL] Did not reach 60 seconds of idle. Max idle reached was {max_idle:.1f} seconds.")
        print("   If you did not touch the mouse/keyboard, a background app or device driver")
        print("   is sending invisible inputs to keep your PC awake.")
        print("=" * 65)

if __name__ == "__main__":
    run_test()
