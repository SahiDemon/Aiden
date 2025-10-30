"""
Speech-to-Text (STT) System with Caching
Migrated and enhanced from original speech_recognition_system.py
"""
import asyncio
import logging
from typing import Optional, Tuple
import speech_recognition as sr

from src.database.redis_client import get_redis_client
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class STTEngine:
    """
    Speech-to-Text engine with Redis caching and concurrent processing
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.recognizer = sr.Recognizer()
        
        # Configure from settings
        self.language = self.settings.speech.stt_language
        self.timeout = self.settings.speech.stt_timeout
        self.energy_threshold = self.settings.speech.stt_energy_threshold
        self.pause_threshold = self.settings.speech.stt_pause_threshold
        
        # Apply configuration
        self.recognizer.energy_threshold = self.energy_threshold
        self.recognizer.pause_threshold = 0.5  # FASTER: Stop recording after 0.5s of silence
        self.recognizer.phrase_threshold = 0.2  # FASTER: Minimum 0.2s phrase
        self.recognizer.dynamic_energy_threshold = False
        self.recognizer.non_speaking_duration = 0.3  # FASTER: Detect end of speech quickly
        
        logger.info(f"STT Engine initialized: energy={self.energy_threshold}, pause={self.pause_threshold}")
    
    async def transcribe(self, play_activation_sound: bool = True) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Listen and transcribe speech to text
        
        Args:
            play_activation_sound: Whether to play activation sound when mic starts
        
        Returns:
            Tuple of (success, text, error_message)
        """
        try:
            # Broadcast listening status
            try:
                from src.utils.websocket_broadcast import broadcast_voice_status
                await broadcast_voice_status("listening", speaking=False)
            except Exception:
                pass  # Non-critical
            
            # Play activation sound RIGHT when mic is about to listen
            if play_activation_sound:
                from src.speech.tts import get_tts_engine
                tts = get_tts_engine()
                await tts.play_sound("activation")
            
            # Run blocking listen operation in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._listen_sync)
            
            # Broadcast idle status after listening completes
            try:
                from src.utils.websocket_broadcast import broadcast_voice_status
                await broadcast_voice_status("idle", speaking=False)
            except Exception:
                pass
            
            return result
            
        except Exception as e:
            logger.error(f"STT error: {e}")
            # Broadcast idle on error
            try:
                from src.utils.websocket_broadcast import broadcast_voice_status
                await broadcast_voice_status("idle", speaking=False)
            except Exception:
                pass
            return False, None, str(e)
    
    def _listen_sync(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """Synchronous listen operation (runs in thread pool)"""
        try:
            with sr.Microphone() as source:
                logger.debug("STT: Microphone ready")
                
                # Listen for audio
                try:
                    # FASTER: 5 second max recording time
                    audio = self.recognizer.listen(source, timeout=self.timeout, phrase_time_limit=5)
                    logger.debug("STT: Audio captured")
                except sr.WaitTimeoutError:
                    logger.info("STT: Timeout - no speech detected")
                    return False, None, "timeout"
                
                # Recognize speech
                try:
                    text = self.recognizer.recognize_google(audio, language=self.language)
                    
                    if text:
                        logger.info(f"STT: Recognized: '{text}'")
                        return True, text, None
                    else:
                        logger.warning("STT: Empty recognition result")
                        return False, None, "No speech detected"
                        
                except sr.UnknownValueError:
                    logger.warning("STT: Could not understand audio")
                    return False, None, "Could not understand speech"
                    
                except sr.RequestError as e:
                    logger.error(f"STT: API error: {e}")
                    return False, None, f"Speech service error: {str(e)}"
                    
        except Exception as e:
            logger.error(f"STT: Exception: {e}")
            return False, None, str(e)
    
    def adjust_for_ambient_noise(self, duration: float = 1.0):
        """Adjust for ambient noise (run once at startup)"""
        try:
            with sr.Microphone() as source:
                logger.info(f"STT: Adjusting for ambient noise ({duration}s)...")
                self.recognizer.adjust_for_ambient_noise(source, duration=duration)
                logger.info(f"STT: Adjusted energy threshold to {self.recognizer.energy_threshold}")
        except Exception as e:
            logger.error(f"STT: Error adjusting for ambient noise: {e}")


# Global instance
_stt_engine: Optional[STTEngine] = None


def get_stt_engine() -> STTEngine:
    """Get or create global STT engine"""
    global _stt_engine
    if _stt_engine is None:
        _stt_engine = STTEngine()
    return _stt_engine



