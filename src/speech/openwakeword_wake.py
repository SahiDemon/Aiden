"""
openWakeWord Wake Word Detection System
Replacement for Porcupine — fully open-source, no API key required.

Key advantages over Porcupine:
- Built-in Silero VAD gating → dramatically fewer false positives
- No API key or licence required
- Custom models trainable in ~1hr on free Google Colab
- Apache 2.0 licence

Architecture:
  PyAudio mic → 80ms frames → openWakeWord.predict()
                                   └─ Silero VAD gate (vad_threshold)
                                   └─ score ≥ activation_threshold?
                                         └─ YES → callback → debounce
"""

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pyaudio

from src.utils.config import get_settings
from src.utils.logger import get_logger
from src.utils.paths import resource_path

logger = get_logger(__name__)

# openWakeWord chunk size: must be 80 ms of 16 kHz mono → 1 280 samples
_SAMPLE_RATE = 16_000
_FRAME_MS = 80
_FRAME_SAMPLES = int(_SAMPLE_RATE * _FRAME_MS / 1000)  # 1 280
_FORMAT = pyaudio.paInt16
_CHANNELS = 1

# Supervisor constants
_MAX_RAPID_RESTARTS = 5
_RAPID_RESTART_WINDOW = 60  # seconds


class OpenWakeWordDetector:
    """
    Wake-word detector backed by openWakeWord (ONNX, CPU).

    Parameters controlled via SpeechConfig:
      oww_model_path          – path to .tflite or .onnx model file
                                (leave blank to use a pre-trained built-in model)
      oww_threshold           – activation score threshold  (default 0.5)
      oww_vad_threshold       – Silero VAD gate; 0 = disabled, 0.5 = balanced
      porcupine_debounce_seconds – reused for debounce timing
      porcupine_min_energy    – reused as a lightweight RMS energy pre-gate
    """

    def __init__(self, callback: Callable[[], None]):
        self.callback = callback
        cfg = get_settings().speech

        # Resolve the model path via resource_path() so it works correctly
        # both when running from source AND from a PyInstaller EXE bundle
        # (where the CWD may differ from the EXE's directory).
        raw_model_path: str = getattr(cfg, "oww_model_path", "")
        if raw_model_path:
            p = Path(raw_model_path)
            self.model_path = str(
                p if p.is_absolute() else resource_path(*p.parts)
            )
        else:
            self.model_path = ""
        self.threshold: float = getattr(cfg, "oww_threshold", 0.5)
        self.vad_threshold: float = getattr(cfg, "oww_vad_threshold", 0.3)
        self.debounce: float = cfg.porcupine_debounce_seconds
        self.min_energy: float = cfg.porcupine_min_energy

        self._oww_model = None
        self._pa: Optional[pyaudio.PyAudio] = None
        self._stream: Optional[pyaudio.Stream] = None

        self._running = False
        self._paused = False
        self._lock = threading.Lock()

        self._last_trigger_time: float = 0.0

        self._thread: Optional[threading.Thread] = None

        logger.info(
            "OpenWakeWord detector configured: threshold=%.2f, vad_threshold=%.2f, "
            "debounce=%.1fs, min_energy=%.0f",
            self.threshold,
            self.vad_threshold,
            self.debounce,
            self.min_energy,
        )

    # ------------------------------------------------------------------
    # Public API (mirrors PorcupineWakeWordDetector)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the detector in a background supervisor thread."""
        self._running = True
        self._thread = threading.Thread(
            target=self._supervisor_loop, name="oww-supervisor", daemon=True
        )
        self._thread.start()
        logger.info("OpenWakeWord detector started (with watchdog)")

    def stop(self) -> None:
        """Gracefully stop the detector."""
        self._running = False
        self._cleanup()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info("OpenWakeWord detector stopped")

    def pause(self) -> None:
        with self._lock:
            self._paused = True
            # Reset debounce so the same utterance can't re-fire after resume.
            self._last_trigger_time = time.monotonic()

    def resume(self) -> None:
        with self._lock:
            self._paused = False
            # Clear the model's internal prediction buffer so stale high-score
            # frames from the previous wake-word utterance don't immediately
            # retrigger detection as soon as we start processing again.
            if self._oww_model is not None:
                try:
                    self._oww_model.reset()
                except Exception:
                    pass  # Older OWW versions may not have reset(); safe to ignore
            # Also keep debounce active for a brief window after resume so any
            # residual echo in the audio buffer is ignored.
            self._last_trigger_time = time.monotonic()

    @property
    def is_running(self) -> bool:
        return self._running and (self._thread is not None) and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """Import and initialise the openWakeWord Model."""
        try:
            from openwakeword.model import Model  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "openwakeword is not installed. "
                "Run: pip install openwakeword"
            ) from exc

        if self.model_path:
            logger.info("OpenWakeWord: loading custom model from %s", self.model_path)
            self._oww_model = Model(
                wakeword_models=[self.model_path],
                vad_threshold=self.vad_threshold,
                inference_framework="onnx",
            )
        else:
            # Fall back to pre-trained models bundled with openWakeWord
            logger.info(
                "OpenWakeWord: no custom model path set — downloading/using "
                "pre-trained models (hey_jarvis, hey_mycroft, alexa, etc.)"
            )
            try:
                import openwakeword  # type: ignore[import-untyped]
                openwakeword.utils.download_models()
            except Exception as e:
                logger.warning("OpenWakeWord: could not download models: %s", e)
            self._oww_model = Model(
                vad_threshold=self.vad_threshold,
                inference_framework="onnx",
            )

        logger.info("OpenWakeWord: model loaded OK — labels: %s", list(self._oww_model.models.keys()))

    def _open_stream(self) -> None:
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(
            rate=_SAMPLE_RATE,
            channels=_CHANNELS,
            format=_FORMAT,
            input=True,
            frames_per_buffer=_FRAME_SAMPLES,
        )
        logger.info("OpenWakeWord: audio stream opened (%d Hz, %d ms frames)", _SAMPLE_RATE, _FRAME_MS)

    def _cleanup(self) -> None:
        try:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
        except Exception:
            pass
        finally:
            self._stream = None

        try:
            if self._pa:
                self._pa.terminate()
        except Exception:
            pass
        finally:
            self._pa = None

    def _supervisor_loop(self) -> None:
        restart_times: list[float] = []

        while self._running:
            try:
                self._detection_loop()
            except Exception as exc:
                if not self._running:
                    break

                now = time.monotonic()
                restart_times = [t for t in restart_times if now - t < _RAPID_RESTART_WINDOW]
                restart_times.append(now)
                n = len(restart_times)

                logger.error(
                    "[WATCHDOG] OpenWakeWord detection loop crashed (restart #%d): %s",
                    n, exc, exc_info=True,
                )
                self._cleanup()

                if n > _MAX_RAPID_RESTARTS:
                    backoff = min(2 ** (n - _MAX_RAPID_RESTARTS), 60)
                    logger.warning("[WATCHDOG] %d restarts in %ds — backing off %ds", n, _RAPID_RESTART_WINDOW, backoff)
                    time.sleep(backoff)
                else:
                    time.sleep(1.0)

                if self._running:
                    logger.info("[WATCHDOG] Restarting OpenWakeWord detection loop...")

    def _detection_loop(self) -> None:
        self._load_model()
        self._open_stream()

        logger.info("OpenWakeWord: listening for wake word…")

        while self._running:
            with self._lock:
                paused = self._paused
            
            if paused:
                if self._stream is not None:
                    logger.info("OpenWakeWord: detector paused — releasing microphone resources")
                    self._cleanup()
                time.sleep(0.1)
                continue

            if self._stream is None:
                logger.info("OpenWakeWord: detector resumed — opening microphone stream")
                try:
                    self._open_stream()
                    if self._oww_model is not None:
                        try:
                            self._oww_model.reset()
                        except Exception:
                            pass
                    self._last_trigger_time = time.monotonic()
                except Exception as exc:
                    logger.error("OpenWakeWord: failed to re-open stream on resume: %s", exc)
                    time.sleep(1.0)
                    continue

            try:
                raw = self._stream.read(_FRAME_SAMPLES, exception_on_overflow=False)
            except Exception as e:
                logger.warning("OpenWakeWord: stream read error: %s", e)
                raise  # let watchdog restart

            audio = np.frombuffer(raw, dtype=np.int16)

            # Lightweight RMS energy pre-gate (same concept as Porcupine's min_energy)
            if self.min_energy > 0:
                rms = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
                if rms < self.min_energy:
                    continue

            # Run openWakeWord inference (includes Silero VAD internally)
            predictions = self._oww_model.predict(audio)

            # Check if any model exceeded threshold
            for model_name, score in predictions.items():
                if score >= self.threshold:
                    now = time.monotonic()
                    if now - self._last_trigger_time < self.debounce:
                        logger.debug(
                            "OpenWakeWord: debounced trigger (%.2f < %.2f debounce)",
                            now - self._last_trigger_time, self.debounce,
                        )
                        break

                    self._last_trigger_time = now
                    logger.info(
                        "OpenWakeWord: WAKE WORD detected! model=%s score=%.3f",
                        model_name, score,
                    )
                    try:
                        self.callback()
                    except Exception as cb_exc:
                        logger.error("OpenWakeWord: callback error: %s", cb_exc)
                    break  # one trigger per frame
