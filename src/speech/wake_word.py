"""
Wake Word Detection System
Migrated from efficient_wake_word.py and vosk_wake_word.py
Optimized for better performance
"""
import asyncio
import json
import logging
import os
import threading
import time
from typing import Callable, Optional
import pyaudio
import vosk

from src.speech.tts import get_tts_engine
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class WakeWordDetector:
    """
    Wake word detector using Vosk
    Optimized with better thresholds and pause/resume logic
    """
    
    def __init__(self, on_wake_word: Optional[Callable] = None):
        """
        Initialize wake word detector
        
        Args:
            on_wake_word: Callback function to call when wake word is detected
        """
        self.settings = get_settings()
        self.wake_word = self.settings.app.wake_word.lower()
        self.on_wake_word = on_wake_word
        
        # Vosk model
        self.model_path = self.settings.speech.vosk_model_path or "vosk_models/vosk-model-small-en-us-0.15"
        self.model = None
        self.recognizer = None
        
        # Audio settings
        self.audio = None
        self.stream = None
        
        # Control flags
        self.is_running = False
        self.is_paused = False
        self._thread = None
        
        logger.info(f"Wake Word Detector initialized: wake_word='{self.wake_word}', model='{self.model_path}'")
    
    def _load_model(self):
        """Load Vosk model"""
        try:
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Vosk model not found at: {self.model_path}")
            
            logger.info(f"Loading Vosk model from: {self.model_path}")
            self.model = vosk.Model(self.model_path)
            self.recognizer = vosk.KaldiRecognizer(self.model, 16000)
            self.recognizer.SetWords(True)
            
            logger.info("Vosk model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load Vosk model: {e}")
            raise
    
    def start(self):
        """Start wake word detection in background thread"""
        if self.is_running:
            logger.warning("Wake word detector already running")
            return
        
        logger.info("Starting wake word detector...")
        self.is_running = True
        self._thread = threading.Thread(target=self._detection_loop, daemon=True)
        self._thread.start()
        logger.info("Wake word detector started")
    
    def stop(self):
        """Stop wake word detection"""
        logger.info("Stopping wake word detector...")
        self.is_running = False
        
        if self._thread:
            self._thread.join(timeout=2.0)
        
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass
        
        if self.audio:
            try:
                self.audio.terminate()
            except:
                pass
        
        logger.info("Wake word detector stopped")
    
    def pause(self):
        """Pause wake word detection (during conversation)"""
        logger.debug("Wake word detector paused")
        self.is_paused = True
    
    def resume(self):
        """Resume wake word detection"""
        logger.debug("Wake word detector resumed")
        self.is_paused = False
    
    def _is_wake_word_match(self, text: str) -> bool:
        """
        Check if text matches wake word with fuzzy matching
        More lenient to catch variations like "aidan", "aid in", etc.
        """
        text = text.lower().strip()
        wake = self.wake_word.lower()
        
        # Exact match
        if wake in text:
            return True
        
        # Common variations for "aiden"
        if wake == "aiden":
            variations = [
                "aidan", "ayden", "aden", "aid in", "aid and",
                "a den", "hey aiden", "ok aiden", "hey den"
            ]
            for variation in variations:
                if variation in text:
                    logger.debug(f"Matched variation: '{variation}' in '{text}'")
                    return True
        
        # Fuzzy match - check if most characters match (stricter threshold)
        if len(wake) >= 3:
            # Allow 1 character difference for wake words
            from difflib import SequenceMatcher
            words = text.split()
            for word in words:
                # Only fuzzy match if word is similar length
                if abs(len(word) - len(wake)) <= 2:
                    similarity = SequenceMatcher(None, wake, word).ratio()
                    if similarity >= 0.85:  # 85% similarity threshold (stricter)
                        logger.debug(f"Fuzzy matched: '{word}' (similarity: {similarity:.2f})")
                        return True
        
        return False
    
    def _detection_loop(self):
        """Main detection loop (runs in background thread)"""
        try:
            # Load model
            self._load_model()
            
            # Initialize audio
            self.audio = pyaudio.PyAudio()
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=4000
            )
            self.stream.start_stream()
            
            logger.info("Wake word detection loop started")
            
            # Detection loop
            while self.is_running:
                try:
                    # Skip if paused
                    if self.is_paused:
                        time.sleep(0.1)
                        continue
                    
                    # Read audio data
                    data = self.stream.read(4000, exception_on_overflow=False)
                    
                    # Process with Vosk - ONLY use final results (not partials)
                    if self.recognizer.AcceptWaveform(data):
                        result = json.loads(self.recognizer.Result())
                        text = result.get("text", "").lower()
                        
                        if text:
                            logger.debug(f"Wake word: Heard: '{text}'")
                            
                            # Check for wake word with fuzzy matching
                            if self._is_wake_word_match(text):
                                logger.info(f"[DETECTED] Wake word detected: '{text}'")
                                self._on_wake_word_detected()
                    # Partial results disabled - too many false positives
                    
                except Exception as e:
                    logger.error(f"Wake word detection error: {e}")
                    asyncio.sleep(0.5)
                    
        except Exception as e:
            logger.error(f"Wake word detection loop failed: {e}")
        finally:
            logger.info("Wake word detection loop ended")
    
    def _on_wake_word_detected(self):
        """Handle wake word detection"""
        try:
            # Play activation sound
            asyncio.run(self._play_activation_sound())
            
            # Pause detection during interaction
            self.pause()
            
            # Trigger callback
            if self.on_wake_word:
                self.on_wake_word()
                
        except Exception as e:
            logger.error(f"Error handling wake word: {e}")
    
    async def _play_activation_sound(self):
        """Play wake word acknowledgment sound"""
        try:
            import random
            tts = get_tts_engine()
            # Play random mmm sound for wake word acknowledgment only
            sound_name = random.choice(["mmm1", "mmm2"])
            await tts.play_sound(sound_name)
            logger.debug(f"Played wake word acknowledgment sound: {sound_name}")
        except Exception as e:
            logger.error(f"Error playing wake word acknowledgment: {e}")


# Global instance
_wake_word_detector: Optional[WakeWordDetector] = None


def get_wake_word_detector(on_wake_word: Optional[Callable] = None) -> WakeWordDetector:
    """Get or create global wake word detector"""
    global _wake_word_detector
    if _wake_word_detector is None:
        _wake_word_detector = WakeWordDetector(on_wake_word)
    return _wake_word_detector

