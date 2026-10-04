from pycaw.pycaw import AudioUtilities

def mute_browser_only():
    browsers = ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"]
    sessions = AudioUtilities.GetAllSessions()
    
    for session in sessions:
        if session.Process and session.Process.name().lower() in browsers:
            # SetMute(1, None) mutes the app. Use SetMute(0, None) to unmute.
            session.SimpleAudioVolume.SetMute(1, None)
            print(f"🔇 Successfully muted {session.Process.name()}!")

if __name__ == "__main__":
    mute_browser_only()
