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
        self.device_index = self.settings.speech.stt_device_index
        # Keep a sane minimum while still allowing quieter voices.
        self.min_energy_threshold = max(80, int(self.energy_threshold * 0.6))
        
        # Apply configuration
        # Dynamic threshold prevents getting stuck open in noisy rooms
        self.recognizer.energy_threshold = self.energy_threshold
        self.recognizer.dynamic_energy_threshold = True  # Allow adapting to fans/AC
        
        # Timing settings
        # 1.2s pause threshold allows natural pauses mid-sentence without cutting off
        self.recognizer.pause_threshold = self.pause_threshold
        self.recognizer.phrase_threshold = 0.3
        self.recognizer.non_speaking_duration = 0.5 
        
        logger.info(f"STT Engine initialized: energy={self.recognizer.energy_threshold}, dynamic={self.recognizer.dynamic_energy_threshold}")
    
    async def transcribe(self, play_activation_sound: bool = True) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Listen and transcribe speech to text
        
        Args:
            play_activation_sound: Whether to play activation sound when mic starts
        
        Returns:
            Tuple of (success, text, error_message)
        """
        try:
            # Play activation sound BEFORE opening microphone
            # This ensures user hears the sound before timeout starts
            if play_activation_sound:
                from src.speech.tts import get_tts_engine
                tts = get_tts_engine()
                await tts.play_sound("activation")
            
            # Broadcast listening status
            try:
                from src.utils.websocket_broadcast import broadcast_voice_status
                await broadcast_voice_status("listening", speaking=False)
            except Exception:
                pass  # Non-critical
            
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
            # Use microphone with max sample rate for better quality
            mic_kwargs = {"sample_rate": 48000}
            if self.device_index is not None:
                mic_kwargs["device_index"] = self.device_index
                logger.debug(f"STT: Using microphone device index {self.device_index}")
            
            with sr.Microphone(**mic_kwargs) as source:
                logger.debug("STT: Microphone ready (48kHz sample rate)")
                
                # Use 0.5s to get a reliable noise sample
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                
                # Prevent threshold from dropping too low (which causes hearing everything).
                # Use a lower configurable floor so normal speaking volume is accepted.
                if self.recognizer.energy_threshold < self.min_energy_threshold:
                    self.recognizer.energy_threshold = self.min_energy_threshold
                
                logger.debug(f"STT: Ready to listen - energy threshold={self.recognizer.energy_threshold}")
                
                # Listen for audio
                try:
                    # timeout=self.timeout applies to initial silence only
                    # phrase_time_limit=None allows natural conversation length
                    audio = self.recognizer.listen(source, timeout=self.timeout)
                    logger.debug("STT: Audio captured successfully")
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
            mic_kwargs = {}
            if self.device_index is not None:
                mic_kwargs["device_index"] = self.device_index
            
            with sr.Microphone(**mic_kwargs) as source:
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



