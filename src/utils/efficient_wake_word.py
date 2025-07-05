#!/usr/bin/env python3
"""
Efficient Wake Word Detection System
Uses optimized speech recognition with intelligent buffering and filtering
Much more efficient than continuous full speech recognition
"""
import logging
import threading
import time
import os
import random
from typing import Callable, Dict, Any
import numpy as np

# Check for required imports
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False
    logging.error("SpeechRecognition not available")

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    logging.warning("pygame not available. Sound effects will not work.")

class EfficientWakeWordDetector:
    """
    Highly optimized wake word detection system
    
    Key optimizations:
    1. Short audio chunks (reduces processing time)
    2. Energy-based pre-filtering (skip silent audio)  
    3. Smart timeout management
    4. Minimal API calls to Google
    """
    
    def __init__(self, config_manager, voice_system=None, on_wake_word_detected=None):
        """Initialize the efficient wake word detection system"""
        self.config_manager = config_manager
        self.voice_system = voice_system
        self.on_wake_word_detected = on_wake_word_detected
        
        # Wake word configuration
        self.wake_word = "aiden"
        self.wake_word_alternatives = [
            "aiden", "eden", "aden", "hayden", "aided", "aidan", 
            "ay den", "hidden", "eaten", "headin"
        ]
        self.is_listening = False
        self.should_stop = False
        
        # Efficiency settings
        self.min_energy_threshold = 300    # Skip very quiet audio
        self.recognition_timeout = 0.8     # Short timeout for responsiveness
        self.phrase_time_limit = 1.5       # Quick phrase capture
        
        # Detection statistics
        self.detections = 0
        self.audio_chunks_processed = 0
        self.audio_chunks_skipped = 0
        
        # Sound effects
        self.sound_effects_enabled = config_manager.get_config("voice").get("use_sound_effects", True)
        # Use absolute path for sounds directory
        project_root = self._get_project_root()
        self.sounds_dir = os.path.join(project_root, "sounds")
        self.wake_sounds = ["mmm1.MP3", "mmm2.MP3"]
        
        # Initialize pygame for sound effects if available
        if PYGAME_AVAILABLE and self.sound_effects_enabled:
            try:
                pygame.mixer.init()
                self.sound_system_ready = True
                logging.info("Sound system initialized for efficient wake word detection")
            except Exception as e:
                logging.warning(f"Could not initialize sound system: {e}")
                self.sound_system_ready = False
        else:
            self.sound_system_ready = False
        
        # Initialize speech recognizer with optimized settings
        if SR_AVAILABLE:
            self.recognizer = sr.Recognizer()
            self._configure_recognizer()
            logging.info("Efficient wake word detector initialized")
        else:
            logging.error("Speech recognition not available for wake word detection")
            
        # Threading components
        self.detection_thread = None
        
    def _get_project_root(self):
        """Get the absolute path to the project root directory"""
        # Navigate up from current file location to find project root
        # src/utils/efficient_wake_word.py -> src/utils -> src -> project_root
        current_dir = os.path.dirname(os.path.abspath(__file__))  # src/utils
        src_dir = os.path.dirname(current_dir)  # src
        project_root = os.path.dirname(src_dir)  # project_root
        return project_root
        
    def _configure_recognizer(self):
        """Configure speech recognizer for optimal efficiency"""
        # Optimized for quick wake word detection
        self.recognizer.energy_threshold = 400        # Moderate sensitivity
        self.recognizer.pause_threshold = 0.6         # Quick pause detection
        self.recognizer.phrase_threshold = 0.2        # Short phrases
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.non_speaking_duration = 0.3   # Quick silence detection
        
        logging.info("Speech recognizer configured for efficiency")
    
    def start_listening(self):
        """Start efficient wake word detection"""
        if not SR_AVAILABLE:
            logging.error("Cannot start wake word detection - speech recognition not available")
            return False
            
        if self.is_listening:
            logging.warning("Wake word detection already running")
            return True
            
        self.is_listening = True
        self.should_stop = False
        
        # Reset statistics
        self.detections = 0
        self.audio_chunks_processed = 0
        self.audio_chunks_skipped = 0
        
        # Start the detection thread
        self.detection_thread = threading.Thread(target=self._efficient_detection_loop, daemon=True)
        self.detection_thread.start()
        
        logging.info("Efficient wake word detection started")
        print("🚀 Efficient wake word detection active! (Optimized for low CPU usage)")
        return True
        
    def stop_listening(self):
        """Stop wake word detection"""
        self.should_stop = True
        self.is_listening = False
        
        if self.detection_thread and self.detection_thread.is_alive():
            self.detection_thread.join(timeout=2)
            
        # Log efficiency statistics
        if self.audio_chunks_processed > 0:
            skip_ratio = self.audio_chunks_skipped / (self.audio_chunks_processed + self.audio_chunks_skipped)
            logging.info(f"Efficiency: {self.audio_chunks_processed} processed, "
                        f"{self.audio_chunks_skipped} skipped ({skip_ratio:.1%} efficiency gain)")
            
        logging.info("Efficient wake word detection stopped")
        print("🔇 Efficient wake word detection stopped")
        
    def _efficient_detection_loop(self):
        """Main detection loop optimized for efficiency"""
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while not self.should_stop and self.is_listening:
            try:
                if consecutive_errors > 0:
                    consecutive_errors = 0
                    
                success = self._efficient_wake_word_check()
                
                if success:
                    self._handle_wake_word_detected()
                    # Brief pause after detection
                    time.sleep(1.0)
                else:
                    # Very short delay for efficiency
                    time.sleep(0.02)
                
            except Exception as e:
                consecutive_errors += 1
                logging.debug(f"Error in efficient detection loop: {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logging.warning(f"Too many consecutive errors ({consecutive_errors}), slowing down")
                    time.sleep(2)
                else:
                    time.sleep(0.2)
                    
    def _efficient_wake_word_check(self) -> bool:
        """Optimized wake word checking with energy pre-filtering"""
        try:
            with sr.Microphone() as source:
                # Quick ambient noise adjustment
                self.recognizer.adjust_for_ambient_noise(source, duration=0.1)
                
                try:
                    # Capture short audio chunk
                    audio = self.recognizer.listen(
                        source, 
                        timeout=self.recognition_timeout, 
                        phrase_time_limit=self.phrase_time_limit
                    )
                    
                    # Energy-based pre-filtering to skip processing quiet audio
                    if self._is_audio_too_quiet(audio):
                        self.audio_chunks_skipped += 1
                        return False
                    
                    self.audio_chunks_processed += 1
                    
                except sr.WaitTimeoutError:
                    # No audio detected - this is normal and efficient
                    return False
                    
            # Only process audio that passed energy threshold
            try:
                text = self.recognizer.recognize_google(audio, language="en-US").lower().strip()
                
                if text:
                    logging.debug(f"Speech: '{text}'")
                    print(f"👂 Heard: '{text}'")
                
                # Check for wake word matches
                for word in self.wake_word_alternatives:
                    if word in text:
                        logging.info(f"Wake word detected: '{text}' -> '{word}'")
                        print(f"🎯 WAKE WORD: '{text}' -> '{word}'")
                        return True
                        
            except sr.UnknownValueError:
                # Audio not understood - common and normal
                logging.debug("Audio not understood")
            except sr.RequestError as e:
                logging.warning(f"Speech recognition request error: {e}")
                
        except Exception as e:
            logging.debug(f"Wake word check error: {e}")
            
        return False
    
    def _is_audio_too_quiet(self, audio) -> bool:
        """Check if audio energy is too low to bother processing"""
        try:
            # Convert audio to numpy array for energy calculation
            audio_data = np.frombuffer(audio.frame_data, dtype=np.int16)
            
            # Calculate RMS energy
            rms_energy = np.sqrt(np.mean(audio_data**2))
            
            # Skip if energy is below threshold
            if rms_energy < self.min_energy_threshold:
                logging.debug(f"Skipping quiet audio (RMS: {rms_energy:.1f})")
                return True
                
            return False
            
        except Exception as e:
            logging.debug(f"Energy calculation error: {e}")
            return False  # Process anyway if we can't calculate energy
    
    def _handle_wake_word_detected(self):
        """Handle wake word detection - play sound and trigger command listening"""
        try:
            self.detections += 1
            self._play_wake_sound()
            
            if self.on_wake_word_detected:
                self.on_wake_word_detected()
                
        except Exception as e:
            logging.error(f"Error handling wake word detection: {e}")
            
    def _play_wake_sound(self):
        """Play acknowledgment sound when wake word is detected"""
        if not self.sound_system_ready or not self.sound_effects_enabled:
            return
            
        try:
            sound_file = random.choice(self.wake_sounds)
            sound_path = os.path.join(self.sounds_dir, sound_file)
            
            if os.path.exists(sound_path):
                sound = pygame.mixer.Sound(sound_path)
                sound.play()
                
                logging.info(f"Played wake sound: {sound_file}")
                print(f"🔊 *{sound_file[:-4]}* - Efficient detection!")
                
                time.sleep(0.5)
                
            else:
                logging.warning(f"Wake sound file not found: {sound_path}")
                
        except Exception as e:
            logging.error(f"Error playing wake sound: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of efficient wake word detection"""
        efficiency_ratio = 0
        if self.audio_chunks_processed + self.audio_chunks_skipped > 0:
            efficiency_ratio = self.audio_chunks_skipped / (self.audio_chunks_processed + self.audio_chunks_skipped)
            
        return {
            "listening": self.is_listening,
            "wake_word": self.wake_word,
            "sound_effects": self.sound_system_ready and self.sound_effects_enabled,
            "alternatives": self.wake_word_alternatives,
            "thread_alive": self.detection_thread.is_alive() if self.detection_thread else False,
            "detections": self.detections,
            "chunks_processed": self.audio_chunks_processed,
            "chunks_skipped": self.audio_chunks_skipped,
            "efficiency_ratio": efficiency_ratio,
            "optimized": True,
            "library": "Efficient SpeechRecognition"
        }
 