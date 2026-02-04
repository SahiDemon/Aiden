"""
Text-to-Speech (TTS) System with Caching
Migrated and enhanced from original voice_system.py
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
    Uses Microsoft edge-tts for high-quality voices
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.voice_id = self.settings.speech.tts_voice
        self.rate = self.settings.speech.tts_rate
        self.temp_dir = tempfile.gettempdir()
        
        self.audio_queue = asyncio.Queue()
        self.is_processing = False
        
        # Start queue processor
        asyncio.create_task(self._process_queue())
        
        logger.info(f"TTS Engine initialized: voice={self.voice_id}, rate={self.rate}")

    async def _process_queue(self):
        """Process audio queue sequentially"""
        logger.info("TTS: Queue processor started")
        while True:
            try:
                task = await self.audio_queue.get()
                self.is_processing = True
                
                task_type = task.get("type")
                
                if task_type == "speak":
                    audio_data = task.get("data")
                    text = task.get("text")
                    
                    # Broadcast speaking status
                    from src.utils.websocket_broadcast import broadcast_voice_status, broadcast_message
                    await broadcast_voice_status("speaking", speaking=True)
                    if text:
                        await broadcast_message("assistant_speaking", {"text": text})
                    
                    # Play
                    await self._play_audio_data(audio_data)
                    
                    # Broadcast idle status
                    await broadcast_voice_status("idle", speaking=False)
                    
                elif task_type == "sound":
                    sound_path = task.get("path")
                    # Play sound NON-BLOCKING (fire and forget task)
                    asyncio.create_task(self._play_sound_file(sound_path))
                    # DO NOT wait here, immediately process next item in queue (which might be speech)
                    self.audio_queue.task_done()
                    continue
                
                self.audio_queue.task_done()
                
            except Exception as e:
                logger.error(f"Error in TTS queue processor: {e}")
            finally:
                self.is_processing = False
    
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
                    audio_data = await self._generate_speech(text)
                except Exception as e:
                    error_str = str(e)
                    if "getaddrinfo failed" in error_str or "Cannot connect" in error_str:
                        logger.warning(f"TTS: Edge-TTS unavailable (network issue), using offline TTS")
                    else:
                        logger.warning(f"TTS: Edge-TTS failed, trying offline fallback: {e}")
                    
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
            
            # Windows: Use ProactorEventLoop for subprocess support
            # Run in executor to avoid event loop issues
            loop = asyncio.get_event_loop()
            
            # Run the generator script using subprocess.run in executor
            def run_subprocess():
                result = subprocess.run(
                    [sys.executable, script_path, text, output_file],
                    capture_output=True,
                    text=False,
                    timeout=30
                )
                return result
            
            result = await loop.run_in_executor(None, run_subprocess)
            
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
            sound_path = os.path.join("sounds", f"{sound_name}.mp3")
            if not os.path.exists(sound_path):
                sound_path = os.path.join("sounds", f"{sound_name}.MP3")
            
            if os.path.exists(sound_path):
                # Queue the sound
                await self.audio_queue.put({
                    "type": "sound",
                    "path": sound_path
                })
                logger.debug(f"TTS: Queued sound: {sound_name}")
            else:
                logger.warning(f"TTS: Sound not found: {sound_name}")
                
        except Exception as e:
            logger.error(f"TTS: Error queuing sound: {e}")

    async def _play_sound_file(self, sound_path: str):
        """Internal method to play sound file and wait"""
        if not PYGAME_AVAILABLE:
            return
            
        try:
            sound = pygame.mixer.Sound(sound_path)
            sound.set_volume(0.6)
            
            # Sound.play returns a Channel
            channel = sound.play()
            
            # Wait for channel to finish (this task is now backgrounded by the queue processor,
            # so this await only blocks this specific sound task, not the main queue)
            if channel:
                while channel.get_busy():
                    await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Error playing sound file: {e}")
    
    async def wait_until_done(self, timeout: float = 10.0):
        """Wait for all queued audio to finish playing"""
        start = asyncio.get_event_loop().time()
        while True:
            # Check if queue is empty and not processing
            if self.audio_queue.empty() and not self.is_processing:
                return True
            
            # Check timeout
            if asyncio.get_event_loop().time() - start > timeout:
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









