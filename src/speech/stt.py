"""
Speech-to-Text (STT) System — WebRTC VAD Edition

Uses Google's open-source WebRTC Voice Activity Detection (the same VAD
used by Chrome, Android, and Google Translate) instead of the crude
energy-threshold approach from speech_recognition.

Key differences from the old energy-threshold approach:
- WebRTC VAD is a neural-network classifier that looks at audio *features*,
  not just volume.  It detects speech from across the room even when quiet.
- A ring buffer captures 300ms of pre-speech audio so the start of words
  isn't clipped.
- Speech ends when the VAD sees enough consecutive non-speech frames to
  exceed pause_threshold, matching how Google Translate behaves.
"""
import asyncio
import collections
import io
import time
import struct
from typing import Optional, Tuple

import speech_recognition as sr
import webrtcvad

from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# WebRTC VAD constraints
_SUPPORTED_RATES = (8000, 16000, 32000, 48000)
_FRAME_DURATION_MS = 30  # 10, 20, or 30 ms — 30 gives the best accuracy
_SAMPLE_WIDTH = 2  # 16-bit PCM = 2 bytes per sample


class STTEngine:
    """
    Speech-to-Text engine using WebRTC VAD for voice activity detection.

    Instead of relying on SpeechRecognition's energy-threshold VAD (which
    requires you to shout from a few metres away), this uses Google's
    WebRTC VAD — the exact same detector powering Chrome and Google
    Translate.  It classifies audio by its spectral features, not just
    its loudness, so it works at natural speaking volumes from across
    the room.
    """

    def __init__(self):
        self.settings = get_settings()
        self.recognizer = sr.Recognizer()

        # Configure from settings
        self.language = self.settings.speech.stt_language
        self.timeout = self.settings.speech.stt_timeout
        self.pause_threshold = self.settings.speech.stt_pause_threshold
        self.device_index = self.settings.speech.stt_device_index
        self.non_speaking_duration = self.settings.speech.stt_non_speaking_duration

        # WebRTC VAD aggressiveness: 0 = most sensitive (catches quiet speech),
        # 3 = most aggressive (only loud/clear speech).
        # Level 1 is a good balance: catches normal-to-quiet speech from distance
        # while still filtering out most non-speech sounds.
        self.vad_aggressiveness = 0

        # Audio parameters — 16kHz mono 16-bit PCM is what WebRTC VAD requires
        self.sample_rate = 16000
        self.frame_duration_ms = _FRAME_DURATION_MS
        self.frame_size = int(self.sample_rate * self.frame_duration_ms / 1000)  # samples per frame
        self.frame_bytes = self.frame_size * _SAMPLE_WIDTH  # bytes per frame

        # Pre-speech ring buffer: 300ms of audio so we don't clip word starts
        self._ring_buffer_size = int(300 / self.frame_duration_ms)  # ~10 frames

        # Maximum recording duration (safety limit)
        self.max_speech_duration = 30.0  # seconds

        # Speech start threshold: what fraction of the ring buffer must
        # contain speech for us to consider "speech has started"
        self.speech_start_ratio = 0.4  # 40% — more sensitive than 50%

        logger.info(
            f"STT Engine initialized (WebRTC VAD): "
            f"aggressiveness={self.vad_aggressiveness}, "
            f"sample_rate={self.sample_rate}, "
            f"pause_threshold={self.pause_threshold}s, "
            f"non_speaking_duration={self.non_speaking_duration}s, "
            f"pre_buffer=300ms"
        )

    async def transcribe(self, play_activation_sound: bool = True) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Listen and transcribe speech to text.

        Returns:
            Tuple of (success, text, error_message)
        """
        try:
            # Play activation sound BEFORE opening microphone
            if play_activation_sound:
                from src.speech.tts import get_tts_engine
                tts = get_tts_engine()
                await tts.play_sound("activation")

            # Broadcast listening status
            try:
                from src.utils.websocket_broadcast import broadcast_voice_status
                await broadcast_voice_status("listening", speaking=False)
            except Exception:
                pass

            # Run blocking listen operation in thread pool
            loop = asyncio.get_event_loop()
            success, audio, error = await loop.run_in_executor(None, self._listen_sync)
            
            text = None
            if success and audio:
                from src.ai.groq_client import get_groq_client
                groq_client = await get_groq_client()
                try:
                    text = await groq_client.transcribe_audio(audio.get_wav_data())
                    if text:
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

    def _listen_with_vad(self, source) -> sr.AudioData:
        """
        Listen for speech using WebRTC VAD — the same voice activity
        detection used by Google Chrome and Google Translate.

        How it works:
        1. Continuously read 30ms audio frames from the microphone
        2. Feed each frame to WebRTC VAD, which classifies it as speech/non-speech
        3. Maintain a 300ms ring buffer of recent frames
        4. When >40% of buffer frames are speech → consider "speech started",
           flush the buffer (preserving word starts) and begin recording
        5. While recording, track consecutive silence
        6. When silence exceeds pause_threshold → speech ended, return audio

        This approach detects quiet/distant speech that energy-threshold
        methods completely miss, because WebRTC VAD analyses spectral
        features rather than just volume.
        """
        vad = webrtcvad.Vad(self.vad_aggressiveness)

        ring_buffer = collections.deque(maxlen=self._ring_buffer_size)
        audio_chunks: list[bytes] = []
        speech_started = False
        silence_duration = 0.0
        speech_duration = 0.0
        start_time = time.time()
        frame_duration_s = self.frame_duration_ms / 1000.0

        logger.debug(
            f"STT VAD: Listening (aggressiveness={self.vad_aggressiveness}, "
            f"timeout={self.timeout}s, pause={self.pause_threshold}s)"
        )

        while True:
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

            # Classify frame as speech or non-speech
            try:
                is_speech = vad.is_speech(frame, self.sample_rate)
            except Exception:
                # Malformed frame — skip
                continue

            if not speech_started:
                # ---- WAITING FOR SPEECH ----
                ring_buffer.append((frame, is_speech))

                # Check if enough recent frames are speech
                speech_frames = sum(1 for _, s in ring_buffer if s)
                if len(ring_buffer) >= 2 and speech_frames >= self.speech_start_ratio * len(ring_buffer):
                    speech_started = True
                    speech_duration = len(ring_buffer) * frame_duration_s
                    logger.debug(
                        f"STT VAD: Speech started "
                        f"({speech_frames}/{len(ring_buffer)} frames in buffer, "
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

                if is_speech:
                    silence_duration = 0.0
                else:
                    silence_duration += frame_duration_s

                # Speech ended: enough silence
                if silence_duration >= self.pause_threshold:
                    logger.debug(
                        f"STT VAD: Speech ended "
                        f"(silence={silence_duration:.2f}s >= pause={self.pause_threshold}s, "
                        f"total_speech={speech_duration:.1f}s)"
                    )
                    break

                # Safety: cap maximum recording length
                if speech_duration >= self.max_speech_duration:
                    logger.warning(f"STT VAD: Max recording duration reached ({self.max_speech_duration}s)")
                    break

        # Combine all chunks into one AudioData
        audio_bytes = b"".join(audio_chunks)
        logger.debug(f"STT VAD: Captured {len(audio_bytes)} bytes ({speech_duration:.1f}s of audio)")

        return sr.AudioData(audio_bytes, self.sample_rate, _SAMPLE_WIDTH)

    def _listen_sync(self) -> Tuple[bool, Optional[sr.AudioData], Optional[str]]:
        """Synchronous listen operation (runs in thread pool)"""
        try:
            mic_kwargs = {"sample_rate": self.sample_rate}
            if self.device_index is not None:
                mic_kwargs["device_index"] = self.device_index
                logger.debug(f"STT: Using microphone device index {self.device_index}")

            with sr.Microphone(**mic_kwargs) as source:
                logger.debug(f"STT: Microphone ready ({self.sample_rate}Hz)")

                # Use WebRTC VAD instead of energy-threshold listening
                try:
                    audio = self._listen_with_vad(source)
                    logger.debug("STT: Audio captured via WebRTC VAD")
                    return True, audio, None
                except sr.WaitTimeoutError:
                    logger.info("STT: Timeout — no speech detected")
                    return False, None, "timeout"

        except Exception as e:
            logger.error(f"STT: Exception: {e}")
            return False, None, str(e)

    def adjust_for_ambient_noise(self, duration: float = 1.0):
        """No-op: WebRTC VAD doesn't need ambient noise calibration."""
        logger.info("STT: WebRTC VAD doesn't require ambient noise calibration — skipping")

    def reset_calibration(self):
        """No-op: WebRTC VAD doesn't use calibration."""
        logger.info("STT: WebRTC VAD doesn't use calibration — nothing to reset")


# Global instance
_stt_engine: Optional[STTEngine] = None


def get_stt_engine() -> STTEngine:
    """Get or create global STT engine"""
    global _stt_engine
    if _stt_engine is None:
        _stt_engine = STTEngine()
    return _stt_engine
