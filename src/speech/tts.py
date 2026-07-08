"""
Text-to-Speech (TTS) System with Caching
Migrated and enhanced from original voice_system.py
Supports multiple TTS providers: Edge TTS, Google Chirp 3 HD, and offline pyttsx3
"""
import asyncio
import hashlib
import logging
import os
import tempfile
from typing import Optional
import edge_tts
import pygame
import subprocess
import sys

from src.database.redis_client import get_redis_client
from src.utils.config import get_settings
from src.utils.logger import get_logger
from src.utils.paths import resource_path

logger = get_logger(__name__)

# Initialize pygame mixer
try:
    pygame.mixer.init()
    PYGAME_AVAILABLE = True
except Exception as e:
    logger.warning(f"Pygame mixer init failed: {e}")
    PYGAME_AVAILABLE = False


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
        if not PYGAME_AVAILABLE:
            return
        common_sounds = ["activation", "mmm1", "mmm2", "error", "success"]
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
                    
                    if task_type == "speak":
                        audio_data = task.get("data")
                        text = task.get("text")
                        
                        # Broadcast speaking status
                        from src.utils.websocket_broadcast import broadcast_voice_status, broadcast_message
                        await broadcast_voice_status("speaking", speaking=True)
                        if text:
                            await broadcast_message("assistant_speaking", {"text": text})

                        wake_word_paused = self._pause_wake_word_detection()
                        try:
                            # Play
                            await self._play_audio_data(audio_data)
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
    
    async def speak(self, text: str):
        """
        Convert text to speech and play it
        Uses Redis cache for common phrases
        
        Args:
            text: Text to speak
        """
        if not text:
            return
        
        try:
            logger.info(f"TTS: Speaking: '{text[:50]}...'")
            
            # Broadcast speaking status (will be done in queue processor)
            # from src.utils.websocket_broadcast import broadcast_voice_status, broadcast_message
            # await broadcast_voice_status("speaking", speaking=True)
            # await broadcast_message("assistant_speaking", {"text": text})
            
            # Try cache with proper error handling
            cached_audio = await self._get_cached_audio(text)
            
            if cached_audio:
                logger.debug("TTS: Using cached audio")
                # Queue for playback
                await self.audio_queue.put({
                    "type": "speak",
                    "data": cached_audio,
                    "text": text
                })
            else:
                logger.debug("TTS: Generating new audio")
                # Try online generation first, fallback to offline
                audio_data = None
                try:
                    # Use appropriate provider
                    if self.provider == "google":
                        audio_data = await self._generate_google_speech(text)
                    elif self.provider == "edge":
                        audio_data = await self._generate_speech(text)
                    else:  # offline
                        audio_data = await self._generate_offline_speech(text)
                except Exception as e:
                    error_str = str(e)
                    if "getaddrinfo failed" in error_str or "Cannot connect" in error_str:
                        logger.warning(f"TTS: {self.provider.upper()} unavailable (network issue), using offline TTS")
                    else:
                        logger.warning(f"TTS: {self.provider.upper()} failed, trying offline fallback: {e}")
                    
                    try:
                        audio_data = await self._generate_offline_speech(text)
                    except Exception as offline_e:
                        logger.error(f"TTS: Offline fallback also failed: {offline_e}")
                
                if audio_data:
                    # Cache in background
                    asyncio.create_task(self._cache_audio(text, audio_data))
                    
                    # Queue for playback
                    await self.audio_queue.put({
                        "type": "speak",
                        "data": audio_data,
                        "text": text
                    })
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
            return await redis.get_tts_audio(text)
        except Exception as e:
            logger.debug(f"Cache read failed (non-critical): {e}")
            return None
    
    async def _cache_audio(self, text: str, audio_data: bytes):
        """Cache audio in background with error handling"""
        try:
            redis = await get_redis_client()
            await redis.cache_tts_audio(text, audio_data)
            logger.debug(f"TTS: Cached audio for: '{text[:30]}...'")
        except Exception as e:
            logger.debug(f"Cache write failed (non-critical): {e}")
    
    async def _generate_speech(self, text: str) -> bytes:
        """Generate speech audio using edge-tts"""
        try:
            # Calculate rate parameter
            rate_value = "+15%"
            if self.rate > 1.2:
                rate_value = "+25%"
            elif self.rate < 0.8:
                rate_value = "+5%"
            
            # Generate audio
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice_id,
                rate=rate_value
            )
            
            # Save to temporary file
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            
            if not audio_data:
                raise ValueError("No audio data generated by Edge TTS")
            
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
    
    async def _play_audio_data(self, audio_data: bytes):
        """Play audio data using pygame"""
        if not PYGAME_AVAILABLE:
            logger.error("Pygame not available for audio playback")
            return
        
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
            pygame.mixer.music.load(temp_file)
            pygame.mixer.music.play()
            
            # Wait for playback to finish
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.1)
            
            # Cleanup
            try:
                os.remove(temp_file)
            except:
                pass
                
        except Exception as e:
            logger.error(f"TTS playback error: {e}")
    
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

    async def play_sound_now(self, sound_name: str):
        """Play a sound effect immediately and wait for it to finish."""
        try:
            # Use pre-loaded sound for zero-latency playback
            preloaded = self._preloaded_sounds.get(sound_name.lower())
            if preloaded:
                logger.debug(f"TTS: Playing pre-loaded sound: {sound_name}")
                channel = preloaded.play()
                if channel:
                    while channel.get_busy():
                        await asyncio.sleep(0.05)
                return

            # Fallback to disk loading for non-preloaded sounds
            sound_path = resource_path("sounds", f"{sound_name}.mp3")
            if not sound_path.exists():
                sound_path = resource_path("sounds", f"{sound_name}.MP3")

            if sound_path.exists():
                logger.debug(f"TTS: Playing sound now (from disk): {sound_name}")
                await self._play_sound_file(str(sound_path))
            else:
                logger.warning(f"TTS: Sound not found: {sound_name}")
        except Exception as e:
            logger.error(f"TTS: Error playing sound immediately: {e}")

    async def _play_sound_file(self, sound_path: str):
        """Internal method to play sound file and wait"""
        if not PYGAME_AVAILABLE:
            return
            
        try:
            # Check preloaded cache by filename stem
            stem = os.path.splitext(os.path.basename(sound_path))[0].lower()
            sound = self._preloaded_sounds.get(stem)

            if not sound:
                sound = pygame.mixer.Sound(sound_path)
                sound.set_volume(0.6)
            
            # Sound.play returns a Channel
            channel = sound.play()
            
            # Wait for channel to finish (reduced from 100ms to 50ms for snappier response)
            if channel:
                while channel.get_busy():
                    await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Error playing sound file: {e}")
            
    def stop(self):
        """Stop current playback and clear the queue (Barge-in / Interruption)"""
        logger.info("TTS: Stop requested (Barge-in)")

        # 1. Stop current audio — music track AND all Sound channels.
        # Previously only music.stop() was called, leaving sound-effect channels
        # (pygame.mixer.Sound) running even after a barge-in.
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.music.stop()
            except Exception as e:
                logger.debug(f"TTS: Error stopping music: {e}")
            try:
                pygame.mixer.stop()   # stops all active Sound channels
            except Exception as e:
                logger.debug(f"TTS: Error stopping channels: {e}")

        # 2. Clear the pending-speech queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
            except asyncio.QueueEmpty:
                break

    def stop_playback_now(self):
        """Thread-friendly immediate audio stop for global hotkey callbacks."""
        if not PYGAME_AVAILABLE:
            return

        try:
            pygame.mixer.music.stop()
        except Exception as e:
            logger.debug(f"TTS: Error stopping music immediately: {e}")
        try:
            pygame.mixer.stop()
        except Exception as e:
            logger.debug(f"TTS: Error stopping channels immediately: {e}")
    
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




