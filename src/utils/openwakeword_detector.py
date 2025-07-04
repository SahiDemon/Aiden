#!/usr/bin/env python3
"""
Efficient Wake Word Detection using openWakeWord
Replaces speech recognition with specialized wake word detection
"""
import logging
import threading
import time
import os
import random
from typing import Callable, Dict, Any, Optional
import numpy as np

# Check for required imports
try:
    import openwakeword
    from openwakeword import Model
    OPENWAKEWORD_AVAILABLE = True
except ImportError:
    OPENWAKEWORD_AVAILABLE = False
    logging.error("openWakeWord not available. Please install: pip install openwakeword")

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    logging.error("PyAudio not available. Please install: pip install pyaudio")

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    logging.warning("pygame not available. Sound effects will not work.")

class OpenWakeWordDetector:
    """Efficient wake word detection using openWakeWord library"""
    
    def __init__(self, config_manager, voice_system=None, on_wake_word_detected=None):
        """Initialize the openWakeWord detection system"""
        self.config_manager = config_manager
        self.voice_system = voice_system
        self.on_wake_word_detected = on_wake_word_detected
        
        # Wake word configuration
        self.wake_word = "aiden"
        self.is_listening = False
        self.should_stop = False
        self.detection_threshold = 0.5  # Confidence threshold for detection
        
        # Audio configuration
        self.chunk_size = 1280  # 80ms at 16kHz (openWakeWord requirement)
        self.sample_rate = 16000  # openWakeWord requires 16kHz
        self.audio_format = pyaudio.paInt16
        self.channels = 1
        
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
                logging.info("Sound system initialized for openWakeWord detection")
            except Exception as e:
                logging.warning(f"Could not initialize sound system: {e}")
                self.sound_system_ready = False
        else:
            self.sound_system_ready = False
        
        # Initialize openWakeWord models
        if OPENWAKEWORD_AVAILABLE:
            self._initialize_models()
        else:
            logging.error("Cannot initialize openWakeWord - library not available")
            
        # Threading components
        self.detection_thread = None
        self.audio_stream = None
        
    def _get_project_root(self):
        """Get the absolute path to the project root directory"""
        # Navigate up from current file location to find project root
        # src/utils/openwakeword_detector.py -> src/utils -> src -> project_root
        current_dir = os.path.dirname(os.path.abspath(__file__))  # src/utils
        src_dir = os.path.dirname(current_dir)  # src
        project_root = os.path.dirname(src_dir)  # project_root
        return project_root
        
    def _initialize_models(self):
        """Initialize openWakeWord models"""
        try:
            # Initialize the openWakeWord model
            # We'll start with pre-trained models and see which ones work best for "Aiden"
            self.oww_model = Model()
            
            # Get available models
            available_models = self.oww_model.models
            logging.info(f"Available openWakeWord models: {list(available_models.keys())}")
            
            # Log model details
            for model_name in available_models:
                logging.info(f"Model '{model_name}' loaded successfully")
            
            logging.info("openWakeWord models initialized successfully")
            
        except Exception as e:
            logging.error(f"Failed to initialize openWakeWord models: {e}")
            self.oww_model = None
    
    def start_listening(self):
        """Start continuous wake word detection"""
        if not OPENWAKEWORD_AVAILABLE:
            logging.error("Cannot start wake word detection - openWakeWord not available")
            return False
            
        if not PYAUDIO_AVAILABLE:
            logging.error("Cannot start wake word detection - PyAudio not available")
            return False
            
        if not self.oww_model:
            logging.error("Cannot start wake word detection - models not loaded")
            return False
            
        if self.is_listening:
            logging.warning("Wake word detection already running")
            return True
            
        self.is_listening = True
        self.should_stop = False
        
        # Start the detection thread
        self.detection_thread = threading.Thread(target=self._detection_loop, daemon=True)
        self.detection_thread.start()
        
        logging.info("openWakeWord detection started - listening for wake words...")
        print("🎤 Always listening with openWakeWord... (Much more efficient!)")
        return True
        
    def stop_listening(self):
        """Stop wake word detection"""
        self.should_stop = True
        self.is_listening = False
        
        # Stop audio stream
        if self.audio_stream:
            try:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
                self.audio_stream = None
            except Exception as e:
                logging.debug(f"Error closing audio stream: {e}")
        
        if self.detection_thread and self.detection_thread.is_alive():
            self.detection_thread.join(timeout=2)
            
        logging.info("openWakeWord detection stopped")
        print("🔇 openWakeWord detection stopped")
        
    def _detection_loop(self):
        """Main detection loop using openWakeWord"""
        try:
            # Initialize PyAudio
            audio = pyaudio.PyAudio()
            
            # Open audio stream
            self.audio_stream = audio.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size
            )
            
            logging.info(f"Audio stream started: {self.sample_rate}Hz, {self.chunk_size} frames")
            
            consecutive_errors = 0
            max_consecutive_errors = 10
            
            while not self.should_stop and self.is_listening:
                try:
                    if consecutive_errors > 0:
                        consecutive_errors = 0
                    
                    # Read audio data
                    audio_data = self.audio_stream.read(self.chunk_size, exception_on_overflow=False)
                    
                    # Convert to numpy array (openWakeWord expects this format)
                    audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
                    
                    # Get predictions from openWakeWord
                    predictions = self.oww_model.predict(audio_array)
                    
                    # Check for wake word detection
                    self._check_predictions(predictions)
                        
                except Exception as e:
                    consecutive_errors += 1
                    logging.debug(f"Error in openWakeWord detection loop: {e}")
                    
                    if consecutive_errors >= max_consecutive_errors:
                        logging.warning(f"Too many consecutive errors ({consecutive_errors}), slowing down detection")
                        time.sleep(1)
                    else:
                        time.sleep(0.1)
                        
        except Exception as e:
            logging.error(f"Fatal error in openWakeWord detection: {e}")
        finally:
            # Cleanup
            if self.audio_stream:
                try:
                    self.audio_stream.stop_stream()
                    self.audio_stream.close()
                except:
                    pass
            try:
                audio.terminate()
            except:
                pass
    
    def _check_predictions(self, predictions: Dict[str, float]):
        """Check openWakeWord predictions for wake word detection"""
        for model_name, confidence in predictions.items():
            if confidence > self.detection_threshold:
                # Check if this model is suitable for "Aiden" or similar
                model_lower = model_name.lower()
                
                # Look for models that might work for "Aiden"
                # Common openWakeWord models that might match: "hey mycroft", "alexa", etc.
                wake_word_matches = [
                    "hey", "mycroft", "alexa", "computer", "jarvis", 
                    "assistant", "wake", "listen", "start"
                ]
                
                # For now, let's detect on any model above threshold
                # We can fine-tune this based on which models work best
                logging.info(f"Wake word detected! Model: '{model_name}', Confidence: {confidence:.3f}")
                print(f"🎯 openWakeWord detected: '{model_name}' (confidence: {confidence:.1%})")
                
                self._handle_wake_word_detected(model_name, confidence)
                
                # Brief pause after detection to avoid rapid re-triggering
                time.sleep(1.0)
                break
    
    def _handle_wake_word_detected(self, model_name: str, confidence: float):
        """Handle wake word detection - play sound and trigger command listening"""
        try:
            self._play_wake_sound()
            
            if self.on_wake_word_detected:
                self.on_wake_word_detected()
                
        except Exception as e:
            logging.error(f"Error handling wake word detection: {e}")
            
    def _play_wake_sound(self):
        """Play a beautiful acknowledgment sound when wake word is detected"""
        if not self.sound_system_ready or not self.sound_effects_enabled:
            return
            
        try:
            sound_file = random.choice(self.wake_sounds)
            sound_path = os.path.join(self.sounds_dir, sound_file)
            
            if os.path.exists(sound_path):
                sound = pygame.mixer.Sound(sound_path)
                sound.play()
                
                logging.info(f"Played wake sound: {sound_file}")
                print(f"🔊 *{sound_file[:-4]}* - openWakeWord activated!")
                
                time.sleep(0.5)
                
            else:
                logging.warning(f"Wake sound file not found: {sound_path}")
                
        except Exception as e:
            logging.error(f"Error playing wake sound: {e}")
    
    def set_wake_word_callback(self, callback: Callable):
        """Set the callback function for when wake word is detected"""
        self.on_wake_word_detected = callback
        
    def is_detection_active(self) -> bool:
        """Check if wake word detection is currently active"""
        return self.is_listening and not self.should_stop
        
    def get_status(self) -> Dict[str, Any]:
        """Get current status of openWakeWord detection"""
        models_loaded = []
        if self.oww_model and hasattr(self.oww_model, 'models'):
            models_loaded = list(self.oww_model.models.keys())
            
        return {
            "listening": self.is_listening,
            "wake_word": self.wake_word,
            "sound_effects": self.sound_system_ready and self.sound_effects_enabled,
            "detection_threshold": self.detection_threshold,
            "models_loaded": models_loaded,
            "thread_alive": self.detection_thread.is_alive() if self.detection_thread else False,
            "library": "openWakeWord",
            "efficient": True
        }
    
    def set_detection_threshold(self, threshold: float):
        """Set the confidence threshold for wake word detection"""
        if 0.0 <= threshold <= 1.0:
            self.detection_threshold = threshold
            logging.info(f"Detection threshold set to {threshold}")
        else:
            logging.warning(f"Invalid threshold {threshold}. Must be between 0.0 and 1.0")
            
    def list_available_models(self) -> list:
        """Get list of available openWakeWord models"""
        if self.oww_model and hasattr(self.oww_model, 'models'):
            return list(self.oww_model.models.keys())
        return [] 