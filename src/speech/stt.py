"""
Speech-to-Text (STT) System — Silero VAD Edition

Primary VAD: Silero VAD (PyTorch neural network, significantly more accurate than
WebRTC VAD at distinguishing speech from noise/music/TV).

Fallback VAD: WebRTC VAD (used automatically if torch is not installed).

Key improvements over the old WebRTC-only approach:
- Silero scores each 32ms frame with a 0–1 confidence value; WebRTC gives binary yes/no
- speech_start_ratio raised 0.40 → 0.55 (harder for noise to trigger recording)
- Minimum 4 ring-buffer frames required before accepting speech started
- 0.3s minimum speech duration gate (silence / coughs won't reach Groq)
- Whisper hallucination filter rejects known phantom phrases
- pause_threshold default reduced 1.5 → 0.8s (configured in SpeechConfig)
"""
from __future__ import annotations

import asyncio
import collections
import io
import time
import struct
import threading
from typing import Optional, Tuple, List

import speech_recognition as sr
try:
    import webrtcvad
    _WEBRTCVAD_AVAILABLE = True
except ImportError:
    webrtcvad = None  # type: ignore[assignment]
    _WEBRTCVAD_AVAILABLE = False
import numpy as np

from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# WebRTC VAD constraints (used as fallback when torch/Silero is unavailable)
_SUPPORTED_RATES = (8000, 16000, 32000, 48000)
_FRAME_DURATION_MS_WEBRTC = 30   # 10, 20, or 30 ms — 30 gives the best WebRTC accuracy
_FRAME_DURATION_MS_SILERO = 32   # Silero requires exactly 512 samples @ 16 kHz = 32 ms
_SAMPLE_WIDTH = 2                # 16-bit PCM = 2 bytes per sample

# Known Whisper hallucinations on silence / noise.
# These are verbatim phrases Whisper reliably outputs when fed near-silence.
# IMPORTANT: Only include multi-word phrases that cannot occur in real speech.
# Single words like 'you' or 'bye' are too broad and will block real commands.
_WHISPER_HALLUCINATIONS: tuple[str, ...] = (
    "subtitles by the amara.org community",
    "thank you for watching",
    "thanks for watching",
    "please subscribe",
    "like and subscribe",
    "don't forget to subscribe",
    "see you in the next video",
)


# ---------------------------------------------------------------------------
# Silero VAD wrapper
# ---------------------------------------------------------------------------

class _SileroVAD:
    """
    Thin wrapper around the Silero VAD model from torch.hub.

    Usage:
        vad = _SileroVAD(threshold=0.5, sample_rate=16000)
        is_speech = vad.is_speech(pcm_bytes)  # bytes must be exactly frame_bytes long

    Falls back gracefully: if torch is unavailable the constructor raises
    ImportError, which the caller catches to fall back to WebRTC VAD.
    """

    def __init__(self, threshold: float = 0.5, sample_rate: int = 16000):
        import torch  # raises ImportError if not installed

        self.threshold = threshold
        self.sample_rate = sample_rate
        self._torch = torch

        logger.info("SileroVAD: Loading model from torch.hub (first run may download ~2 MB)…")
        self._model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            verbose=False,
            trust_repo=True,
        )
        self._model.eval()
        # Reset internal state (Silero is stateful per stream)
        self._model.reset_states()
        logger.info("SileroVAD: Model loaded successfully.")

    def reset(self):
        """Reset per-stream state (call before each new listen session)."""
        self._model.reset_states()

    def is_speech(self, pcm_bytes: bytes) -> bool:
        """
        Classify a single PCM frame.

        Args:
            pcm_bytes: Raw 16-bit little-endian PCM; must be exactly
                       512 samples (1024 bytes) at 16 kHz.
        Returns:
            True if Silero confidence >= threshold.
        """
        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        tensor = self._torch.from_numpy(audio).unsqueeze(0)  # shape: [1, 512]
        with self._torch.no_grad():
            confidence = self._model(tensor, self.sample_rate).item()
        return confidence >= self.threshold


# ---------------------------------------------------------------------------
# STT Engine
# ---------------------------------------------------------------------------

