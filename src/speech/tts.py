"""
Text-to-Speech (TTS) System with Caching
Migrated and enhanced from original voice_system.py
Supports multiple TTS providers: Edge TTS, Google Chirp 3 HD, and offline pyttsx3
"""
import asyncio
import hashlib
import json
import math
from collections import OrderedDict
import logging
import os
import tempfile
from typing import Optional
import edge_tts
import pygame
import subprocess
import sys
import threading
import time
from contextlib import suppress
import numpy as np

from src.database.redis_client import get_redis_client
from src.utils.config import get_settings
from src.utils.logger import get_logger
from src.utils.paths import resource_path
from src.speech.audio_cues import ACTIVATION_TONE_HZ

logger = get_logger(__name__)


def _activation_tone_pcm(sample_rate: int, channels: int) -> np.ndarray:
    """A 120ms non-voice readiness tone with smooth edges."""
    count = int(sample_rate * 0.12)
    phase = np.arange(count, dtype=np.float64) / sample_rate
    envelope = np.ones(count)
    ramp = max(1, int(sample_rate * 0.01))
    envelope[:ramp] = np.linspace(0, 1, ramp)
    envelope[-ramp:] = np.linspace(1, 0, ramp)
    mono = (np.sin(2 * np.pi * ACTIVATION_TONE_HZ * phase) * envelope * 4000).astype(np.int16)
    return mono if channels == 1 else np.repeat(mono[:, None], channels, axis=1)

# Pygame mixer is initialized lazily on first use (see _ensure_mixer())
# so it always runs on the correct thread.
PYGAME_AVAILABLE = True  # assumed True until proven otherwise
_MIXER_INITIALIZED = False


def _ensure_mixer() -> bool:
    """Lazily initialize pygame mixer. Safe to call multiple times."""
    global _MIXER_INITIALIZED, PYGAME_AVAILABLE
    if _MIXER_INITIALIZED:
        return PYGAME_AVAILABLE
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        _MIXER_INITIALIZED = True
        PYGAME_AVAILABLE = True
    except Exception as e:
        logger.warning(f"Pygame mixer init failed: {e}")
        PYGAME_AVAILABLE = False
        _MIXER_INITIALIZED = True  # don't keep retrying
    return PYGAME_AVAILABLE


