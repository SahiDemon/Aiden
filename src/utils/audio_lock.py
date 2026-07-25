"""
Global thread-safe reentrant lock for Windows audio device operations.

Prevents concurrent access between Pygame (SDL WASAPI output) and PyAudio
(PortAudio WASAPI input stream open/close/terminate), which otherwise causes
Windows audio driver buffer collisions and C-level access violations (0xC0000005).
"""
import threading

AUDIO_DEVICE_LOCK = threading.RLock()