class STTEngine:
    """
    Speech-to-Text engine with Silero VAD (falls back to WebRTC VAD).

    Silero VAD is a neural-network classifier that assigns a 0–1 confidence
    score to each 32 ms audio frame, making it far more robust than the
    volume-threshold (WebRTC) approach for distinguishing speech from music,
    TV, background chatter, fan noise, etc.
    """

    def __init__(self):
        self.settings = get_settings()
        self.recognizer = sr.Recognizer()
        self._stop_requested = threading.Event()

        # Configure from settings
        self.language = self.settings.speech.stt_language
        self.timeout = self.settings.speech.stt_timeout
        self.pause_threshold = self.settings.speech.stt_pause_threshold
        self.device_index = self.settings.speech.stt_device_index
        self.non_speaking_duration = self.settings.speech.stt_non_speaking_duration

        # Audio parameters — 16 kHz mono 16-bit PCM
        self.sample_rate = 16000

        # --- VAD selection ---
        self._silero: Optional[_SileroVAD] = None
        use_silero = getattr(self.settings.speech, "stt_use_silero_vad", True)
        silero_threshold = getattr(self.settings.speech, "stt_silero_threshold", 0.28)

        if use_silero:
            try:
                self._silero = _SileroVAD(
                    threshold=silero_threshold,
                    sample_rate=self.sample_rate,
                )
                # Silero requires exactly 512 samples @ 16 kHz = 32 ms
                self.frame_duration_ms = _FRAME_DURATION_MS_SILERO
                logger.info("STT: Using Silero VAD (neural, high-accuracy)")
            except ImportError:
                logger.warning(
                    "STT: torch not installed — falling back to WebRTC VAD. "
                    "Install PyTorch for better accuracy: "
                    "pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu"
                )
                self.frame_duration_ms = _FRAME_DURATION_MS_WEBRTC
            except Exception as e:
                logger.warning(f"STT: Silero VAD failed to load ({e}) — falling back to WebRTC VAD")
                self.frame_duration_ms = _FRAME_DURATION_MS_WEBRTC
        else:
            logger.info("STT: Silero VAD disabled via config — using WebRTC VAD")
            self.frame_duration_ms = _FRAME_DURATION_MS_WEBRTC

        # WebRTC VAD aggressiveness (0=sensitive … 3=strict); used only as fallback
        self.vad_aggressiveness: int = getattr(
            self.settings.speech, "stt_vad_aggressiveness", 1
        )

        self.frame_size = int(self.sample_rate * self.frame_duration_ms / 1000)
        self.frame_bytes = self.frame_size * _SAMPLE_WIDTH

        # Pre-speech ring buffer — 500 ms so word starts aren't clipped
        self._ring_buffer_size = int(500 / self.frame_duration_ms)          # ~15–16 frames
        self._trailing_window_frames = max(3, int(240 / self.frame_duration_ms))

        # Safety cap on recording length
        self.max_speech_duration = 30.0  # seconds

        # Speech-start threshold: fraction of ring buffer that must be speech.
        # Lowered to 0.35 — allows normal/distant conversational speech without shouting.
        self.speech_start_ratio = 0.35

        # Minimum ring-buffer frames before we can accept "speech started".
        # Prevents 2-frame noise bursts from triggering at the very beginning.
        self.speech_start_min_frames = 3

        # Minimum recorded speech duration (seconds) before sending to Groq.
        # Anything shorter is almost certainly noise or a cough.
        self.min_speech_duration = 0.3

        selected_device_name = self._get_selected_device_name()
        vad_name = "Silero" if self._silero else f"WebRTC (aggressiveness={self.vad_aggressiveness})"

        logger.info(
            f"STT Engine initialized: VAD={vad_name}, "
            f"frame={self.frame_duration_ms}ms, "
            f"pause_threshold={self.pause_threshold}s, "
            f"non_speaking={self.non_speaking_duration}s, "
            f"pre_buffer=500ms"
        )
        logger.info(
            "STT input device: %s",
            selected_device_name or "system default microphone"
        )

        # Initialize persistent microphone to eliminate startup latency
        self._persistent_mic = None
        self._init_persistent_mic()

    def _init_persistent_mic(self):
        """Pre-warm the PyAudio stream to eliminate 500ms+ startup latency."""
        try:
            mic_kwargs = {"sample_rate": self.sample_rate}
            if self.device_index is not None:
                mic_kwargs["device_index"] = self.device_index
            self._persistent_mic = sr.Microphone(**mic_kwargs)
            # Enter the context to open the PyAudio stream and keep it open
            self._persistent_mic.__enter__()
            logger.info("STT: Persistent microphone initialized and pre-warmed")
        except Exception as e:
            logger.error(f"STT: Failed to initialize persistent microphone: {e}")
            self._persistent_mic = None

    def _ensure_mic(self) -> sr.Microphone:
        """Ensure persistent microphone is ready."""
        if not self._persistent_mic:
            self._init_persistent_mic()
        if not self._persistent_mic:
            raise RuntimeError("Could not initialize microphone")
        return self._persistent_mic

    def _get_selected_device_name(self) -> Optional[str]:
        """Resolve the configured microphone name for logging/debugging."""
        try:
            device_names = sr.Microphone.list_microphone_names()
        except Exception as e:
            logger.debug(f"STT: Could not enumerate microphone devices: {e}")
            return None

        if self.device_index is None:
            return None

        if 0 <= self.device_index < len(device_names):
            return f"[{self.device_index}] {device_names[self.device_index]}"

        return f"configured index {self.device_index} (not found)"

    def _should_reject_transcript(self, text: str) -> bool:
        """
        Hallucination filter — currently disabled.
        All transcripts pass through regardless of content.
        Re-enable by adding rejection logic here if needed in future.
        """
        return False

    # ------------------------------------------------------------------
    # Public async interface
    # ------------------------------------------------------------------

    async def transcribe(
        self,
        play_activation_sound: bool = True,
        duck_state: Optional[dict] = None,
        media_already_ducked: bool = False,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Listen and transcribe speech to text.

        Returns:
            Tuple of (success, text, error_message)
        """
        active_duck_state = duck_state if media_already_ducked else None
        self._stop_requested.clear()
        try:
            # Briefly pause media sources so STT does not capture music/voice playback.
            if not media_already_ducked:
                try:
                    from src.media.media_router import get_media_router
                    active_duck_state = await get_media_router().duck_for_listening()
                except Exception as exc:
                    logger.debug(f"STT media ducking unavailable: {exc}")

            # Play activation sound after prep and before opening the microphone.
            if play_activation_sound:
                from src.speech.tts import get_tts_engine
                tts = get_tts_engine()
                await tts.play_sound_now("activation")

            # Broadcast listening status
            try:
                from src.utils.websocket_broadcast import broadcast_voice_status
                await broadcast_voice_status("listening", speaking=False)
            except Exception:
                pass

            # Reset Silero's per-stream state before each listen session
            if self._silero:
                self._silero.reset()

            # Run blocking listen operation in thread pool
            success, audio, error = await asyncio.to_thread(self._listen_sync)

            if self._stop_requested.is_set():
                logger.info("STT: Stop requested after audio capture — treating listen as cancelled")
                return False, None, "cancelled"

            text = None
            if success and audio:
                from src.ai.groq_client import get_groq_client
                groq_client = await get_groq_client()
                if self._stop_requested.is_set():
                    logger.info("STT: Stop requested before transcription — skipping")
                    return False, None, "cancelled"
                try:
                    text = await groq_client.transcribe_audio(audio.get_wav_data())
                    if self._stop_requested.is_set():
                        logger.info("STT: Stop requested during transcription — discarding result")
                        return False, None, "cancelled"
                    if text:
                        if self._should_reject_transcript(text):
                            success = False
                            text = None
                            error = "No speech detected"
                        else:
                            logger.info(f"STT: Recognized (Groq Whisper): '{text}'")
                    else:
                        logger.warning("STT: Empty recognition result")
                        success = False
                        error = "No speech detected"
                except Exception as e:
                    logger.error(f"STT: Groq API error: {e}")
                    success = False
                    error = f"Speech service error: {str(e)}"

            result = (success, text, error)

            # Broadcast idle status after listening completes
            try:
                from src.utils.websocket_broadcast import broadcast_voice_status
                await broadcast_voice_status("idle", speaking=False)
            except Exception:
                pass

            return result

        except Exception as e:
            logger.error(f"STT error: {e}")
            try:
                from src.utils.websocket_broadcast import broadcast_voice_status
                await broadcast_voice_status("idle", speaking=False)
            except Exception:
                pass
            return False, None, str(e)
        finally:
            try:
                if active_duck_state is not None:
                    from src.media.media_router import get_media_router
                    await get_media_router().restore_after_listening(active_duck_state)
            except Exception as exc:
                logger.debug(f"STT media restore skipped: {exc}")
            finally:
                self._stop_requested.clear()

    # ------------------------------------------------------------------
    # VAD listening (blocking — runs inside thread pool)
    # ------------------------------------------------------------------

    def _classify_frame(self, frame: bytes, webrtc_vad: webrtcvad.Vad) -> bool:
        """
        Classify a single PCM frame as speech or non-speech.

        Uses Silero VAD when available, otherwise WebRTC VAD.
        """
        try:
            if self._silero:
                return self._silero.is_speech(frame)
            else:
                return webrtc_vad.is_speech(frame, self.sample_rate)
        except Exception:
            return False

    def _listen_with_vad(self, source) -> sr.AudioData:
        """
        Listen for speech using Silero VAD (or WebRTC VAD as fallback).

        Algorithm:
        1. Read 32 ms (Silero) or 30 ms (WebRTC) frames continuously.
        2. Classify each frame with the active VAD.
        3. Maintain a 300 ms ring buffer.
        4. Speech starts when ≥ 55% of the ring buffer frames are speech
           AND at least 4 frames have been observed.
        5. Track trailing silence; stop when silence ≥ pause_threshold.
        6. Reject recordings shorter than min_speech_duration (noise/cough).
        """
        webrtc_vad = webrtcvad.Vad(self.vad_aggressiveness) if (_WEBRTCVAD_AVAILABLE and webrtcvad) else None

        ring_buffer = collections.deque(maxlen=self._ring_buffer_size)
        audio_chunks: List[bytes] = []
        speech_started = False
        silence_duration = 0.0
        speech_duration = 0.0
        start_time = time.time()
        frame_duration_s = self.frame_duration_ms / 1000.0
        trailing_flags = collections.deque(maxlen=self._trailing_window_frames)
        end_of_speech_silence = max(
            0.55,
            float(self.pause_threshold),
            float(self.non_speaking_duration),
        )

        logger.debug(
            f"STT VAD: Listening (vad={'silero' if self._silero else 'webrtc'}, "
            f"timeout={self.timeout}s, end_silence={end_of_speech_silence}s)"
        )

        while True:
            if self._stop_requested.is_set():
                logger.info("STT VAD: Stop requested — aborting active listen")
                raise InterruptedError("stt_cancelled")

            elapsed = time.time() - start_time

            # Timeout waiting for speech to start
            if not speech_started and elapsed > self.timeout:
                raise sr.WaitTimeoutError("listening timed out while waiting for speech to start")

            # Read one frame from the microphone
            try:
                raw = source.stream.read(self.frame_size)
            except Exception as e:
                logger.warning(f"STT VAD: Frame read error: {e}")
                continue

            # Ensure we have exactly the right number of bytes
            if len(raw) < self.frame_bytes:
                continue

            frame = raw[:self.frame_bytes]

            try:
                is_speech = self._classify_frame(frame, webrtc_vad)
            except Exception:
                is_speech = False

            if not speech_started:
                # ---- WAITING FOR SPEECH ----
                ring_buffer.append((frame, is_speech))

                speech_frames = sum(1 for _, s in ring_buffer if s)
                # Require at least speech_start_min_frames in buffer AND ratio met
                if (
                    len(ring_buffer) >= self.speech_start_min_frames
                    and speech_frames >= self.speech_start_ratio * len(ring_buffer)
                ):
                    speech_started = True
                    speech_duration = len(ring_buffer) * frame_duration_s
                    logger.debug(
                        f"STT VAD: Speech started "
                        f"({speech_frames}/{len(ring_buffer)} frames, "
                        f"{elapsed:.1f}s after listen start)"
                    )
                    # Flush ring buffer into audio (preserves word starts)
                    for buffered_frame, _ in ring_buffer:
                        audio_chunks.append(buffered_frame)
                    ring_buffer.clear()
            else:
                # ---- RECORDING SPEECH ----
                audio_chunks.append(frame)
                speech_duration += frame_duration_s
                trailing_flags.append(is_speech)

                trailing_speech_frames = sum(1 for flag in trailing_flags if flag)
                sustained_speech = trailing_speech_frames >= max(2, len(trailing_flags) // 2)

                if is_speech and sustained_speech:
                    silence_duration = 0.0
                else:
                    silence_duration += frame_duration_s

                # Speech ended: enough silence
                if silence_duration >= end_of_speech_silence:
                    logger.debug(
                        f"STT VAD: Speech ended "
                        f"(silence={silence_duration:.2f}s >= {end_of_speech_silence}s, "
                        f"total_speech={speech_duration:.1f}s)"
                    )
                    break

                # Safety: cap maximum recording length
                if speech_duration >= self.max_speech_duration:
                    logger.warning(f"STT VAD: Max recording duration reached ({self.max_speech_duration}s)")
                    break

        # --- Minimum speech duration gate ---
        if speech_duration < self.min_speech_duration:
            logger.info(
                f"STT VAD: Recording too short ({speech_duration:.2f}s < {self.min_speech_duration}s) "
                "— treating as noise, not sending to Groq"
            )
            raise sr.WaitTimeoutError("recording too short (noise/cough gate)")

        audio_bytes = b"".join(audio_chunks)
        audio_bytes = self._normalize_pcm_gain(audio_bytes)
        logger.debug(f"STT VAD: Captured {len(audio_bytes)} bytes ({speech_duration:.1f}s of audio)")

        return sr.AudioData(audio_bytes, self.sample_rate, _SAMPLE_WIDTH)

    def _normalize_pcm_gain(self, audio_bytes: bytes) -> bytes:
        """
        Automatic Gain Control (AGC) for PCM16 audio.
        Smoothly boosts low-volume/distant speech waveforms to optimal levels
        for Whisper transcription without clipping or blowing up silence.
        """
        try:
            if not audio_bytes:
                return audio_bytes
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
            if len(audio_array) == 0:
                return audio_bytes
            
            peak_amp = np.max(np.abs(audio_array))
            if peak_amp == 0 or peak_amp >= 22000:
                return audio_bytes
                
            target_peak = 22000.0
            gain = min(4.0, target_peak / float(peak_amp))
            if gain <= 1.1:
                return audio_bytes
                
            logger.debug(f"STT AGC: Boosting distant speech gain by {gain:.2f}x (peak {peak_amp} -> {int(peak_amp * gain)})")
            normalized = np.clip(audio_array.astype(np.float32) * gain, -32768, 32767).astype(np.int16)
            return normalized.tobytes()
        except Exception as e:
            logger.warning(f"STT AGC: Failed to normalize audio gain: {e}")
            return audio_bytes

    def _listen_sync(self) -> Tuple[bool, Optional[sr.AudioData], Optional[str]]:
        """Synchronous listen operation (runs in thread pool)"""
        try:
            source = self._ensure_mic()
            logger.debug(f"STT: Persistent microphone ready ({self.sample_rate}Hz)")

            try:
                # Carefully flush stale PyAudio buffer (>500ms old) so we don't catch ancient noise,
                # while preserving the most recent ~400ms of audio in case user started speaking during the cue.
                try:
                    if hasattr(source.stream, 'read'):
                        avail = source.stream.get_read_available()
                        max_keep_samples = int(self.sample_rate * 0.4)  # 400ms = 6400 samples @ 16kHz
                        if avail > max_keep_samples:
                            to_discard = avail - max_keep_samples
                            source.stream.read(to_discard, exception_on_overflow=False)
                            logger.debug(f"STT: Discarded {to_discard} stale stream samples, preserved {avail - to_discard} recent samples")
                except Exception as e:
                    logger.debug(f"STT: Could not flush stream: {e}")

                audio = self._listen_with_vad(source)
                logger.debug("STT: Audio captured via VAD")
                return True, audio, None
            except sr.WaitTimeoutError as e:
                logger.info(f"STT: Timeout/gate — {e}")
                return False, None, "timeout"
            except InterruptedError:
                logger.info("STT: Listening cancelled")
                return False, None, "cancelled"

        except Exception as e:
            logger.error(f"STT: Exception: {e}")
            # If the persistent mic failed (e.g. unplugged), reset it
            if self._persistent_mic:
                try:
                    self._persistent_mic.__exit__(None, None, None)
                except Exception:
                    pass
                self._persistent_mic = None
            return False, None, str(e)


    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def request_stop(self):
        """Request an active microphone listen to stop as soon as possible."""
        self._stop_requested.set()

    def adjust_for_ambient_noise(self, duration: float = 1.0):
        """No-op: neural VAD doesn't need ambient noise calibration."""
        logger.info("STT: Neural VAD doesn't require ambient noise calibration — skipping")

    def reset_calibration(self):
        """No-op: neural VAD doesn't use calibration."""
        logger.info("STT: Neural VAD doesn't use calibration — nothing to reset")

    def close(self):
        """Release persistent microphone resources."""
        if self._persistent_mic:
            try:
                self._persistent_mic.__exit__(None, None, None)
                logger.info("STT: Persistent microphone released")
            except Exception as e:
                logger.warning(f"STT: Error releasing persistent microphone: {e}")
            finally:
                self._persistent_mic = None


# Global instance
_stt_engine: Optional[STTEngine] = None


def get_stt_engine() -> STTEngine:
    """Get or create global STT engine"""
    global _stt_engine
    if _stt_engine is None:
        _stt_engine = STTEngine()
    return _stt_engine


def reset_stt_engine() -> None:
    global _stt_engine
    if _stt_engine is not None:
        _stt_engine.close()
    _stt_engine = None