class TTSEngine:
    """
    Text-to-Speech engine with Redis caching
    Supports multiple providers:
    - Microsoft Edge TTS (default)
    - Google Cloud TTS with Chirp 3 HD voices
    - Offline pyttsx3 (fallback)
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.provider = self.settings.speech.tts_provider
        self.voice_id = self.settings.speech.tts_voice
        self.rate = self.settings.speech.tts_rate
        self.temp_dir = tempfile.gettempdir()
        self._word_timings = OrderedDict()
        self._stream_stop = threading.Event()
        self._speech_generation = 0
        
        # Google TTS specific settings
        self.google_voice = self.settings.speech.google_tts_voice
        self.google_pitch = self.settings.speech.google_tts_pitch
        self.google_speaking_rate = self.settings.speech.google_tts_speaking_rate
        self.google_credentials_path = self.settings.speech.google_tts_credentials_path
        self.google_client = None
        
        # Initialize Google TTS client if provider is google
        if self.provider == "google":
            self._init_google_client()
        
        self.audio_queue = asyncio.Queue()
        self.is_processing = False
        self._wake_word_pause_depth = 0
        
        # Start queue processor
        asyncio.create_task(self._process_queue())
        
        logger.info(f"TTS Engine initialized: provider={self.provider}, voice={self.voice_id if self.provider == 'edge' else self.google_voice}")

        # Pre-load commonly used sound effects for zero-latency playback
        self._preloaded_sounds: dict[str, pygame.mixer.Sound] = {}
        self._preload_common_sounds()

    def _preload_common_sounds(self):
        """Pre-load frequently used sound effects into memory for instant playback."""
        if not _ensure_mixer():
            return
        # A voice-like MP3 acknowledgement can be recognized as a command
        # when capture is already active. Generate a pure readiness tone.
        try:
            sample_rate, _, channels = pygame.mixer.get_init()
            self._preloaded_sounds["activation"] = pygame.sndarray.make_sound(
                _activation_tone_pcm(sample_rate, channels)
            )
        except Exception as exc:
            logger.warning("Could not prepare activation tone: %s", exc)
        common_sounds = ["mmm1", "mmm2", "error", "success"]
        for name in common_sounds:
            try:
                sound_path = resource_path("sounds", f"{name}.mp3")
                if not sound_path.exists():
                    sound_path = resource_path("sounds", f"{name}.MP3")
                if sound_path.exists():
                    sound = pygame.mixer.Sound(str(sound_path))
                    sound.set_volume(0.6)
                    self._preloaded_sounds[name.lower()] = sound
            except Exception as e:
                logger.debug(f"TTS: Could not pre-load sound {name}: {e}")
        logger.info(f"TTS: Pre-loaded {len(self._preloaded_sounds)} sound effects into memory")

    def is_sound_ready(self, sound_name: str) -> bool:
        """Return whether a cue is preloaded or available for disk fallback."""
        if sound_name.lower() in self._preloaded_sounds:
            return True
        if sound_name.lower() == "activation":
            return False
        return any(
            resource_path("sounds", f"{sound_name}{suffix}").exists()
            for suffix in (".mp3", ".MP3")
        )

    def _pause_wake_word_detection(self) -> bool:
        """Pause wake-word detection while TTS audio is playing."""
        try:
            from src.core.wake_word_manager import get_wake_word_manager

            wake_word_manager = get_wake_word_manager()
            if not wake_word_manager or not getattr(wake_word_manager, "detector", None):
                return False

            if not wake_word_manager.get_state():
                return False

            if self._wake_word_pause_depth == 0:
                detector = wake_word_manager.detector
                if getattr(detector, "is_paused", getattr(detector, "_paused", False)):
                    # Capture already owns the pause. Playback must not resume
                    # the wake microphone underneath an active recording.
                    return False
                wake_word_manager.detector.pause()
                logger.debug("TTS: Paused wake-word detection during playback")

            self._wake_word_pause_depth += 1
            return True
        except Exception as e:
            logger.debug(f"TTS: Could not pause wake-word detection: {e}")
            return False

    def _resume_wake_word_detection(self, was_paused: bool):
        """Resume wake-word detection after TTS playback completes."""
        if not was_paused:
            return

        try:
            self._wake_word_pause_depth = max(0, self._wake_word_pause_depth - 1)
            if self._wake_word_pause_depth != 0:
                return

            from src.core.wake_word_manager import get_wake_word_manager

            wake_word_manager = get_wake_word_manager()
            if wake_word_manager and getattr(wake_word_manager, "detector", None):
                wake_word_manager.detector.resume()
                logger.debug("TTS: Resumed wake-word detection after playback")
        except Exception as e:
            logger.debug(f"TTS: Could not resume wake-word detection: {e}")
    
    def _init_google_client(self):
        """Initialize Google Cloud TTS client"""
        try:
            from google.cloud import texttospeech
            
            # Set credentials if path is provided
            if self.google_credentials_path and os.path.exists(self.google_credentials_path):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.google_credentials_path
            
            self.google_client = texttospeech.TextToSpeechClient()
            logger.info(f"Google TTS client initialized with voice: {self.google_voice}")
        except Exception as e:
            logger.error(f"Failed to initialize Google TTS client: {e}")
            logger.warning("Falling back to Edge TTS provider")
            self.provider = "edge"

    async def _process_queue(self):
        """Process audio queue sequentially"""
        logger.info("TTS: Queue processor started")
        while True:
            try:
                task = await self.audio_queue.get()
                self.is_processing = True
                try:
                    task_type = task.get("type")
                    
                    if task_type == "kitten_stream":
                        self._active_stream_task = asyncio.create_task(self._play_kitten_stream(task["text"]))
                        try:
                            await self._active_stream_task
                        except asyncio.CancelledError:
                            if not self._stream_stop.is_set():
                                raise
                        finally:
                            self._active_stream_task = None
                    elif task_type == "speak":
                        playback_generation = getattr(self, "_speech_generation", 0)
                        audio_data = task.get("data")
                        text = task.get("text")
                        self._active_speech_requested_at = task.get("requested_at")
                        
                        from src.speech.playback_events import register_playback, wait_for_playback
                        source = task.get("source", "local")
                        playback = register_playback(text or "", self._timings_for(audio_data), source)
                        self._active_playback = playback

                        # Broadcast speaking status
                        from src.utils.websocket_broadcast import broadcast_voice_status, broadcast_message
                        await broadcast_voice_status(
                            "processing" if source == "web" else "speaking",
                            speaking=source != "web", active=True,
                        )
                        if text:
                            await broadcast_message("assistant_speaking", playback)

                        if playback_generation != getattr(self, "_speech_generation", 0):
                            from src.speech.playback_events import cancel_playback
                            cancel_playback(playback["speech_id"])
                            if source == "web":
                                await wait_for_playback(playback["speech_id"])
                            continue

                        wake_word_paused = self._pause_wake_word_detection()
                        try:
                            # Play
                            source = task.get("source", "local")
                            await self._play_audio_data(audio_data, source=source)
                            if source == "web":
                                await wait_for_playback(playback["speech_id"])
                        finally:
                            self._resume_wake_word_detection(wake_word_paused)
                        
                        # Broadcast idle status
                        await broadcast_voice_status("idle", speaking=False)
                        
                    elif task_type == "sound":
                        sound_path = task.get("path")
                        wake_word_paused = self._pause_wake_word_detection()

                        async def _play_sound_and_resume():
                            try:
                                await self._play_sound_file(sound_path)
                            finally:
                                self._resume_wake_word_detection(wake_word_paused)

                        # Play sound NON-BLOCKING (fire and forget task)
                        asyncio.create_task(_play_sound_and_resume())
                finally:
                    self.audio_queue.task_done()
                    self.is_processing = False
            except Exception as e:
                logger.error(f"Error in TTS queue processor: {e}")
    
    async def speak(self, text: str, source: str = "local"):
        """
        Convert text to speech and play it
        Uses Redis cache for common phrases
        
        Args:
            text: Text to speak
            source: Source of the request (e.g., 'local', 'web')
        """
        if not text or source == "web_text":
            return

        generation = getattr(self, "_speech_generation", 0)

        if self.provider == "kitten" and source == "local":
            # Generate inside the playback queue to preserve order and start
            # playing progressive PCM without awaiting the complete response.
            await self.audio_queue.put({"type": "kitten_stream", "text": text})
            return
        
        try:
            requested_at = time.perf_counter()
            logger.info(f"TTS: Speaking: '{text[:50]}...'")
            
            # Broadcast speaking status (will be done in queue processor)
            # from src.utils.websocket_broadcast import broadcast_voice_status, broadcast_message
            # await broadcast_voice_status("speaking", speaking=True)
            # await broadcast_message("assistant_speaking", {"text": text})
            
            # Try cache with proper error handling
            cached_audio = await self._get_cached_audio(text)
            if generation != getattr(self, "_speech_generation", 0):
                return
            logger.info("[TIMING] TTS cache lookup: %.0f ms | provider=%s hit=%s",
                        (time.perf_counter() - requested_at) * 1000, self.provider, bool(cached_audio))
            
            if cached_audio:
                logger.debug("TTS: Using cached audio")
                # Queue for playback
                await self.audio_queue.put({
                    "type": "speak",
                    "data": cached_audio,
                    "text": text,
                    "source": source,
                    "requested_at": requested_at,
                })
            else:
                logger.debug("TTS: Generating new audio")
                # Try online generation first, fallback to offline
                audio_data = None
                cache_generated_audio = True
                generation_started_at = time.perf_counter()
                try:
                    # Use appropriate provider
                    if self.provider == "kitten":
                        from src.speech.kitten_client import KittenClient
                        audio_data = await KittenClient(self.settings.speech).speech(text)
                    elif self.provider == "google":
                        audio_data = await self._generate_google_speech(text)
                    elif self.provider == "edge":
                        audio_data = await self._generate_speech(text)
                    else:  # offline
                        audio_data = await self._generate_offline_speech(text)
                except Exception as e:
                    if generation != getattr(self, "_speech_generation", 0):
                        return
                    if self.provider == "kitten" and not self.settings.speech.kitten_fallback:
                        raise
                    error_str = str(e)
                    if "getaddrinfo failed" in error_str or "Cannot connect" in error_str:
                        logger.warning(f"TTS: {self.provider.upper()} unavailable (network issue), using offline TTS")
                    else:
                        logger.warning(f"TTS: {self.provider.upper()} failed, trying offline fallback: {e}")
                    
                    try:
                        cache_generated_audio = False
                        audio_data = await self._generate_offline_speech(text)
                    except Exception as offline_e:
                        logger.error(f"TTS: Offline fallback also failed: {offline_e}")
                
                if generation != getattr(self, "_speech_generation", 0):
                    return
                if audio_data:
                    logger.info("[TIMING] TTS generation: %.0f ms | provider=%s",
                                (time.perf_counter() - generation_started_at) * 1000, self.provider)
                    # Audio is ready. Playback need not wait for Redis writes;
                    # still await persistence here so caching is not abandoned.
                    await self.audio_queue.put({
                        "type": "speak",
                        "data": audio_data,
                        "text": text,
                        "source": source,
                        "requested_at": requested_at,
                    })
                    cache_started_at = time.perf_counter()
                    if cache_generated_audio:
                        await self._cache_audio(text, audio_data)
                    logger.info("[TIMING] TTS cache save (overlaps playback): %.0f ms",
                                (time.perf_counter() - cache_started_at) * 1000)
                else:
                    raise ValueError("TTS generation failed (both online and offline)")
                
        except Exception as e:
            logger.error(f"TTS error: {e}")
            print(f"[TTS ERROR]: {text}")
            # Broadcast idle on error
            from src.utils.websocket_broadcast import broadcast_voice_status
            await broadcast_voice_status("idle", speaking=False)
    
    async def _get_cached_audio(self, text: str) -> Optional[bytes]:
        """Get cached audio with proper error handling"""
        try:
            redis = await get_redis_client()
            audio = await redis.get_tts_audio(self._cache_key(text))
            if audio:
                key = "tts:words:" + hashlib.sha256(audio).hexdigest()
                raw = await redis.get(key)
                if raw:
                    words = json.loads(raw)
                    if not isinstance(words, list) or any(
                        not isinstance(word, dict)
                        or not isinstance(word.get("text"), str)
                        or not isinstance(word.get("start"), (int, float))
                        or not isinstance(word.get("end"), (int, float))
                        or not math.isfinite(word["start"])
                        or not math.isfinite(word["end"])
                        or not 0 <= word["start"] <= word["end"]
                        for word in words
                    ):
                        raise ValueError("Invalid cached word timings")
                    self._remember_timings(audio, words)
                elif self.provider == "edge" and audio[:4] != b"RIFF":
                    # Old audio has no boundaries. Regenerate once to populate them.
                    return None
            return audio
        except Exception as e:
            logger.debug(f"Cache read failed (non-critical): {e}")
            return None
    
    async def _cache_audio(self, text: str, audio_data: bytes):
        """Cache audio in background with error handling"""
        try:
            redis = await get_redis_client()
            await redis.cache_tts_audio(self._cache_key(text), audio_data)
            words = self._timings_for(audio_data)
            if words:
                await redis.set("tts:words:" + hashlib.sha256(audio_data).hexdigest(),
                                json.dumps(words), ttl=self.settings.cache.ttl_tts_audio)
            logger.debug(f"TTS: Cached audio for: '{text[:30]}...'")
        except Exception as e:
            logger.debug(f"Cache write failed (non-critical): {e}")
    
    def _cache_key(self, text: str) -> str:
        # Prevent old Edge/Google audio from masking the selected experiment.
        if self.provider == "kitten":
            speech = self.settings.speech
            return f"kitten:{speech.kitten_tts_model}:{speech.kitten_tts_voice}:{speech.kitten_tts_speed}:{text}"
        if self.provider == "edge":
            identity = [self.provider, getattr(self, "voice_id", ""), self._edge_rate()]
        elif self.provider == "google":
            identity = [self.provider, getattr(self, "google_voice", ""),
                        getattr(self, "google_pitch", 0), getattr(self, "google_speaking_rate", 1)]
        else:
            identity = [self.provider, getattr(self, "voice_id", ""), getattr(self, "rate", 1)]
        digest = hashlib.sha256(json.dumps([identity, text]).encode("utf-8")).hexdigest()
        return f"tts:v2:{digest}"

    def _edge_rate(self) -> str:
        rate = getattr(self, "rate", 1)
        return "+25%" if rate > 1.2 else "+5%" if rate < 0.8 else "+15%"

    async def _play_kitten_stream(self, text: str):
        from src.speech.kitten_client import KittenClient, PCM_RATE
        from src.speech.playback_events import register_playback
        from src.utils.websocket_broadcast import broadcast_message, broadcast_voice_status
        import sounddevice as sd

        self._stream_stop.clear()
        playback = register_playback(text, [], "local")
        self._active_playback = playback
        paused = self._pause_wake_word_detection()
        started = False
        stream = None
        pending = bytearray()
        position = 0.0
        began = asyncio.get_running_loop().time()
        try:
            await broadcast_voice_status("processing", speaking=False, active=True)
            async for chunk in KittenClient(self.settings.speech).speech_pcm(text):
                if self._stream_stop.is_set():
                    return
                pending.extend(chunk)
                # 350ms initial buffer tolerates progressive inference jitter.
                threshold = int(PCM_RATE * 2 * (.35 if not started else .1))
                if len(pending) < threshold:
                    continue
                if stream is None:
                    stream = sd.RawOutputStream(samplerate=PCM_RATE, channels=1, dtype="int16")
                    await asyncio.to_thread(stream.start)
                    self._pcm_stream = stream
                if not started:
                    started = True
                    logger.info("[TIMING] Kitten first playback: %.0f ms", (asyncio.get_running_loop().time() - began) * 1000)
                    await broadcast_message("assistant_speaking", playback)
                    await broadcast_voice_status("speaking", speaking=True, active=True)
                data = bytes(pending)
                pending.clear()
                await asyncio.to_thread(stream.write, data)
                position += len(data) / (PCM_RATE * 2)
                await broadcast_message("tts_progress", {**playback, "position": position, "state": "progress"})
            if pending and not self._stream_stop.is_set():
                if stream is None:
                    stream = sd.RawOutputStream(samplerate=PCM_RATE, channels=1, dtype="int16")
                    await asyncio.to_thread(stream.start)
                    self._pcm_stream = stream
                    started = True
                    await broadcast_message("assistant_speaking", playback)
                    await broadcast_voice_status("speaking", speaking=True, active=True)
                await asyncio.to_thread(stream.write, bytes(pending))
        except Exception as exc:
            logger.warning("Kitten streaming playback failed (%s)", type(exc).__name__)
            # Never repeat a sentence already partially spoken.
            if not started and not self._stream_stop.is_set() and self.settings.speech.kitten_fallback:
                audio = await self._generate_speech(text)
                await broadcast_message("assistant_speaking", playback)
                await broadcast_voice_status("speaking", speaking=True, active=True)
                await self._play_audio_data(audio)
        finally:
            if stream is not None:
                with suppress(Exception):
                    await asyncio.to_thread(stream.stop)
                with suppress(Exception):
                    await asyncio.to_thread(stream.close)
            self._pcm_stream = None
            self._resume_wake_word_detection(paused)
            await broadcast_message("tts_progress", {**playback, "position": position, "state": "ended"})
            await broadcast_voice_status("idle", speaking=False)

    def _remember_timings(self, audio: bytes, words: list):
        if not hasattr(self, "_word_timings"):
            self._word_timings = OrderedDict()
        key = hashlib.sha256(audio).hexdigest()
        self._word_timings[key] = words
        self._word_timings.move_to_end(key)
        while len(self._word_timings) > 64:
            self._word_timings.popitem(last=False)

    def _timings_for(self, audio: bytes) -> list:
        return getattr(self, "_word_timings", {}).get(hashlib.sha256(audio).hexdigest(), [])

    async def _generate_speech(self, text: str) -> bytes:
        """Generate speech audio using edge-tts"""
        try:
            # Calculate rate parameter
            rate_value = self._edge_rate()
            
            # Generate audio
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice_id,
                rate=rate_value,
                boundary="WordBoundary",
            )
            
            # Save to temporary file
            audio_data = bytearray()
            words = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.extend(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    words.append({"text": chunk["text"], "start": chunk["offset"] / 10_000_000,
                                  "end": (chunk["offset"] + chunk["duration"]) / 10_000_000})
            
            if not audio_data:
                raise ValueError("No audio data generated by Edge TTS")
            
            audio_data = bytes(audio_data)
            self._remember_timings(audio_data, words)
            return audio_data
            
        except Exception as e:
            # Provide more specific error messages
            error_msg = str(e)
            if "getaddrinfo failed" in error_msg or "Cannot connect" in error_msg:
                logger.error(f"Edge TTS network error (check internet connection): {e}")
            elif "No audio was received" in error_msg:
                logger.error(f"Edge TTS returned no audio (voice: {self.voice_id}): {e}")
            else:
                logger.error(f"Edge TTS generation error: {e}")
            raise
    
    async def _generate_google_speech(self, text: str) -> bytes:
        """Generate speech audio using Google Cloud TTS with Chirp 3 HD voices"""
        try:
            from google.cloud import texttospeech
            
            if not self.google_client:
                raise ValueError("Google TTS client not initialized")
            
            # Set up the synthesis request
            synthesis_input = texttospeech.SynthesisInput(text=text)
            
            # Build the voice parameters
            voice = texttospeech.VoiceSelectionParams(
                name=self.google_voice,
                language_code=self.google_voice[:5]  # Extract language code (e.g., en-US)
            )
            
            # Configure audio format
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=self.google_speaking_rate,
                pitch=self.google_pitch
            )
            
            # Run the synchronous API call in a thread to avoid blocking
            response = await asyncio.to_thread(
                lambda: self.google_client.synthesize_speech(
                    input=synthesis_input,
                    voice=voice,
                    audio_config=audio_config
                )
            )
            
            if not response.audio_content:
                raise ValueError("No audio data generated by Google TTS")
            
            logger.debug(f"Google TTS: Generated {len(response.audio_content)} bytes for '{text[:30]}...'")
            return response.audio_content
            
        except Exception as e:
            error_msg = str(e)
            if "permission" in error_msg.lower() or "credentials" in error_msg.lower():
                logger.error(f"Google TTS authentication error: {e}")
            elif "quota" in error_msg.lower():
                logger.error(f"Google TTS quota exceeded: {e}")
            else:
                logger.error(f"Google TTS generation error: {e}")
            raise
    
    async def _generate_offline_speech(self, text: str) -> bytes:
        """
        Generate speech using offline pyttsx3 engine via subprocess
        Using subprocess ensures isolation and prevents blocking the async loop
        """
        try:
            logger.info(f"TTS: Generating offline speech for: '{text[:30]}...'")
            
            import uuid
            output_file = os.path.join(self.temp_dir, f"offline_tts_{uuid.uuid4().hex}.wav")
            script_path = os.path.join(os.path.dirname(__file__), "offline_tts_generator.py")
            if not os.path.exists(script_path):
                 # Fallback path if running from root
                 script_path = os.path.abspath("src/speech/offline_tts_generator.py")
            
            # Windows: Run subprocess in thread
            def run_subprocess():
                result = subprocess.run(
                    [sys.executable, script_path, text, output_file],
                    capture_output=True,
                    text=False,
                    timeout=30
                )
                return result
            
            result = await asyncio.to_thread(run_subprocess)
            
            if result.stdout:
                logger.debug(f"Offline TTS stdout: {result.stdout.decode()}")
            
            if result.returncode != 0:
                error_msg = result.stderr.decode() if result.stderr else "Unknown error"
                logger.error(f"Offline TTS subprocess failed with code {result.returncode}: {error_msg}")
                return None
            
            if result.stderr:
                logger.debug(f"Offline TTS stderr: {result.stderr.decode()}")
            
            # Read the generated file
            if os.path.exists(output_file):
                with open(output_file, "rb") as f:
                    audio_data = f.read()
                
                # Cleanup
                try:
                    os.remove(output_file)
                except:
                    pass
                    
                return audio_data
            else:
                logger.error("Offline TTS output file not found")
                return None
                
        except Exception as e:
            logger.error(f"Offline TTS wrapper failed: {e}", exc_info=True)
            return None
    
    async def _play_audio_data(self, audio_data: bytes, source: str = "local"):
        """Play audio data using pygame and broadcast to web clients"""
        playback_generation = getattr(self, "_speech_generation", 0)
        
        # Broadcast audio to all connected web clients via WebSocket
        try:
            from src.api.server import broadcast_update
            import base64
            
            # Encode audio to base64
            audio_b64 = base64.b64encode(audio_data).decode('utf-8')
            
            # Detect format
            is_wav = audio_data[:4] == b'RIFF'
            mime_type = "audio/wav" if is_wav else "audio/mpeg"
            
            # Create data URI
            data_uri = f"data:{mime_type};base64,{audio_b64}"
            
            await broadcast_update("tts_audio", {
                "audio_uri": data_uri,
                **getattr(self, "_active_playback", {}),
            })
            logger.info("Broadcasted TTS audio to web clients")
        except Exception as e:
            logger.error(f"Failed to broadcast TTS audio: {e}")

        if playback_generation != getattr(self, "_speech_generation", 0):
            return

        if source == "web":
            logger.info("TTS: Skipping local playback because request originated from web dashboard")
            return

        if not _ensure_mixer():
            logger.error("Pygame not available for local audio playback")
            return

        temp_file = None
        loaded = False
        try:
            # Save to temporary file
            import uuid
            
            # Detect file format by checking header bytes
            # MP3 files start with 'ID3' or 0xFF 0xFB (MPEG sync)
            # WAV files start with 'RIFF'
            is_wav = audio_data[:4] == b'RIFF'
            extension = '.wav' if is_wav else '.mp3'
            
            temp_file = os.path.join(self.temp_dir, f"tts_{uuid.uuid4().hex}{extension}")
            
            with open(temp_file, 'wb') as f:
                f.write(audio_data)
            
            # Play using pygame
            from src.utils.audio_lock import AUDIO_DEVICE_LOCK
            with AUDIO_DEVICE_LOCK:
                if playback_generation != getattr(self, "_speech_generation", 0):
                    return
                pygame.mixer.music.load(temp_file)
                loaded = True
                pygame.mixer.music.play()
            requested_at = getattr(self, "_active_speech_requested_at", None)
            if requested_at is not None:
                logger.info("[TIMING] TTS first local playback: %.0f ms | provider=%s",
                            (time.perf_counter() - requested_at) * 1000, self.provider)
            
            # Wait for playback to finish
            from src.utils.websocket_broadcast import broadcast_message
            while pygame.mixer.music.get_busy():
                await broadcast_message("tts_progress", {
                    "speech_id": getattr(self, "_active_playback", {}).get("speech_id"),
                    "source": source,
                    "position": max(0, pygame.mixer.music.get_pos()) / 1000,
                    "state": "progress",
                })
                await asyncio.sleep(0.05)
            
        except Exception as e:
            logger.error(f"TTS playback error: {e}")
        finally:
            # Windows keeps a loaded music file open until it is unloaded.
            if loaded:
                with suppress(Exception):
                    from src.utils.audio_lock import AUDIO_DEVICE_LOCK
                    with AUDIO_DEVICE_LOCK:
                        pygame.mixer.music.stop()
                        pygame.mixer.music.unload()
            if temp_file:
                with suppress(OSError):
                    os.remove(temp_file)
    
    async def play_sound(self, sound_name: str):
        """Play a sound effect"""
        try:
            # Try both .mp3 and .MP3 extensions
            sound_path = resource_path("sounds", f"{sound_name}.mp3")
            if not sound_path.exists():
                sound_path = resource_path("sounds", f"{sound_name}.MP3")
            
            if sound_path.exists():
                # Queue the sound
                await self.audio_queue.put({
                    "type": "sound",
                    "path": str(sound_path)
                })
                logger.debug(f"TTS: Queued sound: {sound_name}")
            else:
                logger.warning(f"TTS: Sound not found: {sound_name}")
                
        except Exception as e:
            logger.error(f"TTS: Error queuing sound: {e}")

    async def play_sound_now(self, sound_name: str) -> bool:
        """Play a sound effect immediately and wait for it to finish."""
        if not _ensure_mixer():
            return False
        try:
            # Small guard: give any concurrent stop() a moment to settle
            await asyncio.sleep(0.02)

            # Use pre-loaded sound for zero-latency playback
            preloaded = self._preloaded_sounds.get(sound_name.lower())
            if preloaded:
                logger.debug(f"TTS: Playing pre-loaded sound: {sound_name}")
                from src.utils.audio_lock import AUDIO_DEVICE_LOCK
                with AUDIO_DEVICE_LOCK:
                    channel = (
                        preloaded.play(maxtime=200, fade_ms=10)
                        if sound_name.lower() == "activation" else (
                            preloaded.play(maxtime=300, fade_ms=10)
                            if sound_name.lower() in {"mmm1", "mmm2"} else preloaded.play()
                        )
                    )
                if channel:
                    while channel.get_busy():
                        await asyncio.sleep(0.05)
                    return True
                return False

            # Fallback to disk loading for non-preloaded sounds
            if sound_name.lower() == "activation":
                # Never fall back to the voice-like activation MP3.
                return False
            sound_path = resource_path("sounds", f"{sound_name}.mp3")
            if not sound_path.exists():
                sound_path = resource_path("sounds", f"{sound_name}.MP3")

            if sound_path.exists():
                logger.debug(f"TTS: Playing sound now (from disk): {sound_name}")
                return await self._play_sound_file(str(sound_path))
            else:
                logger.warning(f"TTS: Sound not found: {sound_name}")
                return False
        except Exception as e:
            logger.error(f"TTS: Error playing sound immediately: {e}")
            return False

    async def _play_sound_file(self, sound_path: str) -> bool:
        """Internal method to play sound file and wait"""
        if not _ensure_mixer():
            return False
            
        try:
            stem = os.path.splitext(os.path.basename(sound_path))[0].lower()
            sound = self._preloaded_sounds.get(stem)

            if not sound:
                if stem == "activation":
                    return False
                sound = pygame.mixer.Sound(sound_path)
                sound.set_volume(0.6)
            
            from src.utils.audio_lock import AUDIO_DEVICE_LOCK
            with AUDIO_DEVICE_LOCK:
                channel = (
                    sound.play(maxtime=200, fade_ms=10)
                    if stem == "activation" else (
                        sound.play(maxtime=300, fade_ms=10)
                        if stem in {"mmm1", "mmm2"} else sound.play()
                    )
                )
            
            if channel:
                while channel.get_busy():
                    await asyncio.sleep(0.05)
                return True
            return False
        except Exception as e:
            logger.error(f"Error playing sound file: {e}")
            return False
            
    def stop(self):
        """Stop current playback and clear the queue (Barge-in / Interruption)"""
        logger.info("TTS: Stop requested (Barge-in)")
        self.stop_playback_now()
        from src.speech.playback_events import cancel_playback
        cancel_playback(getattr(self, "_active_playback", {}).get("speech_id", ""))

        if _ensure_mixer():
            from src.utils.audio_lock import AUDIO_DEVICE_LOCK
            with AUDIO_DEVICE_LOCK:
                try:
                    pygame.mixer.music.stop()
                except Exception as e:
                    logger.debug(f"TTS: Error stopping music: {e}")

        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
            except asyncio.QueueEmpty:
                break

    def stop_playback_now(self):
        """Thread-friendly immediate audio stop for global hotkey callbacks."""
        # Invalidate requests still awaiting Redis or synthesis as well as
        # stopping audio already playing. Late replies must not reappear.
        self._speech_generation = getattr(self, "_speech_generation", 0) + 1
        if hasattr(self, "_stream_stop"):
            self._stream_stop.set()
        task = getattr(self, "_active_stream_task", None)
        if task is not None and not task.done():
            task.get_loop().call_soon_threadsafe(task.cancel)
        stream = getattr(self, "_pcm_stream", None)
        if stream is not None:
            try:
                stream.abort()
            except Exception:
                pass
        from src.speech.playback_events import cancel_playback
        cancel_playback(getattr(self, "_active_playback", {}).get("speech_id", ""))
        if not _ensure_mixer():
            return

        from src.utils.audio_lock import AUDIO_DEVICE_LOCK
        with AUDIO_DEVICE_LOCK:
            try:
                pygame.mixer.music.stop()
            except Exception as e:
                logger.debug(f"TTS: Error stopping music immediately: {e}")
    
    async def wait_until_done(self, timeout: float = 10.0):
        """Wait for all queued audio to finish playing"""
        loop = asyncio.get_running_loop()
        start = loop.time()
        while True:
            # Check if queue is empty and not processing
            if self.audio_queue.empty() and not self.is_processing:
                return True
            
            # Check timeout
            if loop.time() - start > timeout:
                logger.warning(f"TTS wait timed out after {timeout}s")
                return False
            
            await asyncio.sleep(0.1)


# Global instance
_tts_engine: Optional[TTSEngine] = None


def get_tts_engine() -> TTSEngine:
    """Get or create global TTS engine"""
    global _tts_engine
    if _tts_engine is None:
        _tts_engine = TTSEngine()
    return _tts_engine


def reset_tts_engine() -> None:
    global _tts_engine
    _tts_engine = None
