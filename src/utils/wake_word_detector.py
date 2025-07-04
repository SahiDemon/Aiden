"""
Wake Word Detection System for Aiden
Continuously listens for the wake word "Aiden" and triggers command processing
"""
import os
import logging
import time
import threading
import queue
from typing import Optional, Callable, Dict, Any
import random

# Try to import speech recognition dependencies
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False
    logging.error("SpeechRecognition package not available. Wake word detection will not work.")

# Try to import pygame for sound effects
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    logging.warning("pygame not available. Sound effects will not work.")

class WakeWordDetector:
    """Handles continuous wake word detection for 'Aiden'"""
    
    def __init__(self, config_manager, voice_system=None, on_wake_word_detected=None):
        """Initialize the wake word detection system"""
        self.config_manager = config_manager
        self.voice_system = voice_system
        self.on_wake_word_detected = on_wake_word_detected
        
        # Wake word configuration
        self.wake_word = "aiden"
        self.wake_word_alternatives = ["aiden", "eden", "aden", "hayden", "aided", "aidan", "ay den", "hidden"]
        self.is_listening = False
        self.should_stop = False
        
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
                logging.info("Sound system initialized for wake word detection")
            except Exception as e:
                logging.warning(f"Could not initialize sound system: {e}")
                self.sound_system_ready = False
        else:
            self.sound_system_ready = False
        
        # Initialize speech recognizer for wake word detection
        if SR_AVAILABLE:
            self.recognizer = sr.Recognizer()
            
            # Configure for single wake word detection - optimized for "Aiden"
            self.recognizer.energy_threshold = 600   # Even more sensitive
            self.recognizer.pause_threshold = 0.8    # Wait longer for complete word
            self.recognizer.phrase_threshold = 0.3   # Minimum time for "Aiden"
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.non_speaking_duration = 0.5  # Wait for silence after word
            
            logging.info("Wake word detector initialized")
        else:
            logging.error("Speech recognition not available for wake word detection")
            
        # Threading components
        self.detection_thread = None
        
    def _get_project_root(self):
        """Get the absolute path to the project root directory"""
        # Navigate up from current file location to find project root
        # src/utils/wake_word_detector.py -> src/utils -> src -> project_root
        current_dir = os.path.dirname(os.path.abspath(__file__))  # src/utils
        src_dir = os.path.dirname(current_dir)  # src
        project_root = os.path.dirname(src_dir)  # project_root
        return project_root
        
    def start_listening(self):
        """Start continuous wake word detection"""
        if not SR_AVAILABLE:
            logging.error("Cannot start wake word detection - speech recognition not available")
            return False
            
        if self.is_listening:
            logging.warning("Wake word detection already running")
            return True
            
        self.is_listening = True
        self.should_stop = False
        
        # Start the detection thread
        self.detection_thread = threading.Thread(target=self._detection_loop, daemon=True)
        self.detection_thread.start()
        
        logging.info("Wake word detection started - listening for 'Aiden'...")
        print("🎤 Always listening for 'Aiden'... (Say 'Aiden' to activate)")
        return True
        
    def stop_listening(self):
        """Stop wake word detection"""
        self.should_stop = True
        self.is_listening = False
        
        if self.detection_thread and self.detection_thread.is_alive():
            self.detection_thread.join(timeout=2)
            
        logging.info("Wake word detection stopped")
        print("🔇 Wake word detection stopped")
        
    def _detection_loop(self):
        """Main detection loop that runs continuously"""
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while not self.should_stop and self.is_listening:
            try:
                if consecutive_errors > 0:
                    consecutive_errors = 0
                    
                success = self._listen_for_wake_word()
                
                if success:
                    self._handle_wake_word_detected()
                    # Brief pause after detection before resuming
                    time.sleep(1.0)
                else:
                    # Minimal delay between attempts for faster detection
                    time.sleep(0.05)
                
            except Exception as e:
                consecutive_errors += 1
                logging.error(f"Error in wake word detection loop: {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logging.warning(f"Too many consecutive errors ({consecutive_errors}), slowing down detection")
                    time.sleep(2)
                else:
                    time.sleep(0.5)
                    
    def _listen_for_wake_word(self) -> bool:
        """Listen for the wake word with lightweight processing"""
        try:
            with sr.Microphone() as source:
                # Quick ambient noise adjustment for responsive single-word detection
                self.recognizer.adjust_for_ambient_noise(source, duration=0.1)
                
                try:
                    # Optimized for single wake word - shorter limits to avoid waiting for continuous speech
                    audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=2)
                except sr.WaitTimeoutError:
                    return False
                    
            try:
                text = self.recognizer.recognize_google(audio, language="en-US").lower().strip()
                
                # Log all recognized speech for debugging
                if text:
                    logging.debug(f"Speech recognized: '{text}'")
                    print(f"👂 Heard: '{text}'")
                
                for word in self.wake_word_alternatives:
                    if word in text:
                        logging.info(f"Wake word detected: '{text}' (matched: '{word}')")
                        print(f"🎯 Wake word detected: '{text}' -> '{word}'")
                        return True
                        
            except sr.UnknownValueError:
                # More frequent but less verbose logging
                logging.debug("Speech not understood")
            except sr.RequestError as e:
                logging.warning(f"Speech recognition request error: {e}")
                
        except Exception as e:
            logging.debug(f"Wake word detection error: {e}")
            
        return False
        
    def _handle_wake_word_detected(self):
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
                print(f"🔊 *{sound_file[:-4]}* - I'm listening...")
                
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
        """Get current status of wake word detection"""
        return {
            "listening": self.is_listening,
            "wake_word": self.wake_word,
            "sound_effects": self.sound_system_ready and self.sound_effects_enabled,
            "alternatives": self.wake_word_alternatives,
            "thread_alive": self.detection_thread.is_alive() if self.detection_thread else False
        } 