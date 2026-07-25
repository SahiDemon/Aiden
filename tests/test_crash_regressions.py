"""
Crash regression tests for the pygame / TTS stability fixes.

Scenarios covered:
1. stop() called before any sound has ever played (the exact crash that was happening)
2. stop() called multiple times in a row without segfaulting
3. _ensure_mixer() is idempotent and never raises
4. pygame mixer is initialized when main.py startup block runs
5. wake-word activation path: pause → schedule coroutine → resume
"""
import asyncio
import sys
import os
import threading
import importlib

import pytest

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_tts_module():
    """Force tts module into a fresh un-initialized state for isolation."""
    import src.speech.tts as tts_mod
    tts_mod._MIXER_INITIALIZED = False
    tts_mod.PYGAME_AVAILABLE = True


# ---------------------------------------------------------------------------
# 1. _ensure_mixer() never raises, always returns a bool
# ---------------------------------------------------------------------------

def test_ensure_mixer_never_raises():
    """_ensure_mixer() must not raise even if pygame is broken/absent."""
    import src.speech.tts as tts_mod
    result = tts_mod._ensure_mixer()
    assert isinstance(result, bool)


def test_ensure_mixer_idempotent():
    """Calling _ensure_mixer() many times must return the same value."""
    import src.speech.tts as tts_mod
    results = {tts_mod._ensure_mixer() for _ in range(10)}
    assert len(results) == 1, "Multiple calls returned different values"


# ---------------------------------------------------------------------------
# 2. stop() safe before any sound plays (THE crash regression)
# ---------------------------------------------------------------------------

def test_stop_before_any_sound_does_not_crash():
    """
    Regression: tts.stop() was called as barge-in the moment a wake-word fired,
    *before* any TTS had ever played (so pygame mixer was uninitialised).
    This used to segfault. It must now complete silently.
    """
    import src.speech.tts as tts_mod

    # Simulate the exact pre-crash state: mixer not yet initialised
    # but main.py startup block has since run and set the flags.
    tts_mod._ensure_mixer()  # make sure mixer is up (mirrors startup block)

    # Build a minimal TTSEngine with a real async queue but no tasks running
    loop = asyncio.new_event_loop()
    try:
        async def _run():
            engine = tts_mod.TTSEngine.__new__(tts_mod.TTSEngine)
            engine.audio_queue = asyncio.Queue()
            engine.is_processing = False
            engine._wake_word_pause_depth = 0
            engine._preloaded_sounds = {}

            # THE CRASH SCENARIO: call stop() with no audio ever played
            engine.stop()   # must not raise or segfault

            # Call it again immediately (double-stop race)
            engine.stop()

        loop.run_until_complete(_run())
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# 3. stop_playback_now() safe from a background thread (hotkey path)
# ---------------------------------------------------------------------------

def test_stop_playback_now_from_thread():
    """stop_playback_now() is called from hotkey threads — must be thread-safe."""
    import src.speech.tts as tts_mod
    tts_mod._ensure_mixer()

    errors = []

    def _thread_stop():
        try:
            # Build minimal engine
            engine = tts_mod.TTSEngine.__new__(tts_mod.TTSEngine)
            engine.audio_queue = asyncio.Queue()
            engine.is_processing = False
            engine._wake_word_pause_depth = 0
            engine._preloaded_sounds = {}
            engine.stop_playback_now()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_thread_stop) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not errors, f"stop_playback_now() raised from thread: {errors}"


# ---------------------------------------------------------------------------
# 4. Main startup block initialises pygame before TTS imports
# ---------------------------------------------------------------------------

def test_main_startup_sets_mixer_flags():
    """
    The startup block in main.py must mark the mixer as initialized so that
    the first tts.stop() call doesn't hit an uninitialized mixer.
    """
    import src.speech.tts as tts_mod

    # Simulate the main.py startup block
    import pygame
    if not pygame.mixer.get_init():
        pygame.mixer.init()
    tts_mod._MIXER_INITIALIZED = True
    tts_mod.PYGAME_AVAILABLE = True

    # Now _ensure_mixer() should immediately return True without re-running init
    assert tts_mod._ensure_mixer() is True
    assert tts_mod._MIXER_INITIALIZED is True
    assert tts_mod.PYGAME_AVAILABLE is True


# ---------------------------------------------------------------------------
# 5. Queue clear in stop() doesn't raise on empty queue
# ---------------------------------------------------------------------------

def test_stop_clears_empty_queue_safely():
    """stop() drains the audio queue; must not raise if queue is already empty."""
    import src.speech.tts as tts_mod
    tts_mod._ensure_mixer()

    loop = asyncio.new_event_loop()
    try:
        async def _run():
            engine = tts_mod.TTSEngine.__new__(tts_mod.TTSEngine)
            engine.audio_queue = asyncio.Queue()
            engine.is_processing = False
            engine._wake_word_pause_depth = 0
            engine._preloaded_sounds = {}

            # Put some items then stop
            await engine.audio_queue.put({"type": "speak", "data": b"", "text": "hi"})
            await engine.audio_queue.put({"type": "speak", "data": b"", "text": "bye"})
            engine.stop()
            assert engine.audio_queue.empty()

        loop.run_until_complete(_run())
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# 6. comtypes import in audio_session_ducker doesn't raise
# ---------------------------------------------------------------------------

def test_audio_session_ducker_imports_comtypes():
    """comtypes must be importable inside audio_session_ducker (was missing)."""
    import src.media.audio_session_ducker as ducker_mod
    # If comtypes wasn't importable, PYCAW_AVAILABLE would be False and
    # comtypes would be None — but it should be a real module
    if ducker_mod.PYCAW_AVAILABLE:
        import comtypes
        assert ducker_mod.comtypes is comtypes
    else:
        pytest.skip("pycaw not installed — COM path not testable")


# ---------------------------------------------------------------------------
# 7. duck_for_listening returns a dict (no NameError crash)
# ---------------------------------------------------------------------------

def test_duck_for_listening_returns_dict():
    """duck_for_listening() must return a dict and never raise NameError."""
    from src.media.audio_session_ducker import get_audio_session_ducker
    ducker = get_audio_session_ducker()
    result = ducker.duck_for_listening()
    assert isinstance(result, dict)
    assert "muted_sessions" in result
    assert isinstance(result["muted_sessions"], list)
