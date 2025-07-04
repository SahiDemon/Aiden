#!/usr/bin/env python3
"""
Vosk-based Wake Word Detection
Uses offline speech recognition with trained models for accurate wake word detection
Much better than Google Speech Recognition for wake words
"""
import logging
import threading
import time
import os
import random
import json
import zipfile
from typing import Callable, Dict, Any
import requests

# Check for required imports
try:
    import vosk
    import pyaudio
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    logging.error("Vosk or PyAudio not available")

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    logging.warning("pygame not available. Sound effects will not work.")

class VoskWakeWordDetector:
    """
    Professional wake word detection using Vosk offline speech recognition
    
    Benefits:
    - Completely offline (no internet required)
    - Fast and accurate
    - Low CPU usage
    - Proper trained models
    - Works great on Windows
    """
    
    def __init__(self, config_manager, voice_system=None, on_wake_word_detected=None):
        """Initialize Vosk wake word detection"""
        self.config_manager = config_manager
        self.voice_system = voice_system
        self.on_wake_word_detected = on_wake_word_detected
        
        # Wake word configuration
        self.wake_word = "aiden"
        self.wake_word_alternatives = [
            "aiden", "hayden", "aidan"
        ]
        self.is_listening = False
        self.should_stop = False
        self.is_paused = False  # Add pause capability
        self.cleanup_in_progress = False  # Prevent race conditions
        
        # Audio configuration for Vosk
        self.sample_rate = 16000  # Vosk works best with 16kHz
        self.chunk_size = 4000    # Good chunk size for real-time
        self.audio_format = pyaudio.paInt16
        self.channels = 1
        
        # Detection statistics
        self.detections = 0
        self.confidence_threshold = 0.7  # Higher confidence for fewer false positives
        
        # Sound effects
        self.sound_effects_enabled = config_manager.get_config("voice").get("use_sound_effects", True)
        # Use absolute path for sounds directory
        project_root = self._get_project_root()
        self.sounds_dir = os.path.join(project_root, "sounds")
        self.wake_sounds = ["mmm1.MP3", "mmm2.MP3"]
        
        # Initialize pygame for sound effects
        if PYGAME_AVAILABLE and self.sound_effects_enabled:
            try:
                pygame.mixer.init()
                self.sound_system_ready = True
                logging.info("Sound system initialized for Vosk wake word detection")
            except Exception as e:
                logging.warning(f"Could not initialize sound system: {e}")
                self.sound_system_ready = False
        else:
            self.sound_system_ready = False
        
        # Vosk model and recognizer
        self.vosk_model = None
        self.vosk_recognizer = None
        self.audio_stream = None
        
        # Initialize Vosk if available
        if VOSK_AVAILABLE:
            self._initialize_vosk_model()
        else:
            logging.error("Vosk not available for wake word detection")
            
        # Threading components
        self.detection_thread = None
        
    def _get_project_root(self):
        """Get the absolute path to the project root directory"""
        # Navigate up from current file location to find project root
        # src/utils/vosk_wake_word.py -> src/utils -> src -> project_root
        current_dir = os.path.dirname(os.path.abspath(__file__))  # src/utils
        src_dir = os.path.dirname(current_dir)  # src
        project_root = os.path.dirname(src_dir)  # project_root
        return project_root
        
    def _initialize_vosk_model(self):
        """Initialize Vosk model for wake word detection"""
        try:
            # Download and setup Vosk model
            model_path = self._ensure_vosk_model()
            if model_path:
                logging.info(f"Loading Vosk model from: {model_path}")
                self.vosk_model = vosk.Model(model_path)
                
                # Create recognizer WITHOUT grammar restrictions (like our successful test)
                self.vosk_recognizer = vosk.KaldiRecognizer(self.vosk_model, self.sample_rate)
                
                # Don't set grammar - use full vocabulary for better detection
                # This matches our successful test approach
                
                logging.info("Vosk wake word detector initialized successfully")
                return True
            else:
                logging.error("Failed to download/setup Vosk model")
                return False
                
        except Exception as e:
            logging.error(f"Error initializing Vosk model: {e}")
            return False
    
    def _ensure_vosk_model(self):
        """Download Vosk model if not present"""
        # Use absolute path for models directory
        project_root = self._get_project_root()
        models_dir = os.path.join(project_root, "vosk_models")
        model_name = "vosk-model-small-en-us-0.15"
        model_path = os.path.join(models_dir, model_name)
        
        # Check if model already exists
        if os.path.exists(model_path) and os.path.isdir(model_path):
            logging.info(f"Vosk model already exists: {model_path}")
            return model_path
        
        # Download model
        try:
            os.makedirs(models_dir, exist_ok=True)
            
            model_url = f"https://alphacephei.com/vosk/models/{model_name}.zip"
            model_zip_path = os.path.join(models_dir, f"{model_name}.zip")
            
            logging.info(f"Downloading Vosk model: {model_name}")
            print(f"📥 Downloading wake word model... (this may take a minute)")
            
            response = requests.get(model_url, stream=True)
            total_size = int(response.headers.get('content-length', 0))
            
            with open(model_zip_path, 'wb') as f:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            print(f"\r📥 Download progress: {progress:.1f}%", end="", flush=True)
            
            print(f"\n✅ Download completed!")
            
            # Extract model
            logging.info(f"Extracting Vosk model...")
            print(f"📦 Extracting model...")
            
            with zipfile.ZipFile(model_zip_path, 'r') as zip_ref:
                zip_ref.extractall(models_dir)
            
            # Clean up zip file
            os.remove(model_zip_path)
            
            print(f"✅ Model ready: {model_path}")
            return model_path
            
        except Exception as e:
            logging.error(f"Error downloading Vosk model: {e}")
            print(f"❌ Failed to download model: {e}")
            return None
    
    def start_listening(self):
        """Start Vosk wake word detection"""
        if not VOSK_AVAILABLE:
            logging.error("Cannot start wake word detection - Vosk not available")
            return False
            
        if not self.vosk_model or not self.vosk_recognizer:
            logging.error("Cannot start wake word detection - Vosk model not loaded")
            return False
            
        if self.is_listening:
            logging.warning("Wake word detection already running")
            return True
            
        # Reset all flags for fresh start
        self.is_listening = True
        self.should_stop = False
        self.is_paused = False
        self.cleanup_in_progress = False
        
        # Reset statistics
        self.detections = 0
        
        # Clear any leftover audio stream references
        self.audio_stream = None
        
        # Start the detection thread
        self.detection_thread = threading.Thread(target=self._vosk_detection_loop, daemon=True)
        self.detection_thread.start()
        
        logging.info("Vosk wake word detection started")
        print("🎯 Vosk wake word detection active! (Offline & Accurate)")
        return True
        
    def stop_listening(self):
        """Stop wake word detection"""
        if self.cleanup_in_progress:
            print("🔇 Cleanup already in progress, skipping...")
            return
            
        print("🔇 Stopping Vosk wake word detection...")
        self.cleanup_in_progress = True
        
        try:
            # Signal the thread to stop
            self.should_stop = True
            self.is_listening = False
            
            # Give the detection thread time to see the stop signal
            time.sleep(0.2)
            
            # Wait for the detection thread to finish gracefully
            if self.detection_thread and self.detection_thread.is_alive():
                print("⏳ Waiting for detection thread to stop...")
                self.detection_thread.join(timeout=3)
                
                # Force cleanup if thread is still alive
                if self.detection_thread.is_alive():
                    print("⚠️ Detection thread didn't stop gracefully, forcing cleanup...")
                    # Nuclear option: force close audio stream to unstick the thread
                    if self.audio_stream:
                        try:
                            self.audio_stream.close()
                            self.audio_stream = None
                            print("🔥 Force closed audio stream")
                        except:
                            self.audio_stream = None
                    
                    # Give it one more chance to exit
                    self.detection_thread.join(timeout=1)
                    if self.detection_thread.is_alive():
                        print("🔥 Thread still alive - this is expected, continuing...")
                    else:
                        print("✅ Thread stopped after force cleanup")
            
            # Clean up audio stream (only if detection thread hasn't already)
            if self.audio_stream:
                try:
                    print("Ensuring audio stream is properly closed...")
                    self.audio_stream.stop_stream()
                    self.audio_stream.close()
                    self.audio_stream = None
                    print("Audio stream cleanup completed")
                except Exception as e:
                    print(f"Audio cleanup error (non-fatal): {e}")
                    self.audio_stream = None
            
            logging.info("Vosk wake word detection stopped")
            print("✅ Vosk wake word detection stopped successfully")
            
        finally:
            self.cleanup_in_progress = False
        
    def pause_listening(self):
        """Pause wake word detection (e.g., during AI response)"""
        self.is_paused = True
        logging.debug("Wake word detection paused")
        
    def resume_listening(self):
        """Resume wake word detection after AI response"""
        self.is_paused = False
        logging.debug("Wake word detection resumed")
        
    def _vosk_detection_loop(self):
        """Main Vosk detection loop"""
        audio = None
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
            
            logging.info(f"Vosk audio stream started: {self.sample_rate}Hz")
            
            consecutive_errors = 0
            max_consecutive_errors = 10
            
            while not self.should_stop and self.is_listening:
                try:
                    if consecutive_errors > 0:
                        consecutive_errors = 0
                    
                    # Read audio data
                    audio_data = self.audio_stream.read(self.chunk_size, exception_on_overflow=False)
                    
                    # Skip processing if paused (during AI responses)
                    if self.is_paused:
                        time.sleep(0.05)  # Brief pause to avoid busy waiting
                        continue
                    
                    # Process with Vosk
                    if self.vosk_recognizer.AcceptWaveform(audio_data):
                        # Final result
                        result = json.loads(self.vosk_recognizer.Result())
                        self._process_vosk_result(result, final=True)
                    else:
                        # Partial result  
                        result = json.loads(self.vosk_recognizer.PartialResult())
                        self._process_vosk_result(result, final=False)
                        
                except Exception as e:
                    consecutive_errors += 1
                    logging.debug(f"Error in Vosk detection loop: {e}")
                    
                    if consecutive_errors >= max_consecutive_errors:
                        logging.warning(f"Too many consecutive errors ({consecutive_errors}), slowing down")
                        time.sleep(1)
                    else:
                        time.sleep(0.1)
                        
        except Exception as e:
            logging.error(f"Fatal error in Vosk detection: {e}")
        finally:
            # Cleanup - but only if main thread isn't already cleaning up
            if not self.cleanup_in_progress:
                print("🧹 Detection thread cleaning up...")
                if self.audio_stream:
                    try:
                        print("Detection thread stopping audio stream...")
                        self.audio_stream.stop_stream()
                        self.audio_stream.close()
                        print("Audio stream closed from detection thread")
                    except Exception as cleanup_error:
                        print(f"Audio cleanup error in detection thread: {cleanup_error}")
                    finally:
                        self.audio_stream = None
                
                if audio:
                    try:
                        audio.terminate()
                        print("PyAudio terminated from detection thread")
                    except Exception as terminate_error:
                        print(f"PyAudio terminate error: {terminate_error}")
                
                print("🧹 Detection thread cleanup completed")
            else:
                print("🧹 Skipping detection thread cleanup (main thread handling it)")
    
    def _process_vosk_result(self, result: Dict, final: bool):
        """Process Vosk recognition result"""
        try:
            text = result.get('text', '').lower().strip()
            confidence = result.get('confidence', 0.0)
            
            if text and final:  # Only process final results
                logging.debug(f"Vosk heard: '{text}' (confidence: {confidence:.2f})")
                print(f"👂 Vosk heard: '{text}' (conf: {confidence:.1%})")
                
                # Check for wake words WITHOUT confidence threshold (Vosk often returns 0.0% even for correct detections)
                for wake_word in self.wake_word_alternatives:
                    if wake_word in text:
                        logging.info(f"Wake word detected: '{text}' -> '{wake_word}' (conf: {confidence:.2f})")
                        print(f"🎯 VOSK WAKE WORD: '{text}' -> '{wake_word}' (conf: {confidence:.1%})")
                        
                        self._handle_wake_word_detected()
                        time.sleep(1.0)  # Brief pause after detection
                        break
                        
        except Exception as e:
            logging.debug(f"Error processing Vosk result: {e}")
    
    def _handle_wake_word_detected(self):
        """Handle wake word detection"""
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
                print(f"🔊 *{sound_file[:-4]}* - Vosk activated!")
                
                time.sleep(0.5)
                
            else:
                logging.warning(f"Wake sound file not found: {sound_path}")
                
        except Exception as e:
            logging.error(f"Error playing wake sound: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of Vosk wake word detection"""
        return {
            "listening": self.is_listening,
            "paused": self.is_paused,
            "wake_word": self.wake_word,
            "sound_effects": self.sound_system_ready and self.sound_effects_enabled,
            "alternatives": self.wake_word_alternatives,
            "thread_alive": self.detection_thread.is_alive() if self.detection_thread else False,
            "detections": self.detections,
            "confidence_threshold": self.confidence_threshold,
            "model_loaded": self.vosk_model is not None,
            "offline": True,
            "library": "Vosk Offline Speech Recognition"
        }
    
    def set_confidence_threshold(self, threshold: float):
        """Set confidence threshold for wake word detection"""
        if 0.0 <= threshold <= 1.0:
            self.confidence_threshold = threshold
            logging.info(f"Confidence threshold set to {threshold}")
        else:
            logging.warning(f"Invalid threshold {threshold}. Must be between 0.0 and 1.0")