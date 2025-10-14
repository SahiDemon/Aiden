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
        
        logger.info(f"TTS Engine initialized: voice={self.voice_id}, rate={self.rate}")
    
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
            
            # Check cache first
            redis = await get_redis_client()
            cached_audio = await redis.get_tts_audio(text)
            
            if cached_audio:
                logger.debug("TTS: Using cached audio")
                await self._play_audio_data(cached_audio)
            else:
                logger.debug("TTS: Generating new audio")
                audio_data = await self._generate_speech(text)
                
                # Cache for future use
                await redis.cache_tts_audio(text, audio_data)
                
                # Play the audio
                await self._play_audio_data(audio_data)
                
        except Exception as e:
            logger.error(f"TTS error: {e}")
            print(f"[TTS ERROR]: {text}")
    
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
            
            return audio_data
            
        except Exception as e:
            logger.error(f"TTS generation error: {e}")
            raise
    
    async def _play_audio_data(self, audio_data: bytes):
        """Play audio data using pygame"""
        if not PYGAME_AVAILABLE:
            logger.error("Pygame not available for audio playback")
            return
        
        try:
            # Save to temporary file
            import uuid
            temp_file = os.path.join(self.temp_dir, f"tts_{uuid.uuid4().hex}.mp3")
            
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
            sound_path = os.path.join("sounds", f"{sound_name}.mp3")
            
            if os.path.exists(sound_path) and PYGAME_AVAILABLE:
                sound = pygame.mixer.Sound(sound_path)
                sound.set_volume(0.6)
                sound.play()
                logger.debug(f"TTS: Played sound: {sound_name}")
            else:
                logger.warning(f"TTS: Sound not found: {sound_path}")
                
        except Exception as e:
            logger.error(f"TTS: Error playing sound: {e}")


# Global instance
_tts_engine: Optional[TTSEngine] = None


def get_tts_engine() -> TTSEngine:
    """Get or create global TTS engine"""
    global _tts_engine
    if _tts_engine is None:
        _tts_engine = TTSEngine()
    return _tts_engine





