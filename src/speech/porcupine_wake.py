"""
Porcupine Wake Word Detection System
High-accuracy, low-latency wake word detection using Picovoice Porcupine
"""
import asyncio
import logging
import os
import struct
import threading
import time
from typing import Callable, Optional
import numpy as np
import pvporcupine
import pyaudio

from src.speech.tts import get_tts_engine
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class PorcupineWakeWordDetector:
    """
    Wake word detector using Porcupine
    Optimized for accuracy and speed with audio pre-processing
    """
    
    def __init__(self, on_wake_word: Optional[Callable] = None):
        """
        Initialize Porcupine wake word detector
        
        Args:
            on_wake_word: Callback function to call when wake word is detected
        """
        self.settings = get_settings()
        self.on_wake_word = on_wake_word
        
        # Porcupine configuration
        self.access_key = self.settings.speech.porcupine_access_key
        self.model_path = self.settings.speech.porcupine_model_path
        self.sensitivity = self.settings.speech.porcupine_sensitivity
        
        # Porcupine instance
        self.porcupine = None
        
        # Audio settings
        self.audio = None
        self.stream = None
        self.sample_rate = 16000
        self.frame_length = 512  # Porcupine requirement
        
        # Audio processing
        self.noise_floor = 0
        self.noise_floor_samples = []
        self.max_noise_samples = 100
        self.agc_target_level = 0.3
        self.agc_current_gain = 1.0
        
        # Control flags
        self.is_running = False
        self.is_paused = False
        self._thread = None
        
        logger.info(f"Porcupine Wake Word Detector initialized: sensitivity={self.sensitivity}")
    
    def _initialize_porcupine(self):
        """Initialize Porcupine engine"""
        try:
            # Check if access key is provided
            if not self.access_key:
                raise ValueError("Porcupine AccessKey not provided. Set SPEECH_PORCUPINE_ACCESS_KEY in .env")
            
            # Check if custom model exists
            keyword_paths = None
            if os.path.exists(self.model_path):
                keyword_paths = [self.model_path]
                logger.info(f"Using custom wake word model: {self.model_path}")
            else:
                # Use built-in keyword (if available)
                logger.warning(f"Custom model not found at {self.model_path}, will use built-in keywords")
                keyword_paths = None  # Will use default built-in keywords
            
            # Initialize Porcupine
            if keyword_paths:
                self.porcupine = pvporcupine.create(
                    access_key=self.access_key,
                    keyword_paths=keyword_paths,
                    sensitivities=[self.sensitivity]
                )
            else:
                # Fallback: use built-in "computer" keyword for testing
                self.porcupine = pvporcupine.create(
                    access_key=self.access_key,
                    keywords=["computer"],  # Built-in keyword as fallback
                    sensitivities=[self.sensitivity]
                )
                logger.warning("Using built-in 'computer' keyword as fallback. Create custom 'aiden' model in Picovoice Console.")
            
            self.sample_rate = self.porcupine.sample_rate
            self.frame_length = self.porcupine.frame_length
            
            logger.info(f"Porcupine initialized: sample_rate={self.sample_rate}, frame_length={self.frame_length}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Porcupine: {e}")
            raise
    
    def _apply_agc(self, audio_data: np.ndarray) -> np.ndarray:
        """
        Apply Automatic Gain Control to normalize audio levels
        
        Args:
            audio_data: Input audio samples
            
        Returns:
            AGC-processed audio samples
        """
        # Calculate current audio level
        current_level = np.max(np.abs(audio_data)) / 32768.0  # Normalize to 0-1
        
        if current_level > 0.01:  # Avoid division by zero
            # Calculate desired gain
            desired_gain = self.agc_target_level / current_level
            
            # Smooth gain changes (prevent abrupt adjustments)
            self.agc_current_gain = 0.9 * self.agc_current_gain + 0.1 * desired_gain
            
            # Limit gain to reasonable range
            self.agc_current_gain = np.clip(self.agc_current_gain, 0.5, 4.0)
            
            # Apply gain
            audio_data = (audio_data * self.agc_current_gain).astype(np.int16)
        
        return audio_data
    
    def _update_noise_floor(self, audio_data: np.ndarray):
        """
        Update noise floor estimate for better detection in varying environments
        
        Args:
            audio_data: Current audio frame
        """
        # Calculate RMS of current frame
        rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))
        
        # Add to noise samples
        self.noise_floor_samples.append(rms)
        
        # Keep only recent samples
        if len(self.noise_floor_samples) > self.max_noise_samples:
            self.noise_floor_samples.pop(0)
        
        # Update noise floor (use 25th percentile to avoid including speech)
        if len(self.noise_floor_samples) >= 10:
            self.noise_floor = np.percentile(self.noise_floor_samples, 25)
    
    def _is_audio_above_threshold(self, audio_data: np.ndarray) -> bool:
        """
        Check if audio is above noise floor (contains potential speech)
        
        Args:
            audio_data: Current audio frame
            
        Returns:
            True if audio is above threshold
        """
        rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))
        threshold = self.noise_floor * 2.0  # 2x noise floor
        return rms > threshold
    
    def start(self):
        """Start wake word detection in background thread"""
        if self.is_running:
            logger.warning("Porcupine wake word detector already running")
            return
        
        logger.info("Starting Porcupine wake word detector...")
        self.is_running = True
        self._thread = threading.Thread(target=self._detection_loop, daemon=True)
        self._thread.start()
        logger.info("Porcupine wake word detector started")
    
    def stop(self):
        """Stop wake word detection"""
        logger.info("Stopping Porcupine wake word detector...")
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
        
        if self.porcupine:
            try:
                self.porcupine.delete()
            except:
                pass
        
        logger.info("Porcupine wake word detector stopped")
    
    def pause(self):
        """Pause wake word detection (during conversation)"""
        logger.debug("Porcupine wake word detector paused")
        self.is_paused = True
    
    def resume(self):
        """Resume wake word detection"""
        logger.debug("Porcupine wake word detector resumed")
        self.is_paused = False
    
    def _detection_loop(self):
        """Main detection loop (runs in background thread)"""
        try:
            # Initialize Porcupine
            self._initialize_porcupine()
            
            # Initialize audio
            self.audio = pyaudio.PyAudio()
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.frame_length
            )
            self.stream.start_stream()
            
            logger.info("Porcupine detection loop started")
            
            # Detection loop
            while self.is_running:
                try:
                    if self.is_paused:
                        time.sleep(0.1)
                        continue
                    
                    # Read audio data
                    pcm = self.stream.read(self.frame_length, exception_on_overflow=False)
                    
                    # Convert to numpy array
                    audio_frame = np.frombuffer(pcm, dtype=np.int16)
                    
                    # Update noise floor estimate
                    self._update_noise_floor(audio_frame)
                    
                    # Apply AGC for better detection in varying volumes
                    audio_frame = self._apply_agc(audio_frame)
                    
                    # Process with Porcupine
                    keyword_index = self.porcupine.process(audio_frame)
                    
                    if keyword_index >= 0:
                        # Wake word detected!
                        logger.info(f"[PORCUPINE DETECTED] Wake word detected (keyword_index={keyword_index})")
                        self._on_wake_word_detected()
                    
                except Exception as e:
                    logger.error(f"Porcupine detection error: {e}")
                    time.sleep(0.5)
                    
        except Exception as e:
            logger.error(f"Porcupine detection loop failed: {e}", exc_info=True)
        finally:
            logger.info("Porcupine detection loop ended")
    
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
_porcupine_detector: Optional[PorcupineWakeWordDetector] = None


def get_porcupine_detector(on_wake_word: Optional[Callable] = None) -> PorcupineWakeWordDetector:
    """Get or create global Porcupine wake word detector"""
    global _porcupine_detector
    if _porcupine_detector is None:
        _porcupine_detector = PorcupineWakeWordDetector(on_wake_word)
    return _porcupine_detector




