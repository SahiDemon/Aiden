"""
Wake Word Detection System (Vosk fallback)
Migrated from efficient_wake_word.py and vosk_wake_word.py

Includes:
- Auto-restart watchdog (survives PyAudio / driver crashes)
- False positive reduction with energy gating and debounce
"""
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional
import numpy as np
import pyaudio
import vosk

from src.utils.config import get_settings
from src.utils.logger import get_logger
from src.utils.paths import resource_path

logger = get_logger(__name__)

# Watchdog constants
_MAX_RAPID_RESTARTS = 5
_RAPID_RESTART_WINDOW = 60  # seconds


class WakeWordDetector:
    """
    Wake word detector using Vosk.
    Wrapped in a supervisor/watchdog so transient audio errors
    don't permanently kill listening.
    """

    def __init__(self, on_wake_word: Optional[Callable] = None):
        self.settings = get_settings()
        self.wake_word = self.settings.app.wake_word.lower()
        self.on_wake_word = on_wake_word

        # Vosk model
        configured_model_path = Path(
            self.settings.speech.vosk_model_path or "vosk_models/vosk-model-small-en-us-0.15"
        )
        self.model_path = str(
            configured_model_path
            if configured_model_path.is_absolute()
            else resource_path(*configured_model_path.parts)
        )
        self.model = None
        self.recognizer = None

        # Audio settings
        self.audio = None
        self.stream = None

        # False positive prevention
        # Raised from 150.0 → 300.0: prevents distant TV / fan noise from
        # passing the energy gate into the wake-word detection pipeline.
        self.min_audio_energy = 300.0
        self.debounce_time = 2.0   # raised from 1.5 s → 2.0 s (matches Porcupine default)
        self.last_detection_time = 0

        # Control flags
        self.is_running = False
        self.is_paused = False
        self._thread = None

        # Watchdog stats
        self._restart_count = 0
        self._restart_timestamps: list[float] = []
        self._total_frames_processed = 0
        self._last_health_log = 0.0

        logger.info(f"Wake Word Detector initialized: wake_word='{self.wake_word}', model='{self.model_path}'")

    def _load_model(self):
        """Load Vosk model"""
        try:
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Vosk model not found at: {self.model_path}")

            logger.info(f"Loading Vosk model from: {self.model_path}")
            self.model = vosk.Model(self.model_path)
            self.recognizer = vosk.KaldiRecognizer(self.model, 16000)
            self.recognizer.SetWords(True)
            logger.info("Vosk model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Vosk model: {e}")
            raise

    # ------------------------------------------------------------------ #
    #  Start / Stop / Pause / Resume
    # ------------------------------------------------------------------ #

    def start(self):
        """Start wake word detection in a supervised background thread."""
        if self.is_running:
            logger.warning("Wake word detector already running")
            return

        logger.info("Starting wake word detector...")
        self.is_running = True
        self._thread = threading.Thread(target=self._supervisor_loop, daemon=True, name="vosk-watchdog")
        self._thread.start()
        logger.info("Wake word detector started (with watchdog)")

    def stop(self):
        """Stop wake word detection"""
        logger.info("Stopping wake word detector...")
        self.is_running = False

        if self._thread:
            self._thread.join(timeout=3.0)

        self._cleanup_audio()
        logger.info(f"Wake word detector stopped (total restarts: {self._restart_count})")

    def pause(self):
        """Pause wake word detection (during conversation)"""
        logger.debug("Wake word detector paused")
        self.is_paused = True

    def resume(self):
        """Resume wake word detection"""
        logger.debug("Wake word detector resumed")
        self.is_paused = False

    # ------------------------------------------------------------------ #
    #  Audio helpers
    # ------------------------------------------------------------------ #

    def _cleanup_audio(self):
        """Safely tear down PyAudio resources."""
        if self.stream:
            try:
                if self.stream.is_active():
                    self.stream.stop_stream()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        if self.audio:
            try:
                self.audio.terminate()
            except Exception:
                pass
            self.audio = None

    def _check_audio_energy(self, audio_data: bytes) -> bool:
        """Check if audio has sufficient energy to contain speech."""
        try:
            audio_frame = np.frombuffer(audio_data, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_frame.astype(np.float32) ** 2))
            return rms > self.min_audio_energy
        except Exception as e:
            logger.error(f"Error checking audio energy: {e}")
            return True

    def _should_process_detection(self) -> bool:
        """Debounce: avoid rapid re-triggers."""
        current_time = time.time()
        time_since_last = current_time - self.last_detection_time
        if time_since_last < self.debounce_time:
            logger.debug(f"Debouncing detection (only {time_since_last:.2f}s since last)")
            return False
        return True

    def _is_wake_word_match(self, text: str) -> bool:
        """Check if text matches wake word with fuzzy matching."""
        text = text.lower().strip()
        wake = self.wake_word.lower()

        # Exact match
        if wake in text:
            return True

        # Common variations for "aiden".
        # "aden" removed — only 4 chars; false-matches "eight", "maiden",
        # names in background TV audio, etc.
        if wake == "aiden":
            variations = ["aidan", "ayden", "hey aiden", "ok aiden"]
            for variation in variations:
                if variation in text:
                    logger.debug(f"Matched variation: '{variation}' in '{text}'")
                    return True

        # Fuzzy match — requires:
        #   1. Wake word >= 4 chars (already guaranteed for "aiden")
        #   2. Candidate word is within 1 char of wake word length
        #   3. Similarity >= 0.92 (raised from 0.90 to reduce false positives
        #      from short words like "maiden", "hayden", "pagan")
        if len(wake) >= 4:
            from difflib import SequenceMatcher
            words = text.split()
            for word in words:
                if len(word) < 4:
                    continue  # very short words can't reliably fuzzy-match
                if abs(len(word) - len(wake)) <= 1:
                    similarity = SequenceMatcher(None, wake, word).ratio()
                    if similarity >= 0.92:  # raised from 0.90
                        logger.debug(f"Fuzzy matched: '{word}' (similarity: {similarity:.2f})")
                        return True

        return False

    # ------------------------------------------------------------------ #
    #  Health logging
    # ------------------------------------------------------------------ #

    def _log_health(self):
        """Log health stats every 5 minutes."""
        now = time.time()
        if now - self._last_health_log < 300:
            return
        self._last_health_log = now
        logger.info(
            f"[VOSK WATCHDOG HEALTH] frames_processed={self._total_frames_processed}, "
            f"restarts={self._restart_count}, paused={self.is_paused}"
        )

    # ------------------------------------------------------------------ #
    #  Supervisor (watchdog) loop
    # ------------------------------------------------------------------ #

    def _supervisor_loop(self):
        """
        Supervisor that keeps _detection_loop alive.
        Handles crashes from PyAudio buffer overflows, driver resets, etc.
        """
        while self.is_running:
            try:
                self._detection_loop()
            except Exception as e:
                if not self.is_running:
                    break

                self._restart_count += 1
                now = time.time()
                self._restart_timestamps.append(now)
                self._restart_timestamps = [
                    t for t in self._restart_timestamps if now - t < _RAPID_RESTART_WINDOW
                ]

                logger.error(
                    f"[VOSK WATCHDOG] Detection loop crashed (restart #{self._restart_count}): {e}",
                    exc_info=True,
                )

                self._cleanup_audio()

                rapid_count = len(self._restart_timestamps)
                if rapid_count >= _MAX_RAPID_RESTARTS:
                    backoff = min(30, 2 ** (rapid_count - _MAX_RAPID_RESTARTS + 1))
                    logger.warning(
                        f"[VOSK WATCHDOG] {rapid_count} restarts in {_RAPID_RESTART_WINDOW}s — "
                        f"backing off {backoff}s"
                    )
                    time.sleep(backoff)
                else:
                    time.sleep(2)

                if self.is_running:
                    logger.info("[VOSK WATCHDOG] Restarting detection loop...")

        logger.info("[VOSK WATCHDOG] Supervisor exited")

    # ------------------------------------------------------------------ #
    #  Core detection loop
    # ------------------------------------------------------------------ #

    def _detection_loop(self):
        """Main detection loop — runs inside _supervisor_loop."""
        # Load model
        self._load_model()

        # Initialize audio — fresh PyAudio on every (re)start
        self.audio = pyaudio.PyAudio()
        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=4000,
        )
        self.stream.start_stream()

        logger.info("Wake word detection loop started")
        self._last_health_log = time.time()
        consecutive_errors = 0

        while self.is_running:
            try:
                if self.is_paused:
                    time.sleep(0.1)
                    continue

                data = self.stream.read(4000, exception_on_overflow=False)
                self._total_frames_processed += 1

                # Energy gate
                if not self._check_audio_energy(data):
                    continue

                # Process with Vosk — ONLY use final results (not partials)
                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    text = result.get("text", "").lower()

                    if text:
                        logger.debug(f"Wake word: Heard: '{text}'")

                        if self._is_wake_word_match(text):
                            if not self._should_process_detection():
                                continue

                            logger.info(f"[VOSK CONFIRMED] Wake word detected: '{text}'")
                            self.last_detection_time = time.time()
                            self._on_wake_word_detected()

                # Periodic health log
                self._log_health()
                consecutive_errors = 0

            except IOError as e:
                consecutive_errors += 1
                if consecutive_errors <= 3:
                    logger.debug(f"Vosk audio I/O hiccup (#{consecutive_errors}): {e}")
                    time.sleep(0.05)
                else:
                    logger.warning(f"Too many consecutive Vosk I/O errors ({consecutive_errors})")
                    raise
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Wake word detection error: {e}")
                if consecutive_errors > 10:
                    raise
                time.sleep(0.3)

    # ------------------------------------------------------------------ #
    #  Wake word callback
    # ------------------------------------------------------------------ #

    def _on_wake_word_detected(self):
        """Handle wake word detection — thread-safe."""
        try:
            self.pause()

            if self.on_wake_word:
                self.on_wake_word()

        except Exception as e:
            logger.error(f"Error handling wake word: {e}")


# ------------------------------------------------------------------ #
#  Global singleton
# ------------------------------------------------------------------ #

_wake_word_detector: Optional[WakeWordDetector] = None


def get_wake_word_detector(on_wake_word: Optional[Callable] = None) -> WakeWordDetector:
    """Get or create global wake word detector"""
    global _wake_word_detector
    if _wake_word_detector is None:
        _wake_word_detector = WakeWordDetector(on_wake_word)
    return _wake_word_detector
