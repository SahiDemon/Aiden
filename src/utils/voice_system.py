"""
Voice System for Aiden
Handles text-to-speech (TTS) functionality with natural voice output
"""
import os
import logging
import asyncio
import subprocess
import time
import random
from typing import Optional, List, Dict, Any
import platform

# Try to import optional dependencies
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    logging.warning("edge-tts not available, falling back to pyttsx3")

try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False
    logging.warning("pyttsx3 not available")

# Google TTS removed - not available in current setup
GOOGLE_TTS_AVAILABLE = False

# Try pygame for audio playback (preferred over playsound for newer Python versions)
try:
    import pygame
    PYGAME_AVAILABLE = True
    # Initialize pygame mixer
    pygame.mixer.init()
    print("Pygame mixer initialized successfully")
    print(f"Mixer settings: freq={pygame.mixer.get_init()}")
except ImportError:
    PYGAME_AVAILABLE = False
    logging.warning("pygame not available, trying alternative audio playback methods")
except Exception as e:
    PYGAME_AVAILABLE = False
    print(f"Error initializing pygame mixer: {e}")
    logging.warning(f"pygame mixer init failed: {e}")

# Fallback to playsound if pygame is not available
if not PYGAME_AVAILABLE:
    try:
        from playsound import playsound
        PLAYSOUND_AVAILABLE = True
    except ImportError:
        PLAYSOUND_AVAILABLE = False
        logging.warning("playsound not available, audio playback may be limited")
else:
    PLAYSOUND_AVAILABLE = False  # We'll prefer pygame if available

