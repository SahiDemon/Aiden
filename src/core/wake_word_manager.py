"""
Wake Word Manager
Manages wake word listening state with toggle functionality
"""
import asyncio
import logging
from typing import Optional

from src.speech.tts import get_tts_engine
from src.utils.logger import get_logger

logger = get_logger(__name__)


class WakeWordManager:
    """
    Manages wake word detector state
    Provides toggle functionality and TTS feedback
    """
    
    def __init__(self, wake_word_detector):
        """
        Initialize wake word manager
        
        Args:
            wake_word_detector: The wake word detector instance to manage
        """
        self.detector = wake_word_detector
        self.is_enabled = True  # Start enabled by default
        self.tts = get_tts_engine()
        
        logger.info("Wake word manager initialized")
    
    async def toggle(self) -> bool:
        """
        Toggle wake word listening on/off
        
        Returns:
            New state (True = enabled, False = disabled)
        """
        try:
            if self.is_enabled:
                # Disable wake word listening
                await self.disable()
            else:
                # Enable wake word listening
                await self.enable()
            
            return self.is_enabled
            
        except Exception as e:
            logger.error(f"Error toggling wake word: {e}")
            return self.is_enabled
    
    async def disable(self):
        """Disable wake word listening"""
        try:
            logger.info("Disabling wake word listening...")
            self.is_enabled = False
            
            # Pause the detector
            if self.detector:
                self.detector.pause()
            
            # Announce via TTS
            await self.tts.speak("Wake word has been disabled")
            
            logger.info("✅ Wake word listening disabled")
            
        except Exception as e:
            logger.error(f"Error disabling wake word: {e}")
    
    async def enable(self):
        """Enable wake word listening"""
        try:
            logger.info("Enabling wake word listening...")
            self.is_enabled = True
            
            # Resume the detector
            if self.detector:
                self.detector.resume()
            
            # Announce via TTS
            await self.tts.speak("Wake word has been enabled")
            
            logger.info("✅ Wake word listening enabled")
            
        except Exception as e:
            logger.error(f"Error enabling wake word: {e}")
    
    def get_state(self) -> bool:
        """Get current state"""
        return self.is_enabled


# Global instance
_wake_word_manager: Optional[WakeWordManager] = None


def get_wake_word_manager(wake_word_detector=None) -> WakeWordManager:
    """Get or create global wake word manager"""
    global _wake_word_manager
    if _wake_word_manager is None and wake_word_detector is not None:
        _wake_word_manager = WakeWordManager(wake_word_detector)
    return _wake_word_manager




