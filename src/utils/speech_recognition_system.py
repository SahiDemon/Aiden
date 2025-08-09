"""
Speech Recognition System for Aiden
Handles speech-to-text (STT) functionality for voice commands
"""
import os
import logging
import time
import traceback
from typing import Optional, Dict, Any, Tuple

# Try to import optional dependencies
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False
    logging.error("SpeechRecognition package not available. Voice input will not work.")

# Check PyAudio availability separately
PYAUDIO_AVAILABLE = False
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
    logging.info("PyAudio is available for microphone access")
except ImportError:
    logging.warning("PyAudio not available - this may cause microphone access issues")
    print("WARNING: PyAudio not found. Install it with: pip install pyaudio")
    print("If installation fails, try: pip install pipwin && pipwin install pyaudio")

# Google Cloud Speech system not implemented yet
GOOGLE_SPEECH_AVAILABLE = False

class SpeechRecognitionSystem:
    """Handles speech-to-text functionality"""
    
    def __init__(self, config_manager):
        """Initialize the speech recognition system
        
        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager
        self.stt_config = config_manager.get_config("stt")
        
        # Check which engine to use
        self.engine = self.stt_config.get("engine", "google")
        
        # Google Cloud Speech not implemented yet - using standard Google Web Speech API
        
        if not SR_AVAILABLE:
            logging.error("Speech recognition dependencies not installed")
            return
            
        # Initialize speech recognition
        self.recognizer = sr.Recognizer()
        
        # Configure recognition parameters for natural speech patterns
        self.timeout = self.stt_config.get("timeout", 8)  # Longer timeout for natural speech
        self.language = self.stt_config.get("language", "en-US")
        self.energy_threshold = self.stt_config.get("energy_threshold", 600)  # Lowered from 2000 to 600 for better sensitivity
        self.pause_threshold = self.stt_config.get("pause_threshold", 1.2)  # More forgiving for natural pauses
        self.phrase_threshold = self.stt_config.get("phrase_threshold", 0.3)
        self.dynamic_energy = False
        
        # Apply configuration with proper validation
        self.recognizer.energy_threshold = self.energy_threshold
        self.recognizer.pause_threshold = max(1.0, self.pause_threshold)  # Ensure minimum 1.0s pause threshold
        self.recognizer.phrase_threshold = max(0.3, self.phrase_threshold)  # Ensure minimum phrase threshold
        self.recognizer.dynamic_energy_threshold = self.dynamic_energy
        
        # Ensure non_speaking_duration is properly set and within valid range
        # This parameter controls silence detection and must satisfy: pause_threshold >= non_speaking_duration >= 0
        safe_non_speaking = max(0.0, min(0.5, self.recognizer.pause_threshold - 0.5))
        self.recognizer.non_speaking_duration = safe_non_speaking
        
        # Validate that the assertion condition will be met
        if not (self.recognizer.pause_threshold >= self.recognizer.non_speaking_duration >= 0):
            logging.warning(f"Speech recognition parameter conflict detected (pause: {self.recognizer.pause_threshold}, non_speaking: {self.recognizer.non_speaking_duration}), resetting to safe defaults")
            self.recognizer.pause_threshold = 0.8
            self.recognizer.phrase_threshold = 0.3
            self.recognizer.non_speaking_duration = 0.3
        
        # Log the final configuration for debugging
        logging.info(f"Speech recognition parameters: energy_threshold={self.recognizer.energy_threshold}, pause_threshold={self.recognizer.pause_threshold}, non_speaking_duration={self.recognizer.non_speaking_duration}, phrase_threshold={self.recognizer.phrase_threshold}")
        print(f"🎚️ Speech Recognition Config: energy={self.recognizer.energy_threshold}, pause={self.recognizer.pause_threshold}, timeout={self.timeout}s")
        
        # Test microphone availability during initialization
        self._test_microphone_access()
        
        logging.info("Speech recognition system initialized")
        logging.info(f"Using language: {self.language}")
    
    def _test_microphone_access(self):
        """Test if microphone is accessible during initialization"""
        try:
            if not PYAUDIO_AVAILABLE:
                logging.warning("PyAudio not available - microphone access may fail")
                return False
            
            # Try to get available microphones
            mics = sr.Microphone.list_microphone_names()
            if len(mics) == 0:
                logging.warning("No microphones detected during initialization")
                return False
            
            # Try to create a microphone instance
            test_mic = sr.Microphone()
            logging.info(f"Microphone test successful. Found {len(mics)} microphones.")
            return True
            
        except Exception as e:
            logging.error(f"Microphone test failed during initialization: {e}")
            print(f"Warning: Microphone test failed: {e}")
            print("Speech recognition may not work properly.")
            return False
    
    def listen(self, hotkey_listener=None) -> Tuple[bool, Optional[str], Optional[str]]:
        """Listen for speech and convert to text
        
        Args:
            hotkey_listener: Optional hotkey listener to temporarily pause during listening
        
        Returns:
            Tuple containing:
                - Success status (bool)
                - Transcribed text if successful, None otherwise
                - Error message if unsuccessful, None otherwise
        """
        import time  # Import time at the beginning to avoid duplication
        
        if not SR_AVAILABLE:
            return False, None, "Speech recognition not available"
        
        # Temporarily pause hotkey listener to avoid Windows API conflicts
        hotkey_was_listening = False
        if hotkey_listener and hasattr(hotkey_listener, 'is_listening') and hotkey_listener.is_listening:
            try:
                hotkey_listener.stop_listening()
                hotkey_was_listening = True
                print("Temporarily stopped hotkey listener during speech recognition")
                # Give it time to fully stop
                time.sleep(0.2)
            except Exception as e:
                logging.debug(f"Could not stop hotkey listener: {e}")
            
        text = None
        error = None
        success = False
        
        try:
            # Indicate we're listening
            logging.info("Listening...")
            print("Listening for your command... Please speak now.")
            
            # Try to get available microphones with better error handling
            try:
                mics = sr.Microphone.list_microphone_names()
                print(f"Available microphones: {len(mics)}")
                if len(mics) > 0:
                    print(f"Using default microphone: {mics[0]}")
                else:
                    print("Warning: No microphones detected")
            except Exception as e:
                print(f"Could not list microphones: {e}")
                # Continue anyway as the default might still work
            
            # Initialize microphone with better error handling
            microphone = None
            try:
                microphone = sr.Microphone()
                print("Microphone initialized successfully")
            except Exception as e:
                logging.error(f"Failed to initialize microphone: {e}")
                return False, None, f"Microphone initialization failed: {str(e)}"
            
            # Use the microphone as the audio source with improved error handling
            try:
                with microphone as source:
                    print("Ready to listen...")
                    
                    # Skip ambient noise adjustment to preserve manual energy threshold
                    # This prevents the system from overriding our carefully configured threshold
                    print(f"Using fixed energy threshold: {self.recognizer.energy_threshold}")
                    print("Skipping ambient noise adjustment to preserve manual settings")
                    
                    print(f"Ready to capture your voice (timeout: {self.timeout}s)...")
                    
                    # Listen for audio input with improved error handling
                    try:
                        print(f"🔊 Listening with energy threshold: {self.recognizer.energy_threshold}")
                        audio = self.recognizer.listen(source, timeout=self.timeout, phrase_time_limit=10)
                        print("✅ Audio captured successfully!")
                    except sr.WaitTimeoutError:
                        # This is expected behavior - user didn't speak
                        logging.info("Speech recognition timeout - no speech detected")
                        print("Timeout - no speech detected, returning to standby")
                        return False, None, "timeout"
                    except sr.RequestError as req_error:
                        error_details = str(req_error) if str(req_error) else "Network/service error"
                        logging.error(f"Speech recognition request error: {error_details}")
                        print(f"Speech recognition request error: {error_details}")
                        return False, None, f"Speech service error: {error_details}"
                    except OSError as os_error:
                        error_details = str(os_error) if str(os_error) else "Operating system audio error"
                        logging.error(f"Operating system audio error: {error_details}")
                        print(f"Operating system audio error: {error_details}")
                        return False, None, f"System audio error: {error_details}"
                    except Exception as listen_error:
                        # Get much more detailed error information
                        error_type = type(listen_error).__name__
                        error_message = str(listen_error) if str(listen_error) else "No error message"
                        
                        # Additional debugging
                        import traceback
                        error_traceback = traceback.format_exc()
                        
                        logging.error(f"Error during listening - Type: {error_type}, Message: {error_message}")
                        logging.error(f"Traceback: {error_traceback}")
                        
                        print(f"Error during listening - Type: {error_type}")
                        print(f"Error message: {error_message}")
                        print("Please check that your microphone is properly connected and working.")
                        
                        # Check for specific error patterns
                        if "Input overflowed" in error_message:
                            return False, None, f"Microphone buffer overflow - try speaking more slowly"
                        elif "Device unavailable" in error_message:
                            return False, None, f"Microphone device not available - check if another app is using it"
                        elif "Permission" in error_message:
                            return False, None, f"Microphone permission denied - check Windows privacy settings"
                        elif "unanticipated host error" in error_message:
                            return False, None, f"Audio system error - try restarting the application"
                        else:
                            return False, None, f"Microphone access error: {error_type} - {error_message}"
                
                # Attempt to recognize speech
                print("Processing speech...")
                
                # Use try/except for each recognition attempt
                try:
                    engine = self.stt_config.get("engine", "google")
                    
                    if engine == "google":
                        text = self.recognizer.recognize_google(audio, language=self.language)
                    elif engine == "sphinx":
                        text = self.recognizer.recognize_sphinx(audio, language=self.language)
                    elif engine == "whisper":
                        text = self.recognizer.recognize_whisper(audio, language=self.language)
                    else:
                        # Default to Google
                        text = self.recognizer.recognize_google(audio, language=self.language)
                    
                    if text:
                        success = True
                        logging.info(f"Recognized: {text}")
                        print(f"Recognized: \"{text}\"")
                    else:
                        error = "I didn't hear anything. Please try speaking again."
                        logging.warning("Empty recognition result")
                        print("Empty recognition result")
                except sr.UnknownValueError:
                    error = "I couldn't understand that. Please try speaking more clearly."
                    logging.warning("Speech not understood")
                    print("Speech not understood - Could not recognize what was said.")
                except sr.RequestError as e:
                    error = f"Network issue with speech service: {str(e)}"
                    logging.error(f"Speech recognition request error: {e}")
                    print(f"Network error with speech recognition service: {e}")
                except Exception as recog_error:
                    error_msg = str(recog_error)
                    logging.error(f"Recognition engine error: {error_msg}")
                    print(f"Recognition engine error: {error_msg}")
                    error = f"Speech recognition failed: {error_msg or 'Unknown error'}"
                    
            except Exception as mic_error:
                logging.error(f"Microphone context error: {mic_error}")
                print(f"Microphone context error: {mic_error}")
                return False, None, f"Microphone context error: {str(mic_error)}"
            
        except Exception as e:
            # Capture and log the full traceback for better debugging
            tb = traceback.format_exc()
            error_msg = str(e) if str(e) else "Unknown error occurred"
            error = f"Speech recognition error: {error_msg}"
            logging.error(f"Speech recognition exception: {error_msg}")
            logging.error(f"Traceback: {tb}")
            print(f"Exception in speech recognition: {error_msg}")
        
        finally:
            # Restart hotkey listener if it was stopped
            if hotkey_was_listening and hotkey_listener:
                try:
                    # Give a moment before restarting
                    time.sleep(0.2)
                    hotkey_listener.start_listening()
                    print("Restarted hotkey listener after speech recognition")
                except Exception as e:
                    logging.debug(f"Could not restart hotkey listener: {e}")
                    print(f"Warning: Could not restart hotkey listener: {e}")
            
        return success, text, error
    
    def adjust_recognition_settings(self, 
                                   energy_threshold: Optional[int] = None,
                                   pause_threshold: Optional[float] = None,
                                   timeout: Optional[int] = None) -> None:
        """Adjust speech recognition settings
        
        Args:
            energy_threshold: Minimum audio energy to consider for recording
            pause_threshold: Seconds of non-speaking audio before a phrase is considered complete
            timeout: Maximum seconds to wait for a phrase to start
        """
        if not SR_AVAILABLE:
            return
            
        if energy_threshold is not None:
            self.energy_threshold = energy_threshold
            self.recognizer.energy_threshold = energy_threshold
            
        if pause_threshold is not None:
            self.pause_threshold = pause_threshold
            self.recognizer.pause_threshold = pause_threshold
            
        if timeout is not None:
            self.timeout = timeout
            
        logging.info(f"Recognition settings adjusted: energy={self.energy_threshold}, "
                    f"pause={self.pause_threshold}, timeout={self.timeout}")
