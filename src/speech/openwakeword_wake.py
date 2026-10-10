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

import collections
import json
import pickle
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pyaudio

from src.speech.audio_devices import resolve_input_device_index
from src.speech.wake_detection import WakeDetection
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
      input_device_name       – stable microphone name substring
    """

    def __init__(self, callback: Callable[[WakeDetection], None]):
        self.callback = callback
        cfg = get_settings().speech

        profile = self._load_profile(getattr(cfg, "oww_profile_path", ""))
        self._legacy_threshold = float(getattr(cfg, "oww_threshold", 0.5))
        self._legacy_vad_threshold = float(getattr(cfg, "oww_vad_threshold", 0.3))

        # Resolve the model path via resource_path() so it works correctly
        # both when running from source AND from a PyInstaller EXE bundle
        # (where the CWD may differ from the EXE's directory).
        raw_model_path: str = str(profile.get("model_path") or getattr(cfg, "oww_model_path", ""))
        if raw_model_path:
            p = Path(raw_model_path)
            self.model_path = str(
                p if p.is_absolute() else resource_path(*p.parts)
            )
        else:
            self.model_path = ""
        self.threshold = float(profile.get("threshold", self._legacy_threshold))
        self.vad_threshold = float(profile.get("vad_threshold", self._legacy_vad_threshold))
        self.strong_threshold = float(
            profile.get("strong_threshold", getattr(cfg, "oww_strong_threshold", 0.75))
        )
        self.base_rescue_threshold = float(
            profile.get("base_rescue_threshold", getattr(cfg, "oww_base_rescue_threshold", 1.0))
        )
        self.smoothing_window = max(
            1,
            int(profile.get("smoothing_window", getattr(cfg, "oww_smoothing_window", 3))),
        )
        self.smoothing_hits = min(
            self.smoothing_window,
            max(1, int(profile.get("smoothing_hits", getattr(cfg, "oww_smoothing_hits", 2)))),
        )
        self.verifier_gate = float(
            profile.get("verifier_gate", getattr(cfg, "oww_verifier_gate", 0.25))
        )
        raw_verifier_path = str(
            profile.get("verifier_path") or getattr(cfg, "oww_verifier_path", "")
        )
        self.verifier_path = self._resolve_optional_path(raw_verifier_path)
        self.input_device_name = str(
            profile.get("input_device_name") or getattr(cfg, "input_device_name", "")
        )
        self.continuation_window_ms = max(
            0,
            int(getattr(cfg, "oww_continuation_window_ms", 300)),
        )
        self.shadow_mode = bool(getattr(cfg, "oww_shadow_mode", False))
        self.capture_diagnostics = bool(getattr(cfg, "oww_capture_diagnostics", False))
        if not self.verifier_path and not profile:
            # Preserve legacy one-frame activation until a calibrated v2
            # profile and personal verifier are available.
            self.smoothing_window = 1
            self.smoothing_hits = 1
        self.debounce: float = cfg.porcupine_debounce_seconds

        self._oww_model = None
        self._verifier_model = None
        self._pa: Optional[pyaudio.PyAudio] = None
        self._stream: Optional[pyaudio.Stream] = None
        self._device_index: Optional[int] = None

        self._running = False
        self._paused = False
        self._lock = threading.Lock()

        self._last_trigger_time: float = 0.0
        self._last_metric_time: float = 0.0
        self._noise_rms: float = 30.0
        self._score_history: dict[str, collections.deque[float]] = {}
        self._audio_history: collections.deque[bytes] = collections.deque(
            maxlen=max(8, int(1_600 / _FRAME_MS))
        )
        self._ready_event = threading.Event()
        self._stream_released = threading.Event()
        self._stream_released.set()
        self._startup_error: Optional[str] = None

        self._thread: Optional[threading.Thread] = None

        logger.info(
            "OpenWakeWord detector configured: threshold=%.2f, strong=%.2f, "
            "vad_threshold=%.2f, verifier=%s, smoothing=%d/%d, shadow=%s",
            self.threshold,
            self.strong_threshold,
            self.vad_threshold,
            "enabled" if self.verifier_path else "disabled",
            self.smoothing_hits,
            self.smoothing_window,
            self.shadow_mode,
        )

    @staticmethod
    def _resolve_optional_path(raw_path: str) -> str:
        if not raw_path:
            return ""
        path = Path(raw_path)
        return str(path if path.is_absolute() else resource_path(*path.parts))

    @classmethod
    def _load_profile(cls, raw_path: str) -> dict:
        """Load an optional calibrated profile, leaving legacy settings intact."""
        path_text = (raw_path or "").strip()
        if not path_text:
            return {}
        path = Path(path_text)
        path = path if path.is_absolute() else resource_path(*path.parts)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("profile root must be an object")
            for key in (
                "threshold",
                "strong_threshold",
                "vad_threshold",
                "verifier_gate",
                "base_rescue_threshold",
            ):
                if key in data and not 0.0 <= float(data[key]) <= 1.0:
                    raise ValueError(f"{key} must be between 0 and 1")
            for key in ("smoothing_window", "smoothing_hits"):
                if key in data and int(data[key]) < 1:
                    raise ValueError(f"{key} must be positive")
            if (
                "threshold" in data
                and "strong_threshold" in data
                and float(data["strong_threshold"]) < float(data["threshold"])
            ):
                raise ValueError("strong_threshold must not be below threshold")
            logger.info("OpenWakeWord: loaded calibration profile from %s", path)
            return data
        except Exception as exc:
            logger.warning("OpenWakeWord: ignoring invalid profile %s: %s", path, exc)
            return {}

    # ------------------------------------------------------------------
    # Public API (mirrors PorcupineWakeWordDetector)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the detector in a background supervisor thread."""
        self._startup_error = None
        self._ready_event.clear()
        self._running = True
        self._thread = threading.Thread(
            target=self._supervisor_loop, name="oww-supervisor", daemon=True
        )
        self._thread.start()
        logger.info("OpenWakeWord detector started (with watchdog)")

    def wait_until_ready(self, timeout: float = 10.0) -> bool:
        """Wait until both the model and selected microphone are ready."""
        return self._ready_event.wait(timeout) and self._startup_error is None

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
            # STT must not reopen this device before this detector closes its
            # PortAudio stream, especially after a long idle period.
            if self._stream is not None:
                self._stream_released.clear()
            else:
                self._stream_released.set()
            # Reset debounce so the same utterance can't re-fire after resume.
            self._last_trigger_time = time.monotonic()

    def wait_until_stream_released(self, timeout: float = 0.5) -> bool:
        """Wait for the paused detector to release its microphone stream."""
        return self._stream_released.wait(timeout)

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
            requested_model = Path(self.model_path)
            fallback_model = resource_path("vosk_models", "hey_aiden.onnx")
            if not requested_model.exists():
                if fallback_model.exists():
                    logger.error(
                        "OpenWakeWord: model %s is missing; rolling back to %s",
                        requested_model,
                        fallback_model,
                    )
                    self._use_rollback_settings(fallback_model)
                else:
                    raise FileNotFoundError(f"Wake-word model not found: {requested_model}")

            if Path(self.model_path).stem == "aiden_v2" and not self.verifier_path:
                logger.error(
                    "OpenWakeWord: aiden_v2 requires its personal verifier; using rollback model"
                )
                if fallback_model.exists():
                    self._use_rollback_settings(fallback_model)
                else:
                    raise FileNotFoundError(
                        "aiden_v2 verifier is not configured and rollback model is missing"
                    )

            model_kwargs = {
                "wakeword_models": [self.model_path],
                "vad_threshold": self.vad_threshold,
                "inference_framework": "onnx",
            }
            if self.verifier_path:
                verifier = Path(self.verifier_path)
                if verifier.exists():
                    try:
                        # Load the same sklearn pipeline openWakeWord uses, but
                        # apply it explicitly so diagnostics retain both the
                        # base and personal-verifier scores.
                        with verifier.open("rb") as verifier_file:
                            self._verifier_model = pickle.load(verifier_file)
                    except Exception:
                        logger.exception(
                            "OpenWakeWord: personal verifier failed to load; using rollback model"
                        )
                        if fallback_model.exists():
                            self._use_rollback_settings(fallback_model)
                            model_kwargs["wakeword_models"] = [self.model_path]
                            model_kwargs["vad_threshold"] = self.vad_threshold
                        else:
                            raise
                else:
                    logger.error(
                        "OpenWakeWord: verifier %s is missing; using rollback model",
                        verifier,
                    )
                    if fallback_model.exists():
                        self._use_rollback_settings(fallback_model)
                        model_kwargs["wakeword_models"] = [self.model_path]
                        model_kwargs["vad_threshold"] = self.vad_threshold
                    else:
                        raise FileNotFoundError(
                            f"Personal verifier and rollback model are missing: {verifier}"
                        )

            logger.info("OpenWakeWord: loading custom model from %s", self.model_path)
            try:
                self._oww_model = Model(**model_kwargs)
            except Exception:
                if not fallback_model.exists() or Path(self.model_path) == fallback_model:
                    raise
                logger.exception(
                    "OpenWakeWord: personalized model failed; rolling back to %s",
                    fallback_model,
                )
                self._use_rollback_settings(fallback_model)
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

    def _use_rollback_settings(self, fallback_model: Path) -> None:
        """Restore the known-good model and its backward-compatible policy."""
        self.model_path = str(fallback_model)
        self.verifier_path = ""
        self._verifier_model = None
        self.threshold = self._legacy_threshold
        self.vad_threshold = self._legacy_vad_threshold
        self.strong_threshold = max(self.threshold, 1.0)
        self.base_rescue_threshold = 1.0
        self.smoothing_window = 1
        self.smoothing_hits = 1
        self._score_history.clear()

    def _open_stream(self) -> None:
        from src.utils.audio_lock import AUDIO_DEVICE_LOCK
        with AUDIO_DEVICE_LOCK:
            self._pa = pyaudio.PyAudio()
            self._device_index = resolve_input_device_index(
                self.input_device_name,
                self._pa,
                sample_rate=_SAMPLE_RATE,
                input_format=_FORMAT,
            )
            if self.input_device_name and self._device_index is None:
                logger.warning(
                    "OpenWakeWord: input '%s' not found; using system default",
                    self.input_device_name,
                )
            self._stream = self._pa.open(
                rate=_SAMPLE_RATE,
                channels=_CHANNELS,
                format=_FORMAT,
                input=True,
                frames_per_buffer=_FRAME_SAMPLES,
                input_device_index=self._device_index,
            )
        logger.info(
            "OpenWakeWord: audio stream opened (%d Hz, %d ms frames, device=%s)",
            _SAMPLE_RATE,
            _FRAME_MS,
            self._device_index if self._device_index is not None else "system default",
        )

    def _cleanup(self) -> None:
        from src.utils.audio_lock import AUDIO_DEVICE_LOCK
        with AUDIO_DEVICE_LOCK:
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
            self._stream_released.set()

    def _supervisor_loop(self) -> None:
        restart_times: list[float] = []
        try:
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
                    if not self._ready_event.is_set():
                        self._startup_error = str(exc)
                        self._ready_event.set()
                    self._cleanup()

                    if n > _MAX_RAPID_RESTARTS:
                        backoff = min(2 ** (n - _MAX_RAPID_RESTARTS), 60)
                        logger.warning("[WATCHDOG] %d restarts in %ds — backing off %ds", n, _RAPID_RESTART_WINDOW, backoff)
                        time.sleep(backoff)
                    else:
                        time.sleep(1.0)

                    if self._running:
                        logger.info("[WATCHDOG] Restarting OpenWakeWord detection loop...")
        finally:
            # A stop can arrive while ONNX/openWakeWord is still importing. In
            # that case cleanup must happen after the blocking load returns,
            # otherwise the old detector can open and retain the microphone
            # after main has already switched to a fallback detector.
            self._cleanup()

    def _detection_loop(self) -> None:
        self._load_model()
        if not self._running:
            return
        self._open_stream()
        if not self._running:
            self._cleanup()
            return
        self._startup_error = None
        self._ready_event.set()

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
            self._audio_history.append(raw)
            rms = self._rms(audio)
            if rms < max(80.0, self._noise_rms * 3.0):
                self._noise_rms = (self._noise_rms * 0.98) + (rms * 0.02)

            # Run openWakeWord inference (includes Silero VAD internally),
            # then apply the personal verifier while retaining both scores.
            inference_started = time.perf_counter()
            predictions = self._oww_model.predict(audio)
            vad_score = self._current_vad_score()

            # Check for one strong score or multiple normal scores in a short
            # rolling window. The personal verifier is applied separately so
            # the base score remains available for local diagnostics.
            for model_name, base_score_value in predictions.items():
                base_score = float(base_score_value)
                score, verifier_score = self._apply_personal_verifier(
                    model_name,
                    base_score,
                )
                total_latency_ms = (time.perf_counter() - inference_started) * 1_000
                activated, normal_hits = self._activation_decision(
                    model_name, score, base_score=base_score,
                    verifier_score=verifier_score, vad_score=vad_score,
                )

                if score >= min(self.threshold, self.verifier_gate):
                    self._log_near_miss(
                        model_name,
                        base_score,
                        verifier_score,
                        score,
                        vad_score,
                        rms,
                        total_latency_ms,
                        normal_hits,
                        activated,
                    )

                if activated:
                    now = time.monotonic()
                    if self._is_debounced(now):
                        logger.debug(
                            "OpenWakeWord: debounced trigger (%.2f < %.2f debounce)",
                            now - self._last_trigger_time, self.debounce,
                        )
                        break

                    self._last_trigger_time = now
                    command_audio, continuation_meta = self._capture_command_continuation()
                    detection = WakeDetection(
                        model_name=model_name,
                        confidence=float(score),
                        command_audio=command_audio,
                        metadata={
                            "base_score": round(base_score, 4),
                            "verifier_score": (
                                round(verifier_score, 4)
                                if verifier_score is not None
                                else None
                            ),
                            "vad": round(vad_score, 4),
                            "rms": round(rms, 2),
                            "noise_rms": round(self._noise_rms, 2),
                            "inference_latency_ms": round(total_latency_ms, 2),
                            "normal_hits": normal_hits,
                            **continuation_meta,
                        },
                    )
                    logger.info(
                        "OpenWakeWord: WAKE WORD detected! model=%s score=%.3f command_audio=%s",
                        model_name,
                        score,
                        bool(command_audio),
                    )
                    if self.capture_diagnostics:
                        self._save_diagnostic_clip(detection)
                    if self.shadow_mode:
                        logger.info("OpenWakeWord: shadow mode suppressed activation")
                        self._score_history.get(model_name, collections.deque()).clear()
                        break
                    try:
                        self.callback(detection)
                    except Exception as cb_exc:
                        logger.error("OpenWakeWord: callback error: %s", cb_exc)
                    break  # one trigger per frame

    def _is_debounced(self, now: float) -> bool:
        return now - self._last_trigger_time < self.debounce

    def _apply_personal_verifier(
        self,
        model_name: str,
        base_score: float,
    ) -> tuple[float, Optional[float]]:
        """Return the effective score and optional voice-verifier score."""
        if self._verifier_model is None or base_score < self.verifier_gate:
            return base_score, None

        try:
            parent_model = self._oww_model.get_parent_model_from_label(model_name)
            features = self._oww_model.preprocessor.get_features(
                self._oww_model.model_inputs[parent_model]
            )
            verifier_score = float(self._verifier_model.predict_proba(features)[0][-1])
            return verifier_score, verifier_score
        except Exception as exc:
            fallback_model = resource_path("vosk_models", "hey_aiden.onnx")
            if fallback_model.exists():
                self._use_rollback_settings(fallback_model)
            raise RuntimeError("Personal wake verifier inference failed") from exc

    def _current_vad_score(self) -> float:
        """Return the VAD score window openWakeWord used for this frame."""
        vad = getattr(self._oww_model, "vad", None)
        prediction_buffer = getattr(vad, "prediction_buffer", None)
        if prediction_buffer is None:
            return 0.0
        frames = list(prediction_buffer)[-7:-4]
        return float(max(frames)) if frames else 0.0

    def _activation_decision(
        self, model_name: str, score: float, *, base_score: Optional[float] = None,
        verifier_score: Optional[float] = None, vad_score: float = 0.0,
    ) -> tuple[bool, int]:
        history = self._score_history.setdefault(
            model_name,
            collections.deque(maxlen=self.smoothing_window),
        )
        history.append(score)
        normal_hits = sum(item >= self.threshold for item in history)
        activated = score >= self.strong_threshold or normal_hits >= self.smoothing_hits
        rescue_threshold = getattr(self, "base_rescue_threshold", 1.0)
        # A personal voice classifier can under-score a genuine pronunciation.
        # An explicitly tuned profile may rescue a strong phrase-model match,
        # but only with high speech confidence and some verifier agreement.
        base_rescue = (
            rescue_threshold < 1.0
            and base_score is not None and base_score >= rescue_threshold
            and verifier_score is not None
            and verifier_score >= self.verifier_gate
            and vad_score >= max(0.8, self.vad_threshold)
        )
        activated = activated or base_rescue
        return activated, normal_hits

    @staticmethod
    def _rms(audio: np.ndarray) -> float:
        if audio.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))

    def _log_near_miss(
        self,
        model_name: str,
        base_score: float,
        verifier_score: Optional[float],
        score: float,
        vad_score: float,
        rms: float,
        inference_latency_ms: float,
        hits: int,
        activated: bool,
    ) -> None:
        now = time.monotonic()
        if not activated and now - self._last_metric_time < 0.4:
            return
        self._last_metric_time = now
        logger.info(
            "[WAKE METRIC] model=%s base=%.3f verifier=%s score=%.3f "
            "vad=%.3f rms=%.1f noise=%.1f latency_ms=%.1f hits=%d/%d activated=%s",
            model_name,
            base_score,
            f"{verifier_score:.3f}" if verifier_score is not None else "n/a",
            score,
            vad_score,
            rms,
            self._noise_rms,
            inference_latency_ms,
            hits,
            self.smoothing_window,
            activated,
        )

    def _capture_command_continuation(self) -> tuple[Optional[bytes], dict]:
        """Capture speech following the wake phrase without opening a new mic."""
        if self.continuation_window_ms <= 0:
            return None, {"continuation": False, "continuation_disabled": True}
        if self._stream is None:
            return None, {"continuation": False}

        probe_frames = max(1, int(np.ceil(self.continuation_window_ms / _FRAME_MS)))
        tail: list[bytes] = []
        tail_rms: list[float] = []
        # A very low RMS floor mistakes normal USB-microphone room noise for a
        # same-breath command and blocks the wake callback for the full five
        # second capture limit. Require clearly voiced audio above both a
        # practical absolute floor and the learned room-noise level.
        gate = max(120.0, self._noise_rms * 2.5)

        for _ in range(probe_frames):
            try:
                frame = self._stream.read(_FRAME_SAMPLES, exception_on_overflow=False)
            except Exception:
                return None, {"continuation": False, "capture_error": True}
            tail.append(frame)
            tail_rms.append(self._rms(np.frombuffer(frame, dtype=np.int16)))

        # The first two frames can contain the trailing edge of the wake word.
        # A real same-breath command must remain voiced beyond that 160 ms
        # grace period, avoiding a false continuous-command branch.
        continuation_frames = tail_rms[2:] if len(tail_rms) > 2 else []
        if sum(value >= gate for value in continuation_frames) < 2:
            return None, {
                "continuation": False,
                "continuation_gate": round(gate, 2),
            }

        silence_frames = 0
        max_frames = int(5_000 / _FRAME_MS)
        stop_after_silence = max(4, int(560 / _FRAME_MS))
        from src.utils.websocket_broadcast import broadcast_from_thread
        preview = None
        if broadcast_from_thread("voice_activity", {
            "status": "listening", "active": True, "speaking": False, "source": "local",
        }):
            from src.speech.live_transcript import LiveTranscript
            preview = LiveTranscript(
                get_settings().speech.vosk_model_path, _SAMPLE_RATE,
                lambda text: broadcast_from_thread("voice_transcript", {"text": text, "source": "local"}),
            )
            for frame in tail:
                preview.feed(frame)
        try:
            for _ in range(max_frames - probe_frames):
                try:
                    frame = self._stream.read(_FRAME_SAMPLES, exception_on_overflow=False)
                except Exception:
                    break
                tail.append(frame)
                if preview:
                    preview.feed(frame)
                value = self._rms(np.frombuffer(frame, dtype=np.int16))
                if value >= gate:
                    silence_frames = 0
                else:
                    silence_frames += 1
                    if silence_frames >= stop_after_silence:
                        break
        finally:
            if preview:
                preview.close()
                broadcast_from_thread("voice_activity", {
                    "status": "processing", "active": True, "speaking": False, "source": "local",
                })

        # Include enough pre-roll for Whisper to hear and remove the wake phrase.
        pcm = b"".join(list(self._audio_history) + tail)
        return pcm, {
            "continuation": True,
            "continuation_gate": round(gate, 2),
            "continuation_ms": int(len(tail) * _FRAME_MS),
        }

    def _save_diagnostic_clip(self, detection: WakeDetection) -> None:
        pcm = detection.command_audio or b"".join(self._audio_history)
        if not pcm:
            return
        try:
            output_dir = resource_path(".local", "wake-word", "captures")
            output_dir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            path = output_dir / f"{stamp}-{detection.model_name}-{detection.confidence:.3f}.wav"
            with wave.open(str(path), "wb") as wav_file:
                wav_file.setnchannels(_CHANNELS)
                wav_file.setsampwidth(2)
                wav_file.setframerate(_SAMPLE_RATE)
                wav_file.writeframes(pcm)
            logger.info("OpenWakeWord: saved diagnostic clip %s", path)
        except Exception as exc:
            logger.warning("OpenWakeWord: could not save diagnostic clip: %s", exc)
