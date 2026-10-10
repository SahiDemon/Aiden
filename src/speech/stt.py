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
from typing import Awaitable, Callable, Optional, Tuple, List

import speech_recognition as sr
try:
    import webrtcvad
    _WEBRTCVAD_AVAILABLE = True
except ImportError:
    webrtcvad = None  # type: ignore[assignment]
    _WEBRTCVAD_AVAILABLE = False
import numpy as np
import pyaudio

from src.speech.audio_devices import resolve_input_device_index
from src.speech.audio_cues import is_activation_tone_only
from src.speech.wake_detection import strip_wake_phrase
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
        self.min_listening_duration = self.settings.speech.stt_min_listening_duration
        self.device_index = self.settings.speech.stt_device_index
        self.input_device_name = getattr(self.settings.speech, "input_device_name", "")
        self.non_speaking_duration = self.settings.speech.stt_non_speaking_duration

        # Audio parameters — 16 kHz mono 16-bit PCM
        self.sample_rate = 16000

        # --- VAD selection ---
        self._silero: Optional[_SileroVAD] = None
        use_silero = getattr(self.settings.speech, "stt_use_silero_vad", True)
        silero_threshold = getattr(self.settings.speech, "stt_silero_threshold", 0.5)

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
        self._vad_warmed = False
        self._warm_vad()

        vad_name = "Silero" if self._silero else f"WebRTC (aggressiveness={self.vad_aggressiveness})"

        logger.info(
            f"STT Engine initialized: VAD={vad_name}, "
            f"frame={self.frame_duration_ms}ms, "
            f"pause_threshold={self.pause_threshold}s, "
            f"non_speaking={self.non_speaking_duration}s, "
            f"pre_buffer=500ms"
        )
        # Initialize persistent microphone to eliminate startup latency
        self._persistent_mic = None
        self._init_persistent_mic()
        self._last_activation_refresh = time.monotonic()
        selected_device_name = self._get_selected_device_name()
        logger.info(
            "STT input device: %s",
            selected_device_name or "system default microphone",
        )

    def _init_persistent_mic(self):
        """Pre-warm the PyAudio stream to eliminate 500ms+ startup latency."""
        try:
            # PyAudio/PortAudio device changes must not race with the wake
            # detector releasing or reopening its own stream on Windows.
            from src.utils.audio_lock import AUDIO_DEVICE_LOCK

            with AUDIO_DEVICE_LOCK:
                if self.input_device_name:
                    audio = pyaudio.PyAudio()
                    try:
                        resolved_index = resolve_input_device_index(
                            self.input_device_name,
                            audio,
                            sample_rate=self.sample_rate,
                            input_format=pyaudio.paInt16,
                        )
                    finally:
                        audio.terminate()
                    if resolved_index is not None:
                        # Stable name selection takes precedence over the legacy
                        # numeric index so wake detection and STT share a device.
                        self.device_index = resolved_index
                    elif self.device_index is None:
                        logger.warning(
                            "STT input '%s' not found; using system default microphone",
                            self.input_device_name,
                        )
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

    def _warm_vad(self) -> None:
        """Pay first-inference setup once during startup, before activation."""
        if self._silero and not getattr(self, "_vad_warmed", False):
            self._silero.is_speech(bytes(self.frame_bytes))
            self._silero.reset()
            self._vad_warmed = True

    def refresh_microphone(self) -> bool:
        """Reopen the input stream after a wake-word handoff.

        USB microphones and their Windows audio drivers can leave an otherwise
        valid long-lived PortAudio stream silent after a period of inactivity.
        The wake detector has released its stream before Aiden plays the
        acknowledgement, so reopening the stream before that cue ensures the
        cue only plays once the microphone is genuinely ready.
        """
        idle_seconds = time.monotonic() - getattr(
            self, "_last_activation_refresh", time.monotonic()
        )
        self._last_activation_refresh = time.monotonic()
        self.close()
        logger.info("STT: Refreshing microphone after wake activation (idle %.0fs)", idle_seconds)
        self._init_persistent_mic()
        # The capture worker verifies fresh frames and reopens only if needed.
        # Blindly opening twice added driver latency to every activation.
        return self._persistent_mic is not None

    def _ensure_mic(self) -> sr.Microphone:
        """Ensure persistent microphone is ready."""
        if not self._persistent_mic:
            self._init_persistent_mic()
        if not self._persistent_mic:
            raise RuntimeError("Could not initialize microphone")
        return self._persistent_mic

    @property
    def microphone_ready(self) -> bool:
        """Whether the persistent microphone stream opened successfully."""
        return self._persistent_mic is not None

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
        """Reject empty recognition and explicit acoustic captions, not short replies."""
        text = text.strip()
        if not any(character.isalnum() for character in text):
            return True
        # Whisper sometimes captions a cue instead of recognizing speech.
        # Restrict this to caption formatting so ordinary spoken sentences,
        # including short replies such as 'Oh', 'Bye', and 'Music', survive.
        caption = text.strip("[]() .!♪♫").casefold()
        caption_format = text.isupper() or text.startswith(("[", "("))
        return caption_format and caption in {
            "bell rings", "bell ringing", "beep", "beeping", "music",
            "silence", "applause", "laughter", "background noise",
        }

    # ------------------------------------------------------------------
    # Public async interface
    # ------------------------------------------------------------------

    async def transcribe(
        self,
        play_activation_sound: bool = True,
        duck_state: Optional[dict] = None,
        media_already_ducked: bool = False,
        restore_media: bool = True,
        preserve_recent_audio: bool = False,
        ready_cue: Optional[Callable[[], Awaitable[object]]] = None,
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

            # Convert the legacy flag into a cue callback. The capture worker
            # is armed before this callback runs, so audio cannot be lost in
            # the thread-start gap immediately after the sound.
            if ready_cue is None and play_activation_sound:
                from src.speech.tts import get_tts_engine
                tts = get_tts_engine()

                async def play_default_ready_cue() -> object:
                    return await tts.play_sound_now("activation")

                ready_cue = play_default_ready_cue

            # Reset Silero's per-stream state before each listen session
            if self._silero:
                self._silero.reset()

            # Start capture in the thread pool, but do not claim to be listening
            # until that thread has confirmed live microphone input. Audio
            # arriving during the cue is retained, including early speech.
            loop = asyncio.get_running_loop()
            from src.speech.live_transcript import LiveTranscript
            from src.utils.websocket_broadcast import broadcast_message

            def publish_preview(text):
                def dispatch():
                    if preview and not preview.closed.is_set():
                        asyncio.create_task(broadcast_message("voice_transcript", {"text": text, "source": "local"}))
                loop.call_soon_threadsafe(dispatch)

            speech_settings = getattr(getattr(self, "settings", None), "speech", None)
            preview = LiveTranscript(
                getattr(speech_settings, "vosk_model_path", ""), getattr(self, "sample_rate", 16000), publish_preview,
            )
            self._live_preview = preview
            capture_started_at = loop.time()
            listening_ready = asyncio.Event()
            capture_armed = asyncio.Event()
            start_capture = threading.Event() if ready_cue is not None else None

            def signal_listening_ready() -> None:
                loop.call_soon_threadsafe(listening_ready.set)

            def signal_capture_armed() -> None:
                loop.call_soon_threadsafe(capture_armed.set)

            listen_task = asyncio.create_task(
                asyncio.to_thread(
                    self._listen_sync,
                    signal_listening_ready,
                    preserve_recent_audio,
                    start_capture,
                    signal_capture_armed,
                )
            )
            ready_task = asyncio.create_task(listening_ready.wait())
            armed_task = asyncio.create_task(capture_armed.wait())

            try:
                if ready_cue is not None:
                    armed_or_finished, _ = await asyncio.wait(
                        {listen_task, armed_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if armed_task in armed_or_finished:
                        logger.info("STT: Capture worker armed; playing speak-now cue")
                        logger.info("[TIMING] Capture readiness: %.0f ms", (loop.time() - capture_started_at) * 1000)
                        try:
                            await ready_cue()
                        finally:
                            # The worker retains audio throughout the cue and
                            # passes it into VAD before reading subsequent audio.
                            start_capture.set()
                        logger.info("STT: Speak-now cue finished; microphone is listening")

                done, _ = await asyncio.wait(
                    {listen_task, ready_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if ready_task in done:
                    try:
                        from src.utils.websocket_broadcast import broadcast_voice_status
                        await broadcast_voice_status("listening", speaking=False, active=True)
                    except Exception:
                        pass

                success, audio, error = await asyncio.shield(listen_task)
                logger.info("[TIMING] Microphone recording: %.0f ms", (loop.time() - capture_started_at) * 1000)
            except asyncio.CancelledError:
                # Cancelling to_thread does not stop its microphone worker.
                # Join it before another activation can reopen the device.
                self.request_stop()
                if start_capture is not None:
                    start_capture.set()
                await asyncio.shield(listen_task)
                raise
            finally:
                if start_capture is not None:
                    start_capture.set()
                if not ready_task.done():
                    ready_task.cancel()
                if not armed_task.done():
                    armed_task.cancel()

            if getattr(self, "_live_preview", None):
                self._live_preview.close()

            if self._stop_requested.is_set():
                logger.info("STT: Stop requested after audio capture — treating listen as cancelled")
                return False, None, "cancelled"

            text = None
            if success and audio:
                if self._stop_requested.is_set():
                    logger.info("STT: Stop requested before transcription — skipping")
                    return False, None, "cancelled"
                try:
                    transcription_started_at = loop.time()
                    text = await self._transcribe_audio(audio.get_wav_data())
                    logger.info("[TIMING] Final transcription wait: %.0f ms", (loop.time() - transcription_started_at) * 1000)
                    if self._stop_requested.is_set():
                        logger.info("STT: Stop requested during transcription — discarding result")
                        return False, None, "cancelled"
                    if text:
                        if self._should_reject_transcript(text):
                            logger.info("STT: Ignoring non-speech recognition: %r", text)
                            success = False
                            text = None
                            error = "non_speech"
                        else:
                            logger.info(f"STT: Recognized: '{text}'")
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
            if getattr(self, "_live_preview", None):
                self._live_preview.close()
            try:
                if restore_media and active_duck_state is not None:
                    from src.media.media_router import get_media_router
                    await get_media_router().restore_after_listening(active_duck_state)
            except Exception as exc:
                logger.debug(f"STT media restore skipped: {exc}")
            finally:
                self._stop_requested.clear()

    async def _transcribe_audio(self, wav_bytes: bytes) -> str:
        """Transcribe captured audio with Groq Whisper."""
        from src.ai.groq_client import get_groq_client
        return await (await get_groq_client()).transcribe_audio(wav_bytes)

    async def transcribe_captured_pcm(
        self,
        pcm_bytes: bytes,
        *,
        remove_wake_phrase: bool = True,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Transcribe PCM already captured by the wake-word microphone.

        This avoids reopening the microphone and preserves commands spoken in
        the same breath as the wake phrase.
        """
        if not pcm_bytes:
            return False, None, "empty_audio"

        minimum_bytes = int(self.sample_rate * _SAMPLE_WIDTH * self.min_speech_duration)
        if len(pcm_bytes) < minimum_bytes:
            return False, None, "recording_too_short"

        try:
            normalized = self._normalize_pcm_gain(pcm_bytes)
            audio = sr.AudioData(normalized, self.sample_rate, _SAMPLE_WIDTH)
            text = await self._transcribe_audio(audio.get_wav_data())
            if not text:
                return False, None, "No speech detected"

            command = strip_wake_phrase(text) if remove_wake_phrase else text.strip()
            if self._should_reject_transcript(command):
                return False, None, "non_speech"
            logger.info(
                "STT: Recognized buffered wake command: '%s' -> '%s'",
                text,
                command,
            )
            if not command:
                return False, None, "wake_phrase_only"
            return True, command, None
        except Exception as exc:
            logger.error("STT: Buffered command transcription failed: %s", exc)
            return False, None, f"Speech service error: {exc}"

    # ------------------------------------------------------------------
    # VAD listening (blocking — runs inside thread pool)
    # ------------------------------------------------------------------

    def _classify_frame(
        self, frame: bytes, webrtc_vad: webrtcvad.Vad, *, starting: bool = True,
    ) -> bool:
        """
        Classify a single PCM frame as speech or non-speech.

        Uses Silero VAD when available, otherwise WebRTC VAD.
        Includes a pre-gate RMS energy check to ignore absolute silence/hum.
        """
        try:
            self._last_frame_confirmed_speech = False
            # Quick energy gate: if RMS is extremely low (<30 out of 32768), 
            # it's just silence/line-noise. Don't let the neural net hallucinate.
            audio_array = np.frombuffer(frame, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
            if rms < 30.0:
                return False

            if self._silero:
                if self._silero.is_speech(frame):
                    self._last_frame_confirmed_speech = True
                    return True
                # A quiet command can fall below Silero's confidence threshold.
                # Keep a second speech detector rather than throwing that
                # command away. WebRTC requires 30ms, not Silero's 32ms frame.
                # WebRTC's more sensitive fallback may help START a quiet
                # command, but background noise must not keep extending it
                # after Silero has detected the end of speech.
                if starting and webrtc_vad is not None:
                    valid_bytes = int(self.sample_rate * 0.03) * _SAMPLE_WIDTH
                    return webrtc_vad.is_speech(frame[:valid_bytes], self.sample_rate)
                return False
            if webrtc_vad is None:
                raise RuntimeError("No speech detector is available")
            result = webrtc_vad.is_speech(frame, self.sample_rate)
            self._last_frame_confirmed_speech = result
            return result
        except Exception as exc:
            # Detector errors must be visible; treating every failed inference
            # as silence can discard an entire otherwise valid recording.
            logger.error("STT: Speech detection failed: %s", exc)
            raise

    def _listen_with_vad(self, source, initial_frames=None) -> sr.AudioData:
        """
        Listen for speech using Silero VAD (or WebRTC VAD as fallback).

        Algorithm:
        1. Read 32 ms (Silero) or 30 ms (WebRTC) frames continuously.
        2. Classify each frame with the active VAD.
        3. Maintain a 500 ms ring buffer to retain word starts.
        4. Start when the configured speech ratio and frame count are met.
        5. Track trailing silence; stop when silence ≥ pause_threshold.
        6. Reject recordings shorter than min_speech_duration (noise/cough).
        """
        webrtc_vad = webrtcvad.Vad(self.vad_aggressiveness) if (_WEBRTCVAD_AVAILABLE and webrtcvad) else None

        ring_buffer = collections.deque(maxlen=self._ring_buffer_size)
        audio_chunks: List[bytes] = []
        speech_started = False
        silence_duration = 0.0
        speech_duration = 0.0
        confirmed_speech_duration = 0.0
        frames_read = 0
        energetic_frames = 0
        vad_speech_frames = 0
        start_time = time.monotonic()
        frame_duration_s = self.frame_duration_ms / 1000.0
        trailing_flags = collections.deque(maxlen=self._trailing_window_frames)
        pending_frames = collections.deque(initial_frames or ())
        cue_tail_frames = int(150 / self.frame_duration_ms) if pending_frames else 0
        end_of_speech_silence = max(
            0.55,
            float(self.pause_threshold),
            float(self.non_speaking_duration),
        )
        # Capture starts at the beep, but endpointing must allow a human time
        # to begin. A short cue/noise must not close the window immediately.
        min_listening_duration = getattr(self, "min_listening_duration", 3.0)
        minimum_confirmed_speech = 0.16

        logger.debug(
            f"STT VAD: Listening (vad={'silero' if self._silero else 'webrtc'}, "
            f"timeout={self.timeout}s, end_silence={end_of_speech_silence}s)"
        )

        while True:
            if self._stop_requested.is_set():
                logger.info("STT VAD: Stop requested — aborting active listen")
                raise InterruptedError("stt_cancelled")

            elapsed = time.monotonic() - start_time
            # Include queued cue frames in the audio clock. Unlike wall time,
            # this also accounts for frames consumed from microphone pre-roll.
            capture_elapsed = max(elapsed, frames_read * frame_duration_s)

            # Timeout waiting for speech to start
            if not speech_started and capture_elapsed > max(self.timeout, min_listening_duration):
                logger.warning(
                    "STT VAD: No speech start after %.1fs (frames=%d, energetic=%d, vad_speech=%d)",
                    elapsed,
                    frames_read,
                    energetic_frames,
                    vad_speech_frames,
                )
                raise sr.WaitTimeoutError("listening timed out while waiting for speech to start")

            # Read one frame from the microphone
            during_cue = bool(pending_frames)
            cue_echo_window = during_cue or cue_tail_frames > 0
            if not during_cue and cue_tail_frames > 0:
                cue_tail_frames -= 1
            try:
                raw = pending_frames.popleft() if pending_frames else self._read_live_frame(source)
            except (TimeoutError, InterruptedError):
                raise
            except Exception as e:
                logger.warning(f"STT VAD: Frame read error: {e}")
                raise

            # Ensure we have exactly the right number of bytes
            if len(raw) < self.frame_bytes:
                continue

            frame = raw[:self.frame_bytes]
            frames_read += 1
            frame_samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
            if np.sqrt(np.mean(frame_samples * frame_samples)) >= 30.0:
                energetic_frames += 1

            if cue_echo_window and is_activation_tone_only(frame, self.sample_rate):
                # VAD suppression alone leaves the beep in the pre-roll WAV.
                # Remove tone-only audio before Whisper can caption it; mixed
                # user speech is retained unchanged, including word starts.
                frame = bytes(len(frame))
                is_speech = False
                confirmed_speech = False
            else:
                is_speech = self._classify_frame(
                    frame, webrtc_vad, starting=not speech_started and not during_cue,
                )
                confirmed_speech = is_speech and getattr(self, "_last_frame_confirmed_speech", is_speech)
            if is_speech:
                vad_speech_frames += 1

            if not speech_started:
                # ---- WAITING FOR SPEECH ----
                ring_buffer.append((frame, is_speech, confirmed_speech))

                speech_frames = sum(1 for _, s, _ in ring_buffer if s)
                # Require at least speech_start_min_frames in buffer AND ratio met
                if (
                    len(ring_buffer) >= self.speech_start_min_frames
                    and speech_frames >= self.speech_start_ratio * len(ring_buffer)
                ):
                    speech_started = True
                    speech_duration = len(ring_buffer) * frame_duration_s
                    confirmed_speech_duration = sum(1 for _, _, confirmed in ring_buffer if confirmed) * frame_duration_s
                    logger.debug(
                        f"STT VAD: Speech started "
                        f"({speech_frames}/{len(ring_buffer)} frames, "
                        f"{elapsed:.1f}s after listen start)"
                    )
                    # Flush ring buffer into audio (preserves word starts)
                    for buffered_frame, _, _ in ring_buffer:
                        audio_chunks.append(buffered_frame)
                        if getattr(self, "_live_preview", None):
                            self._live_preview.feed(buffered_frame)
                    ring_buffer.clear()
            else:
                # ---- RECORDING SPEECH ----
                audio_chunks.append(frame)
                if getattr(self, "_live_preview", None):
                    self._live_preview.feed(frame)
                speech_duration += frame_duration_s
                if confirmed_speech:
                    confirmed_speech_duration += frame_duration_s
                trailing_flags.append(is_speech)

                trailing_speech_frames = sum(1 for flag in trailing_flags if flag)
                sustained_speech = trailing_speech_frames >= max(2, len(trailing_flags) // 2)

                if is_speech and (confirmed_speech or sustained_speech):
                    silence_duration = 0.0
                else:
                    silence_duration += frame_duration_s

                # Speech ended: enough silence
                if silence_duration >= end_of_speech_silence:
                    if confirmed_speech_duration < minimum_confirmed_speech:
                        # The sensitive fallback can nominate a quiet onset,
                        # but a noise burst alone must not consume the turn.
                        # Keep the same stream/cue and original start deadline.
                        logger.debug("STT VAD: Unconfirmed noise onset; continuing to wait for speech")
                        speech_started = False
                        speech_duration = 0.0
                        confirmed_speech_duration = 0.0
                        silence_duration = 0.0
                        audio_chunks.clear()
                        if getattr(self, "_live_preview", None):
                            self._live_preview.reset()
                        ring_buffer.clear()
                        trailing_flags.clear()
                        continue
                    if capture_elapsed < min_listening_duration:
                        continue
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

    def _listen_sync(
        self,
        on_listening_ready: Optional[Callable[[], None]] = None,
        preserve_recent_audio: bool = False,
        start_capture: Optional[threading.Event] = None,
        on_capture_armed: Optional[Callable[[], None]] = None,
    ) -> Tuple[bool, Optional[sr.AudioData], Optional[str]]:
        """Synchronous listen operation (runs in thread pool)"""
        try:
            source = self._prepare_live_microphone(preserve_recent_audio)
            logger.debug(f"STT: Persistent microphone ready ({self.sample_rate}Hz)")

            try:
                # Flush anything captured before this listen. SpeechRecognition
                # wraps the native PyAudio stream, so get_read_available() must
                # be read from pyaudio_stream while audio is consumed through
                # the wrapper's one-argument read().
                self._discard_buffered_audio(source, preserve_recent_audio)

                cue_frames = []
                if start_capture is not None:
                    if on_capture_armed:
                        on_capture_armed()

                    # RECORD during the cue. Discarding here swallowed commands
                    # spoken during the acknowledgement or at the beep's end.
                    while not start_capture.is_set():
                        if self._stop_requested.is_set():
                            raise InterruptedError("stt_cancelled")
                        cue_frames.append(self._read_live_frame(source))

                if on_listening_ready:
                    on_listening_ready()

                audio = (
                    self._listen_with_vad(source, initial_frames=cue_frames)
                    if start_capture is not None else self._listen_with_vad(source)
                )
                logger.debug("STT: Audio captured via VAD")
                return True, audio, None
            except sr.WaitTimeoutError as e:
                logger.info(f"STT: Timeout/gate — {e}")
                return False, None, "timeout"
            except InterruptedError:
                logger.info("STT: Listening cancelled")
                return False, None, "cancelled"

        except InterruptedError:
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

    def _read_live_frame(self, source, timeout: float = 1.0) -> bytes:
        """Read only available samples so a stalled driver cannot block capture."""
        native = getattr(source.stream, "pyaudio_stream", source.stream)
        deadline = time.monotonic() + timeout
        while True:
            if self._stop_requested.is_set():
                raise InterruptedError("stt_cancelled")
            if int(native.get_read_available()) >= self.frame_size:
                frame = source.stream.read(self.frame_size)
                if len(frame) != self.frame_bytes:
                    raise OSError("Microphone returned an incomplete audio frame")
                return frame
            if time.monotonic() >= deadline:
                raise TimeoutError("Microphone stopped delivering audio")
            self._stop_requested.wait(0.005)

    def _prepare_live_microphone(self, preserve_recent_audio: bool = False):
        """Prove that fresh frames arrive before allowing a speak-now cue."""
        for attempt in range(3):
            try:
                source = self._ensure_mic()
                if preserve_recent_audio:
                    # Buffered follow-up speech must survive the readiness check.
                    native = getattr(source.stream, "pyaudio_stream", source.stream)
                    if int(native.get_read_available()) >= self.frame_size:
                        return source
                self._discard_buffered_audio(source, preserve_recent_audio=False)
                # Check sustained delivery, not merely a successful stream open
                # or one stale frame. Silence is valid microphone input.
                started = time.monotonic()
                for _ in range(8):
                    self._read_live_frame(source, timeout=0.5)
                    if time.monotonic() - started > 1.0:
                        raise TimeoutError("Microphone frames are arriving too slowly")
                self._warm_vad()
                logger.info("STT: Live microphone verified (8 fresh frames)")
                return source
            except InterruptedError:
                raise
            except Exception as exc:
                logger.warning("STT: Microphone readiness attempt %d failed: %s", attempt + 1, exc)
                self.close()
                if attempt == 2:
                    raise RuntimeError("Microphone is not delivering audio; please check the input device") from exc
        raise RuntimeError("Microphone preparation failed")

    def _discard_buffered_audio(self, source, preserve_recent_audio: bool) -> int:
        """Discard queued microphone samples and return the number consumed."""
        try:
            stream = source.stream
            native_stream = getattr(stream, "pyaudio_stream", stream)
            get_available = getattr(native_stream, "get_read_available", None)
            if get_available is None:
                return 0

            available = int(get_available())
            max_keep_samples = int(self.sample_rate * 0.4) if preserve_recent_audio else 0
            to_discard = max(0, available - max_keep_samples)
            if to_discard:
                stream.read(to_discard)
                logger.debug(
                    "STT: Discarded %d buffered samples, preserved %d recent samples",
                    to_discard,
                    available - to_discard,
                )
            return to_discard
        except Exception as exc:
            logger.debug("STT: Could not flush stream: %s", exc)
            return 0


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
        mic = self._persistent_mic
        self._persistent_mic = None
        if mic is not None:
            try:
                from src.utils.audio_lock import AUDIO_DEVICE_LOCK

                with AUDIO_DEVICE_LOCK:
                    mic.__exit__(None, None, None)
                logger.info("STT: Persistent microphone released")
            except Exception as e:
                logger.warning("STT: Error releasing persistent microphone: %s", e)


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