class VoiceSystem:
    """Handles text-to-speech functionality"""
    
    def __init__(self, config_manager):
        """Initialize the voice system
        
        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager
        self.voice_config = config_manager.get_config("voice")
        self.user_profile = config_manager.get_user_profile()
        
        # Set up voice preferences
        self.tts_engine = self.voice_config["tts_engine"]
        self.voice_id = self.voice_config["tts_voice"]
        self.rate = self.voice_config["tts_rate"]
        self.volume = self.voice_config["tts_volume"]
        
        # Get dynamic greeting options and sound effects settings
        self.use_sound_effects = self.voice_config.get("use_sound_effects", False)
        self.greeting_variations = self.voice_config.get("greeting_variations", [])
        
        # Override with user preferences if available
        user_voice = self.user_profile["preferences"]["voice"]
        if user_voice.get("tts_voice"):
            self.voice_id = user_voice["tts_voice"]
        if user_voice.get("speed"):
            self.rate = user_voice["speed"]
        if user_voice.get("volume"):
            self.volume = user_voice["volume"]
        
        # Initialize TTS engines
        self._init_tts_engines()
        
        # Google TTS removed - fallback to edge-tts if google-tts was configured
        if self.tts_engine == "google-tts":
            self.tts_engine = "edge-tts"
            logging.info("Google TTS not available, using edge-tts instead")
        
        # Create temp directory if it doesn't exist
        temp_dir = config_manager.get_config("general")["temp_dir"]
        os.makedirs(temp_dir, exist_ok=True)
        
        # Make sure we have absolute paths
        temp_dir_abs = os.path.abspath(temp_dir)
        
        # Use a unique filename based on timestamp to avoid conflicts
        import time
        self.temp_dir = temp_dir_abs
        self.temp_audio_path = os.path.join(temp_dir_abs, f"speech_{int(time.time())}.mp3")
        
        # Setup sound effects paths
        self.sounds_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "sounds")
        os.makedirs(self.sounds_dir, exist_ok=True)
        
        # Test file creation permission
        try:
            with open(self.temp_audio_path, 'w') as f:
                f.write("")
            os.remove(self.temp_audio_path)
            print(f"Successfully tested file permissions in temp directory: {temp_dir_abs}")
        except Exception as e:
            print(f"WARNING: Could not write to temp directory ({temp_dir_abs}): {e}")
            print("Falling back to system temp directory")
            import tempfile
            self.temp_dir = tempfile.gettempdir()
            self.temp_audio_path = os.path.join(self.temp_dir, f"aiden_speech_{int(time.time())}.mp3")
        
        logging.info(f"Voice system initialized with {self.tts_engine} engine")
        logging.info(f"Using voice: {self.voice_id}")
        
        # Create default sound effects if they don't exist
        self._create_default_sound_effects()
    
    def _create_default_sound_effects(self):
        """Create default sound effects if they don't exist"""
        # These are placeholder implementations - in a real scenario, 
        # you would include actual sound files in your project
        sound_effects = {
            "startup": "startup.mp3",
            "activation": "activation.mp3",
            "success": "success.mp3",
            "error": "error.mp3",
            "processing": "processing.mp3"
        }
        
        # Just log that we would create sound effects
        for effect, filename in sound_effects.items():
            path = os.path.join(self.sounds_dir, filename)
            if not os.path.exists(path):
                logging.info(f"Would create sound effect: {effect} at {path}")
    
    def _init_tts_engines(self):
        """Initialize available TTS engines"""
        self.edge_tts_available = EDGE_TTS_AVAILABLE
        self.pyttsx3_available = PYTTSX3_AVAILABLE
        
        # Initialize pyttsx3 engine if available (as fallback)
        if self.pyttsx3_available:
            try:
                self.pyttsx3_engine = pyttsx3.init()
                # Configure pyttsx3
                self.pyttsx3_engine.setProperty('rate', int(175 * self.rate))
                self.pyttsx3_engine.setProperty('volume', self.volume)
                
                # Try to find a female voice
                voices = self.pyttsx3_engine.getProperty('voices')
                for voice in voices:
                    # Look for female voice
                    if "female" in voice.name.lower():
                        self.pyttsx3_engine.setProperty('voice', voice.id)
                        break
            except Exception as e:
                logging.error(f"Error initializing pyttsx3: {e}")
                self.pyttsx3_available = False
    
    def _play_sound_effect(self, effect: str) -> None:
        """Play a sound effect
        
        Args:
            effect: Name of the sound effect to play (startup, activation, success, error, processing)
        """
        if not self.use_sound_effects:
            return
            
        effect_file = os.path.join(self.sounds_dir, f"{effect}.mp3")
        
        if not os.path.exists(effect_file):
            logging.warning(f"Sound effect not found: {effect_file}")
            return
            
        try:
            if PYGAME_AVAILABLE:
                sound = pygame.mixer.Sound(effect_file)
                sound.play()
            elif PLAYSOUND_AVAILABLE:
                playsound(effect_file, block=False)
            # Otherwise we just skip the sound effect
        except Exception as e:
            logging.error(f"Error playing sound effect: {e}")
    
    async def _edge_tts_speak(self, text: str, play_sound_effect: bool = False, effect: str = None) -> None:
        """Speak using edge-tts
        
        Args:
            text: Text to speak
            play_sound_effect: Whether to play a sound effect before speaking
            effect: Name of the sound effect to play
        """
        try:
            # Generate a completely new unique filename using uuid and process ID
            import uuid
            import time
            import os
            
            # Create a more unique filename that includes process ID to avoid conflicts
            unique_id = str(uuid.uuid4()).replace('-', '')[:8]
            timestamp = int(time.time())
            process_id = os.getpid()
            unique_path = os.path.join(self.temp_dir, f"speech_{unique_id}_{timestamp}_{process_id}.mp3")
            
            print(f"Generating speech to file: {unique_path}")
            
            # Play sound effect if requested
            if play_sound_effect and effect:
                self._play_sound_effect(effect)
            
            # Clean up any previous temp files to avoid accumulation
            try:
                if hasattr(self, 'temp_audio_path') and self.temp_audio_path and os.path.exists(self.temp_audio_path):
                    if self.temp_audio_path != unique_path:  # Don't delete the file we're about to create
                        os.remove(self.temp_audio_path)
            except Exception as cleanup_error:
                logging.debug(f"Could not clean up previous temp file: {cleanup_error}")
                
            # Use edge-tts's built-in rate parameter instead of SSML
            # Edge-TTS Communicate class supports rate parameter directly
            rate_value = "+15%"  # Moderately faster speech
            if self.rate > 1.2:
                rate_value = "+25%"  # Faster for users who prefer it
            elif self.rate < 0.8:
                rate_value = "+5%"  # Just slightly faster for slower preferences
            
            # Create communicate object with rate parameter
            communicate = edge_tts.Communicate(
                text=text, 
                voice=self.voice_id,
                rate=rate_value
            )
            await communicate.save(unique_path)
            
            # Update the path to use this file
            self.temp_audio_path = unique_path
            
            # Verify file was created successfully
            if not os.path.exists(unique_path):
                raise Exception(f"Failed to create audio file: {unique_path}")
            
            # Play the audio with improved error handling
            if PYGAME_AVAILABLE:
                try:
                    # Use pygame for audio playback
                    pygame.mixer.music.load(self.temp_audio_path)
                    pygame.mixer.music.play()
                    # Wait for playback to finish
                    while pygame.mixer.music.get_busy():
                        time.sleep(0.1)
                except Exception as pygame_error:
                    logging.warning(f"Pygame playback failed: {pygame_error}")
                    # Fall back to other methods
                    if PLAYSOUND_AVAILABLE:
                        playsound(self.temp_audio_path)
                    else:
                        self._fallback_audio_playback(self.temp_audio_path)
            elif PLAYSOUND_AVAILABLE:
                try:
                    playsound(self.temp_audio_path)
                except Exception as playsound_error:
                    logging.warning(f"Playsound playback failed: {playsound_error}")
                    self._fallback_audio_playback(self.temp_audio_path)
            else:
                self._fallback_audio_playback(self.temp_audio_path)
                    
        except Exception as e:
            logging.error(f"Error with edge-tts: {e}")
            # Fall back to pyttsx3 if available
            if self.pyttsx3_available:
                self._pyttsx3_speak(text)
            else:
                # Last resort - just print the text
                print(f"[SPEECH FALLBACK]: {text}")
    
    def _fallback_audio_playback(self, audio_file: str):
        """Fallback audio playback using OS-specific methods"""
        try:
            if platform.system() == "Windows":
                # Use Windows Media Player or default audio player
                import subprocess
                subprocess.run(['start', '', audio_file], shell=True, check=False)
            elif platform.system() == "Darwin":  # macOS
                subprocess.call(["afplay", audio_file])
            else:  # Linux
                subprocess.call(["aplay", audio_file])
        except Exception as fallback_error:
            logging.error(f"All audio playback methods failed: {fallback_error}")
            print(f"[AUDIO PLAYBACK FAILED]: Could not play audio file {audio_file}")
    
    def _pyttsx3_speak(self, text: str) -> None:
        """Speak using pyttsx3
        
        Args:
            text: Text to speak
        """
        try:
            self.pyttsx3_engine.say(text)
            self.pyttsx3_engine.runAndWait()
        except Exception as e:
            logging.error(f"Error with pyttsx3: {e}")
    
    def speak(self, text: str, play_sound_effect: bool = False, effect: str = None) -> None:
        """Speak text using the configured TTS engine
        
        Args:
            text: Text to speak
            play_sound_effect: Whether to play a sound effect before speaking
            effect: Name of the sound effect to play
        """
        if not text:
            return
            
        logging.info(f"Speaking: {text[:50]}{'...' if len(text) > 50 else ''}")
        
        # Pause wake word detection during TTS to prevent hearing our own voice
        if hasattr(self, 'wake_word_detector') and self.wake_word_detector:
            self.wake_word_detector.pause_listening()
        
        # Play sound effect if requested
        if play_sound_effect and effect:
            self._play_sound_effect(effect)
        
        try:
            if self.tts_engine == "edge-tts" and self.edge_tts_available:
                asyncio.run(self._edge_tts_speak(text, False, None))
            elif self.pyttsx3_available:
                self._pyttsx3_speak(text)
            else:
                logging.error("No TTS engine available")
                print(f"[SPEECH]: {text}")
        finally:
            # Resume wake word detection after TTS completes
            if hasattr(self, 'wake_word_detector') and self.wake_word_detector:
                self.wake_word_detector.resume_listening()
    
    def say_greeting(self) -> None:
        """Play just the activation sound without speaking a greeting"""
        # Play activation sound effect only
        if self.use_sound_effects:
            self._play_sound_effect("activation")
        
        # Don't speak a greeting anymore
        # Just log that activation happened
        logging.info("Voice activation sound played - no greeting spoken")
    
    def _get_proactive_greeting(self) -> str:
        """Generate a proactive, conversational greeting based on user history"""
        try:
            user_profile = self.config_manager.get_user_profile()
            user_name = user_profile.get("personal", {}).get("name", "")
            interactions = user_profile.get("history", {}).get("interactions", [])
            total_sessions = user_profile.get("history", {}).get("total_sessions", 0)
            
            # Get time-based greeting
            import datetime
            current_hour = datetime.datetime.now().hour
            
            if current_hour < 12:
                time_greeting = "Good morning"
            elif current_hour < 17:
                time_greeting = "Good afternoon" 
            else:
                time_greeting = "Good evening"
                
            # Base greeting with name
            base_greeting = f"{time_greeting}, {user_name}! What can I help you with today?"
            
            # Add proactive suggestions based on recent activity and patterns
            recent_interactions = interactions[-5:] if len(interactions) > 5 else interactions
            
            if total_sessions < 3:
                # New user - be more instructional
                return f"{time_greeting}, {user_name}! I'm Aiden, your AI assistant. Try asking me to open an app, check the weather, or control your fan!"
            
            # Check recent patterns for proactive suggestions
            has_recent_coding = any("vscode" in i.get("text", "").lower() or "code" in i.get("text", "").lower() for i in recent_interactions)
            has_recent_fan = any(i.get("type") == "fan_control" for i in recent_interactions)
            
            # Get last interaction time to see if it's a new session
            if interactions:
                last_interaction = interactions[-1].get("timestamp", "")
                if last_interaction:
                    try:
                        last_time = datetime.datetime.fromisoformat(last_interaction.replace("Z", "+00:00"))
                        time_diff = datetime.datetime.now() - last_time.replace(tzinfo=None)
                        hours_since_last = time_diff.total_seconds() / 3600
                        
                        if hours_since_last > 24:
                            return f"{time_greeting}, {user_name}! Welcome back! It's been a while - anything exciting happening in your projects?"
                        elif hours_since_last > 4:
                            if has_recent_coding:
                                return f"{time_greeting}, {user_name}! Ready to continue coding? I can help with your development workflow!"
                            else:
                                return f"{time_greeting}, {user_name}! What's on your agenda today? Any projects or tasks I can assist with?"
                    except:
                        pass
            
            # Regular session greetings with variety
            import random
            
            if has_recent_coding:
                coding_greetings = [
                    f"{time_greeting}, {user_name}! Ready to dive into some code? What are you working on?",
                    f"{time_greeting}, {user_name}! I see you've been coding lately - need help with your current project?",
                    f"{time_greeting}, {user_name}! Time to code! Want me to open your development tools or help brainstorm?"
                ]
                return random.choice(coding_greetings)
            
            elif has_recent_fan:
                return f"{time_greeting}, {user_name}! Need to adjust your workspace? I can control the fan or help with other tasks!"
            
            else:
                general_greetings = [
                    f"{time_greeting}, {user_name}! What do you have in mind today?",
                    f"{time_greeting}, {user_name}! Ready to get productive? What can I help you with?",
                    f"{time_greeting}, {user_name}! I'm here to help - any projects or questions for me?",
                    f"{time_greeting}, {user_name}! What brings you here today? Let's make something happen!"
                ]
                return random.choice(general_greetings)
                
        except Exception as e:
            logging.error(f"Error generating proactive greeting: {e}")
            # Fallback to default
            if self.greeting_variations and len(self.greeting_variations) > 0:
                return random.choice(self.greeting_variations)
            else:
                return self.config_manager.get_personalized_greeting()
    
    async def get_available_voices(self) -> List[Dict[str, Any]]:
        """Get list of available voices from edge-tts
        
        Returns:
            List of voice dictionaries with 'Name' and 'ShortName' keys
        """
        if not self.edge_tts_available:
            return []
            
        try:
            voices = await edge_tts.list_voices()
            return voices
        except Exception as e:
            logging.error(f"Error getting edge-tts voices: {e}")
            return []
            
    def change_voice(self, voice_id: str) -> bool:
        """Change the current voice
        
        Args:
            voice_id: ID of the voice to use
            
        Returns:
            True if voice was changed successfully, False otherwise
        """
        # Update the voice ID
        self.voice_id = voice_id
        
        # Update user profile
        self.config_manager.update_user_profile(
            section="preferences", 
            key="voice", 
            value={
                "tts_voice": voice_id,
                "speed": self.rate,
                "volume": self.volume
            }
        )
        
        logging.info(f"Voice changed to {voice_id}")
        
        # Play success sound effect
        if self.use_sound_effects:
            self._play_sound_effect("success")
            
        return True
    
    def play_ready_sound(self) -> None:
        """Play a sound to indicate Aiden is ready to listen"""
        try:
            # Try to find success.mp3 first
            possible_paths = [
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "sounds", "success.mp3"),
                os.path.join(os.getcwd(), "sounds", "success.mp3"),
                "sounds/success.mp3",
                "success.mp3"
            ]
            
            sound_played = False
            for sound_path in possible_paths:
                if os.path.exists(sound_path) and PYGAME_AVAILABLE:
                    try:
                        print(f"Playing sound from: {sound_path}")
                        sound = pygame.mixer.Sound(sound_path)
                        sound.set_volume(0.6)
                        sound.play()
                        print("Ready sound played successfully!")
                        logging.info(f"Ready sound played from {sound_path}")
                        sound_played = True
                        break
                    except Exception as e:
                        print(f"Error playing {sound_path}: {e}")
                        continue
            
            # If no file found, generate a simple beep
            if not sound_played and PYGAME_AVAILABLE:
                try:
                    print("Generating ready tone...")
                    # Generate a simple beep using pygame
                    import numpy as np
                    sample_rate = 22050
                    duration = 0.3  # seconds
                    frequency = 800  # Hz
                
                    # Generate sine wave
                    frames = int(duration * sample_rate)
                    t = np.linspace(0, duration, frames)
                    arr = np.sin(2 * np.pi * frequency * t)
                
                    # Apply fade to avoid clicks
                    fade_frames = int(0.05 * sample_rate)
                    arr[:fade_frames] *= np.linspace(0, 1, fade_frames)
                    arr[-fade_frames:] *= np.linspace(1, 0, fade_frames)
                
                    # Convert to 16-bit stereo
                    arr = (arr * 16383).astype(np.int16)
                    stereo_arr = np.zeros((frames, 2), dtype=np.int16)
                    stereo_arr[:, 0] = arr
                    stereo_arr[:, 1] = arr
                
                    # Play the sound
                    sound = pygame.sndarray.make_sound(stereo_arr)
                    sound.play()
                    print("Generated ready tone played!")
                    logging.info("Ready sound played (generated tone)")
                    sound_played = True
                except Exception as e:
                    print(f"Error generating tone: {e}")
            
            # Final fallback - Windows system beep
            if not sound_played:
                try:
                    import winsound
                    winsound.Beep(800, 200)  # 800Hz for 200ms
                    print("System beep played!")
                    logging.info("Ready sound played (system beep)")
                except:
                    logging.info("Ready to listen (silent)")
                    
        except Exception as e:
            logging.debug(f"Could not play ready sound: {e}")
            print("Ready to listen!")
