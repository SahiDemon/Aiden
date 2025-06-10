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

class SpeechRecognitionSystem:
    """Handles speech-to-text functionality"""
    
    def __init__(self, config_manager):
        """Initialize the speech recognition system
        
        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager
        self.stt_config = config_manager.get_config("stt")
        
        if not SR_AVAILABLE:
            logging.error("Speech recognition dependencies not installed")
            return
            
        # Initialize speech recognition
        self.recognizer = sr.Recognizer()
        
        # Configure recognition parameters for faster, more responsive experience
        self.timeout = self.stt_config.get("timeout", 6)  # Shorter timeout
        self.language = self.stt_config.get("language", "en-US")
        self.energy_threshold = self.stt_config.get("energy_threshold", 2000)  # Lower for better sensitivity
        self.pause_threshold = self.stt_config.get("pause_threshold", 0.5)  # Balanced for natural speech
        self.phrase_threshold = self.stt_config.get("phrase_threshold", 0.3)
        self.dynamic_energy = True
        
        # Apply configuration
        self.recognizer.energy_threshold = self.energy_threshold
        self.recognizer.pause_threshold = self.pause_threshold
        self.recognizer.phrase_threshold = self.phrase_threshold
        self.recognizer.dynamic_energy_threshold = self.dynamic_energy
        
        logging.info("Speech recognition system initialized")
        logging.info(f"Using language: {self.language}")
    
    def listen(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """Listen for speech and convert to text
        
        Returns:
            Tuple containing:
                - Success status (bool)
                - Transcribed text if successful, None otherwise
                - Error message if unsuccessful, None otherwise
        """
        if not SR_AVAILABLE:
            return False, None, "Speech recognition not available"
            
        text = None
        error = None
        success = False
        
        try:
            # Indicate we're listening
            logging.info("Listening...")
            print("Listening for your command... Please speak now.")
            
            # Try to get available microphones
            try:
                mics = sr.Microphone.list_microphone_names()
                print(f"Available microphones: {len(mics)}")
                if len(mics) > 0:
                    print(f"Using default microphone: {mics[0]}")
            except Exception as e:
                print(f"Could not list microphones: {e}")
            
            # Use the default microphone as the audio source
            with sr.Microphone() as source:
                print("Ready to listen...")
                
                # Try to adjust for ambient noise, but continue even if it fails
                try:
                    print("Adjusting for ambient noise...")
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
                except Exception as e:
                    logging.warning(f"Could not adjust for ambient noise: {e}")
                    print(f"Warning: Could not adjust for ambient noise: {e}")
                    print("Continuing with default settings...")
                
                print(f"Ready to capture your voice (timeout: {self.timeout}s)...")
                
                # Listen for audio input
                try:
                    audio = self.recognizer.listen(source, timeout=self.timeout, phrase_time_limit=5)
                    print("Audio captured successfully!")
                except Exception as e:
                    logging.error(f"Error during listening: {e}")
                    print(f"Error during listening: {e}")
                    print("Please check that your microphone is properly connected and working.")
                    return False, None, f"Microphone access error: {str(e) or 'Unknown error'}"
            
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
                except Exception as recog_error:
                    error_msg = str(recog_error)
                    logging.error(f"Recognition engine error: {error_msg}")
                    print(f"Recognition engine error: {error_msg}")
                    return False, None, f"Speech recognition failed: {error_msg or 'Unknown error'}"
                    
        except sr.WaitTimeoutError:
            # This is a timeout - user didn't speak, return silent error
            error = "timeout"  # Special marker for timeout
            logging.info("Speech recognition timeout - no speech detected")
            print("Timeout - no speech detected, returning to standby")
            
        except sr.UnknownValueError:
            error = "I couldn't understand that. Please try speaking more clearly."
            logging.warning("Speech not understood")
            print("Speech not understood - Could not recognize what was said.")
            
        except sr.RequestError as e:
            error = f"Network issue with speech service: {str(e)}"
            logging.error(f"Speech recognition request error: {e}")
            print(f"Network error with speech recognition service: {e}")
            
        except Exception as e:
            # Capture and log the full traceback for better debugging
            tb = traceback.format_exc()
            error_msg = str(e) if str(e) else "Unknown error occurred"
            error = f"Speech recognition error: {error_msg}"
            logging.error(f"Speech recognition exception: {error_msg}")
            logging.error(f"Traceback: {tb}")
            print(f"Exception in speech recognition: {error_msg}")
            
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
