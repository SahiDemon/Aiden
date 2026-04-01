"""
Porcupine Wake Word Detection System
High-accuracy, low-latency wake word detection using Picovoice Porcupine

Includes:
- Auto-restart watchdog (survives PyAudio / driver crashes)
- AGC applied *before* energy gating (quiet speech isn't thrown away)
- Thread-safe sound playback (no asyncio.run from bg thread)
"""
import asyncio
import logging
import os
import struct
import threading
import time
from typing import Callable, Optional
import numpy as np
import pvporcupine
from pvporcupine._porcupine import (
    PorcupineActivationError,
    PorcupineActivationLimitError,
    PorcupineActivationRefusedError,
    PorcupineActivationThrottledError,
)
import pyaudio

from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Errors that will NEVER resolve by retrying (bad key, quota exhausted, etc.)
_PERMANENT_ERRORS = (
    PorcupineActivationError,
    PorcupineActivationLimitError,
    PorcupineActivationRefusedError,
    PorcupineActivationThrottledError,
    ValueError,  # missing access key
)

# Maximum consecutive rapid restarts before backing off
_MAX_RAPID_RESTARTS = 5
_RAPID_RESTART_WINDOW = 60  # seconds


class PorcupineWakeWordDetector:
    """
    Wake word detector using Porcupine
    Optimized for accuracy and speed with audio pre-processing.

    Key design decisions
    --------------------
    * A *watchdog supervisor* wraps the detection loop so that transient
      PyAudio / OS-driver errors don't permanently kill listening.
    * AGC is applied **before** the energy gate – quiet speech gets boosted
      first, then evaluated.
    * Sound playback from the background thread uses its own throwaway
      asyncio loop in a dedicated thread to avoid corrupting the main loop.
    """

    def __init__(self, on_wake_word: Optional[Callable] = None,
                 on_permanent_failure: Optional[Callable] = None):
        self.settings = get_settings()
        self.on_wake_word = on_wake_word
        self.on_permanent_failure = on_permanent_failure

        # Porcupine configuration
        self.access_key = self.settings.speech.porcupine_access_key
        self.model_path = self.settings.speech.porcupine_model_path
        self.sensitivity = self.settings.speech.porcupine_sensitivity

        # Porcupine instance (created inside the detection thread)
        self.porcupine = None

        # Audio settings (created inside the detection thread)
        self.audio = None
        self.stream = None
        self.sample_rate = 16000
        self.frame_length = 512  # Porcupine requirement

        # Audio processing – AGC
        self.noise_floor = 0
        self.noise_floor_samples = []
        self.max_noise_samples = 100
        self.agc_target_level = 0.35
        self.agc_current_gain = 1.0
        self.agc_max_gain = 6.0  # Boosted from 4.0 → 6.0 so quiet voices are amplified more

        # False positive prevention
        self.min_audio_energy = self.settings.speech.porcupine_min_energy
        self.debounce_time = self.settings.speech.porcupine_debounce_seconds
        self.last_detection_time = 0
        self.confirmation_window = self.settings.speech.porcupine_confirmation_window
        self.recent_detections = []

        # Control flags
        self.is_running = False
        self.is_paused = False
        self._permanent_failure = False  # Set when error is non-recoverable
        self._thread = None

        # Startup readiness: set once _detection_loop processes its first frame
        self._ready_event = threading.Event()
        self._init_error: Optional[Exception] = None

        # Watchdog health stats
        self._restart_count = 0
        self._restart_timestamps: list[float] = []
        self._total_frames_processed = 0
        self._last_health_log = 0.0

        logger.info(
            f"Porcupine Wake Word Detector initialized: sensitivity={self.sensitivity}, "
            f"min_energy={self.min_audio_energy}, debounce={self.debounce_time}s, "
            f"agc_max_gain={self.agc_max_gain}"
        )

    # ------------------------------------------------------------------ #
    #  Porcupine initialisation
    # ------------------------------------------------------------------ #

    def _initialize_porcupine(self):
        """Initialize Porcupine engine"""
        try:
            if not self.access_key:
                raise ValueError("Porcupine AccessKey not provided. Set SPEECH_PORCUPINE_ACCESS_KEY in .env")

            keyword_paths = None
            if os.path.exists(self.model_path):
                keyword_paths = [self.model_path]
                logger.info(f"Using custom wake word model: {self.model_path}")
            else:
                logger.warning(f"Custom model not found at {self.model_path}, will use built-in keywords")

            if keyword_paths:
                self.porcupine = pvporcupine.create(
                    access_key=self.access_key,
                    keyword_paths=keyword_paths,
                    sensitivities=[self.sensitivity],
                )
            else:
                self.porcupine = pvporcupine.create(
                    access_key=self.access_key,
                    keywords=["computer"],
                    sensitivities=[self.sensitivity],
                )
                logger.warning("Using built-in 'computer' keyword as fallback. Create custom 'aiden' model in Picovoice Console.")

            self.sample_rate = self.porcupine.sample_rate
            self.frame_length = self.porcupine.frame_length
            logger.info(f"Porcupine initialized: sample_rate={self.sample_rate}, frame_length={self.frame_length}")

        except _PERMANENT_ERRORS as e:
            # These errors will NEVER resolve by retrying
            error_msg = str(e)
            logger.error(f"Failed to initialize Porcupine (PERMANENT): {error_msg}")
            self._permanent_failure = True
            self._init_error = e
            self._ready_event.set()  # Unblock anyone waiting

            if isinstance(e, (PorcupineActivationLimitError, PorcupineActivationRefusedError)):
                logger.error("=" * 80)
                logger.error("PORCUPINE ACCESS KEY EXHAUSTED / REFUSED!")
                logger.error("Your free-tier Picovoice key has hit its limit.")
                logger.error("Options:")
                logger.error("  1. Get a new key at https://console.picovoice.ai/")
                logger.error("  2. Set SPEECH_USE_PORCUPINE=false in .env to use Vosk")
                logger.error("Will auto-fallback to Vosk now.")
                logger.error("=" * 80)

            if "different version" in error_msg or "4.0.0" in error_msg or "3.0.0" in error_msg:
                logger.error("=" * 80)
                logger.error("PORCUPINE VERSION MISMATCH!")
                logger.error("Your model file version doesn't match the library version.")
                logger.error("Quick Fix: Run .\\fix_porcupine_version.ps1")
                logger.error("Or set SPEECH_USE_PORCUPINE=false in .env")
                logger.error("=" * 80)
            raise

        except Exception as e:
            logger.error(f"Failed to initialize Porcupine: {e}")
            self._init_error = e
            self._ready_event.set()
            raise

    # ------------------------------------------------------------------ #
    #  Audio processing helpers
    # ------------------------------------------------------------------ #

    def _apply_agc(self, audio_data: np.ndarray) -> np.ndarray:
        """
        Apply Automatic Gain Control to normalize audio levels.
        Called BEFORE the energy gate so that quiet speech gets boosted.
        """
        current_level = np.max(np.abs(audio_data)) / 32768.0

        if current_level > 0.005:  # Lowered from 0.01 – catch quieter signals
            desired_gain = self.agc_target_level / current_level
            # Smooth gain changes
            self.agc_current_gain = 0.85 * self.agc_current_gain + 0.15 * desired_gain
            # Wider gain range for quiet environments
            self.agc_current_gain = np.clip(self.agc_current_gain, 0.5, self.agc_max_gain)
            audio_data = np.clip(audio_data * self.agc_current_gain, -32768, 32767).astype(np.int16)

        return audio_data

    def _update_noise_floor(self, audio_data: np.ndarray):
        """Update noise floor estimate for varying environments."""
        rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))
        self.noise_floor_samples.append(rms)

        if len(self.noise_floor_samples) > self.max_noise_samples:
            self.noise_floor_samples.pop(0)

        if len(self.noise_floor_samples) >= 10:
            self.noise_floor = np.percentile(self.noise_floor_samples, 25)

    def _is_audio_above_threshold(self, audio_data: np.ndarray) -> bool:
        """
        Check if audio contains potential speech (post-AGC).
        Uses the configured min_energy as the gate.
        """
        rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))
        return rms > self.min_audio_energy

    def _should_process_detection(self) -> bool:
        """Debounce: avoid rapid re-triggers."""
        if self.last_detection_time == 0:
            return True
        elapsed = time.time() - self.last_detection_time
        if elapsed < self.debounce_time:
            logger.debug(f"Debouncing detection ({elapsed:.2f}s < {self.debounce_time}s)")
            return False
        return True

    def _add_detection_to_confirmation_window(self, confidence: float = 1.0) -> bool:
        """Sliding window confirmation to weed out random spikes."""
        now = time.time()
        self.recent_detections.append({"time": now, "confidence": confidence})
        self.recent_detections = [d for d in self.recent_detections if now - d["time"] <= self.confirmation_window]

        if self.confirmation_window <= 0.3:
            return True  # Single-detection mode

        if len(self.recent_detections) >= 2:
            logger.debug(f"Confirmation: {len(self.recent_detections)} detections in {self.confirmation_window}s")
            return True

        logger.debug(f"Waiting for confirmation: {len(self.recent_detections)}/2 in window")
        return False

    # ------------------------------------------------------------------ #
    #  Health & diagnostics
    # ------------------------------------------------------------------ #

    def _log_health(self):
        """Log health stats every 5 minutes."""
        now = time.time()
        if now - self._last_health_log < 300:
            return
        self._last_health_log = now
        logger.info(
            f"[WATCHDOG HEALTH] frames_processed={self._total_frames_processed}, "
            f"restarts={self._restart_count}, paused={self.is_paused}, "
            f"agc_gain={self.agc_current_gain:.2f}, noise_floor={self.noise_floor:.0f}"
        )

    # ------------------------------------------------------------------ #
    #  Start / Stop / Pause / Resume
    # ------------------------------------------------------------------ #

    def start(self):
        """Start wake word detection in a supervised background thread."""
        if self.is_running:
            logger.warning("Porcupine wake word detector already running")
            return

        logger.info("Starting Porcupine wake word detector...")
        self.is_running = True
        self._permanent_failure = False
        self._ready_event.clear()
        self._init_error = None
        self._thread = threading.Thread(target=self._supervisor_loop, daemon=True, name="porcupine-watchdog")
        self._thread.start()
        logger.info("Porcupine wake word detector started (with watchdog)")

    def wait_until_ready(self, timeout: float = 5.0) -> bool:
        """
        Block until the detector has either started successfully or
        hit a permanent failure.  Returns True if running, False if failed.
        """
        self._ready_event.wait(timeout=timeout)
        return not self._permanent_failure

    @property
    def permanently_failed(self) -> bool:
        return self._permanent_failure

    def stop(self):
        """Stop wake word detection."""
        logger.info("Stopping Porcupine wake word detector...")
        self.is_running = False

        if self._thread:
            self._thread.join(timeout=3.0)

        self._cleanup_audio()
        logger.info(f"Porcupine wake word detector stopped (total restarts: {self._restart_count})")

    def pause(self):
        """Pause wake word detection (during conversation)."""
        logger.debug("Porcupine wake word detector paused")
        self.is_paused = True

    def resume(self):
        """Resume wake word detection."""
        logger.debug("Porcupine wake word detector resumed")
        self.is_paused = False

    # ------------------------------------------------------------------ #
    #  Resource cleanup
    # ------------------------------------------------------------------ #

    def _cleanup_audio(self):
        """Safely tear down PyAudio + Porcupine resources."""
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

        if self.porcupine:
            try:
                self.porcupine.delete()
            except Exception:
                pass
            self.porcupine = None

    # ------------------------------------------------------------------ #
    #  Supervisor (watchdog) loop
    # ------------------------------------------------------------------ #

    def _supervisor_loop(self):
        """
        Supervisor that keeps _detection_loop alive.
        Permanent errors (activation limit, bad key) cause immediate exit
        and trigger the on_permanent_failure callback so main.py can
        fallback to Vosk.
        """
        while self.is_running:
            try:
                self._detection_loop()
            except Exception as e:
                if not self.is_running:
                    break  # Intentional shutdown

                # *** PERMANENT FAILURE — stop retrying ***
                if self._permanent_failure:
                    logger.error(
                        f"[WATCHDOG] Porcupine hit a PERMANENT error — stopping retries: {e}"
                    )
                    self.is_running = False
                    self._cleanup_audio()
                    # Notify main.py so it can fallback to Vosk
                    if self.on_permanent_failure:
                        try:
                            self.on_permanent_failure(e)
                        except Exception as cb_err:
                            logger.error(f"[WATCHDOG] Failure callback error: {cb_err}")
                    break

                # Transient error — restart
                self._restart_count += 1
                now = time.time()
                self._restart_timestamps.append(now)
                self._restart_timestamps = [
                    t for t in self._restart_timestamps if now - t < _RAPID_RESTART_WINDOW
                ]

                logger.error(
                    f"[WATCHDOG] Detection loop crashed (restart #{self._restart_count}): {e}",
                    exc_info=True,
                )

                self._cleanup_audio()

                rapid_count = len(self._restart_timestamps)
                if rapid_count >= _MAX_RAPID_RESTARTS:
                    backoff = min(30, 2 ** (rapid_count - _MAX_RAPID_RESTARTS + 1))
                    logger.warning(
                        f"[WATCHDOG] {rapid_count} restarts in {_RAPID_RESTART_WINDOW}s — "
                        f"backing off {backoff}s"
                    )
                    time.sleep(backoff)
                else:
                    time.sleep(2)

                if self.is_running:
                    logger.info("[WATCHDOG] Restarting detection loop...")

        logger.info("[WATCHDOG] Supervisor exited")

    # ------------------------------------------------------------------ #
    #  Core detection loop
    # ------------------------------------------------------------------ #

    def _detection_loop(self):
        """
        Main detection loop.  Runs inside _supervisor_loop so any
        unhandled exception triggers a clean restart rather than
        silent death.
        """
        # Initialize Porcupine
        self._initialize_porcupine()

        # Initialize audio — fresh PyAudio instance on every (re)start
        self.audio = pyaudio.PyAudio()
        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.frame_length,
        )
        self.stream.start_stream()

        logger.info("Porcupine detection loop started")
        self._last_health_log = time.time()

        # Signal readiness — Porcupine + audio are up
        self._ready_event.set()

        consecutive_errors = 0

        while self.is_running:
            try:
                if self.is_paused:
                    time.sleep(0.1)
                    continue

                # Read audio data
                pcm = self.stream.read(self.frame_length, exception_on_overflow=False)
                audio_frame = np.frombuffer(pcm, dtype=np.int16)

                self._total_frames_processed += 1

                # Update noise floor estimate (on raw audio)
                self._update_noise_floor(audio_frame)

                # *** KEY FIX: Apply AGC *before* energy gate ***
                # This ensures quiet speech gets boosted before we decide
                # whether the frame is worth sending to Porcupine.
                audio_frame = self._apply_agc(audio_frame)

                # Energy gate (post-AGC) – filters digital silence only
                if not self._is_audio_above_threshold(audio_frame):
                    continue

                # Process with Porcupine
                keyword_index = self.porcupine.process(audio_frame)

                if keyword_index >= 0:
                    logger.debug(f"[PORCUPINE RAW DETECTION] keyword_index={keyword_index}")

                    if not self._should_process_detection():
                        logger.debug("Detection debounced")
                        continue

                    if self._add_detection_to_confirmation_window():
                        logger.info(f"[PORCUPINE CONFIRMED] Wake word detected (keyword_index={keyword_index})")
                        self.last_detection_time = time.time()
                        self.recent_detections.clear()
                        self._on_wake_word_detected()

                # Periodic health log
                self._log_health()

                # Reset consecutive error counter on successful frame
                consecutive_errors = 0

            except IOError as e:
                # PyAudio buffer overflow / underflow — common, recoverable
                consecutive_errors += 1
                if consecutive_errors <= 3:
                    logger.debug(f"Audio I/O hiccup (#{consecutive_errors}): {e}")
                    time.sleep(0.05)
                else:
                    # Too many consecutive I/O errors — let supervisor restart
                    logger.warning(f"Too many consecutive audio I/O errors ({consecutive_errors}), raising for restart")
                    raise
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Porcupine detection error: {e}")
                if consecutive_errors > 10:
                    logger.error("Too many consecutive errors — raising for watchdog restart")
                    raise
                time.sleep(0.3)

    # ------------------------------------------------------------------ #
    #  Wake word callback
    # ------------------------------------------------------------------ #

    def _on_wake_word_detected(self):
        """Handle wake word detection — thread-safe."""
        try:
            # Play activation sound in a dedicated thread to avoid
            # asyncio.run() conflicts with the main event loop.
            sound_thread = threading.Thread(
                target=self._play_activation_sound_sync,
                daemon=True,
                name="wake-sound",
            )
            sound_thread.start()
            sound_thread.join(timeout=3.0)  # Don't wait forever

            # Pause detection during interaction
            self.pause()

            # Trigger callback
            if self.on_wake_word:
                self.on_wake_word()

        except Exception as e:
            logger.error(f"Error handling wake word: {e}")

    def _play_activation_sound_sync(self):
        """
        Play wake word acknowledgment sound.
        Runs in its own thread with a throwaway event loop to avoid
        interfering with the main asyncio loop.
        """
        try:
            import random
            loop = asyncio.new_event_loop()
            try:
                from src.speech.tts import get_tts_engine
                tts = get_tts_engine()
                sound_name = random.choice(["mmm1", "mmm2"])
                loop.run_until_complete(tts.play_sound(sound_name))
                logger.debug(f"Played wake word acknowledgment sound: {sound_name}")
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Error playing wake word acknowledgment: {e}")


# ------------------------------------------------------------------ #
#  Global singleton
# ------------------------------------------------------------------ #

_porcupine_detector: Optional[PorcupineWakeWordDetector] = None


def get_porcupine_detector(
    on_wake_word: Optional[Callable] = None,
    on_permanent_failure: Optional[Callable] = None,
) -> PorcupineWakeWordDetector:
    """Get or create global Porcupine wake word detector"""
    global _porcupine_detector
    if _porcupine_detector is None:
        _porcupine_detector = PorcupineWakeWordDetector(on_wake_word, on_permanent_failure)
    return _porcupine_detector
