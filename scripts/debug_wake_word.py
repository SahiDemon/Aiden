"""
Wake Word False Positive Debugger
Continuously records, transcribes, and logs what the wake word detector is hearing
Helps identify exactly what phrases trigger false positives
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from typing import Optional
import numpy as np
import pyaudio
import vosk
import wave

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class WakeWordDebugger:
    """
    Debugger that continuously transcribes audio and monitors wake word detection
    Logs everything to help identify false positive patterns
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.wake_word = self.settings.app.wake_word.lower()
        
        # Vosk model for continuous transcription
        self.model_path = self.settings.speech.vosk_model_path or "vosk_models/vosk-model-small-en-us-0.15"
        self.model = None
        self.recognizer = None
        
        # Audio
        self.audio = None
        self.stream = None
        self.sample_rate = 16000
        
        # Logging
        self.log_file = f"logs/wake_word_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        self.audio_log_dir = f"logs/wake_word_audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(self.audio_log_dir, exist_ok=True)
        
        # Detection tracking
        self.false_positive_count = 0
        self.true_positive_count = 0
        self.current_audio_buffer = []
        self.buffer_duration = 5.0  # Keep 5 seconds of audio
        
        # Wake word detection (simplified version for debugging)
        self.min_audio_energy = 150.0
        self.last_detection_time = 0
        self.debounce_time = 1.5
        
        logger.info(f"Wake Word Debugger initialized")
        logger.info(f"Monitoring for wake word: '{self.wake_word}'")
        logger.info(f"Log file: {self.log_file}")
        logger.info(f"Audio clips will be saved to: {self.audio_log_dir}")
        
        # Create log file with header
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("WAKE WORD FALSE POSITIVE DEBUG LOG\n")
            f.write(f"Wake Word: '{self.wake_word}'\n")
            f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
    
    def _load_model(self):
        """Load Vosk model for transcription"""
        try:
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Vosk model not found at: {self.model_path}")
            
            logger.info(f"Loading Vosk model from: {self.model_path}")
            self.model = vosk.Model(self.model_path)
            self.recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)
            self.recognizer.SetWords(True)
            
            logger.info("Vosk model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load Vosk model: {e}")
            raise
    
    def _play_detection_sound(self):
        """Play a beep sound when detection occurs"""
        try:
            import winsound
            # Play a beep: frequency=1000Hz, duration=200ms
            winsound.Beep(1000, 200)
        except Exception as e:
            # Fallback: print bell character
            print('\a', end='', flush=True)
    
    def _log_event(self, event_type: str, text: str, energy: float, timestamp: str, is_wake_word: bool = False):
        """Log an event to the debug log file"""
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {event_type}\n")
                f.write(f"  Text: '{text}'\n")
                f.write(f"  Energy: {energy:.2f}\n")
                if is_wake_word:
                    f.write(f"  *** WAKE WORD DETECTED ***\n")
                f.write("\n")
            
            # Play sound if wake word detected
            if is_wake_word:
                self._play_detection_sound()
            
            # Also print to console
            print(f"\n[{timestamp}] {event_type}")
            print(f"  Text: '{text}'")
            print(f"  Energy: {energy:.2f}")
            if is_wake_word:
                print(f"  *** WAKE WORD DETECTED ***")
                print(f"  Was this a FALSE POSITIVE? (Press 'f' within 3 seconds)")
        
        except Exception as e:
            logger.error(f"Error logging event: {e}")
    
    def _save_audio_clip(self, audio_data: list, filename: str):
        """Save audio clip to WAV file"""
        try:
            filepath = os.path.join(self.audio_log_dir, filename)
            
            # Combine audio chunks
            audio_bytes = b''.join(audio_data)
            
            # Save as WAV
            with wave.open(filepath, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_bytes)
            
            logger.info(f"Saved audio clip: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error saving audio clip: {e}")
            return None
    
    def _check_audio_energy(self, audio_data: bytes) -> float:
        """Calculate RMS energy of audio"""
        try:
            audio_frame = np.frombuffer(audio_data, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_frame.astype(np.float32) ** 2))
            return rms
        except Exception as e:
            logger.error(f"Error checking audio energy: {e}")
            return 0.0
    
    def _is_wake_word_match(self, text: str) -> bool:
        """Check if text matches wake word (same logic as production)"""
        text = text.lower().strip()
        wake = self.wake_word.lower()
        
        # Exact match
        if wake in text:
            return True
        
        # Common variations for "aiden"
        if wake == "aiden":
            variations = [
                "aidan", "ayden", "aden", "hey aiden", "ok aiden", "hayden", "aid in", "aiding"
            ]
            for variation in variations:
                if variation in text:
                    logger.debug(f"Matched variation: '{variation}' in '{text}'")
                    return True
        
        # Fuzzy match
        if len(wake) >= 4:
            from difflib import SequenceMatcher
            words = text.split()
            for word in words:
                if abs(len(word) - len(wake)) <= 1:
                    similarity = SequenceMatcher(None, wake, word).ratio()
                    if similarity >= 0.90:
                        logger.debug(f"Fuzzy matched: '{word}' (similarity: {similarity:.2f})")
                        return True
        
        return False
    
    def _should_process_detection(self) -> bool:
        """Check debounce"""
        current_time = time.time()
        time_since_last = current_time - self.last_detection_time
        
        if time_since_last < self.debounce_time:
            return False
        
        return True
    
    async def run(self):
        """Main debug loop"""
        try:
            # Load model
            self._load_model()
            
            # Initialize audio
            self.audio = pyaudio.PyAudio()
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=4000
            )
            self.stream.start_stream()
            
            logger.info("=" * 80)
            logger.info("WAKE WORD DEBUGGER STARTED")
            logger.info("Speak normally - everything will be transcribed and logged")
            logger.info("When wake word is detected, press 'f' within 3 seconds to mark as FALSE POSITIVE")
            logger.info("Press Ctrl+C to stop")
            logger.info("=" * 80)
            
            print("\n" + "=" * 80)
            print("LISTENING... (Speak normally)")
            print("=" * 80 + "\n")
            
            # Main loop
            while True:
                try:
                    # Read audio data
                    data = self.stream.read(4000, exception_on_overflow=False)
                    
                    # Add to buffer (for saving clips)
                    self.current_audio_buffer.append(data)
                    
                    # Keep buffer to ~5 seconds
                    max_chunks = int(self.buffer_duration * self.sample_rate / 4000)
                    if len(self.current_audio_buffer) > max_chunks:
                        self.current_audio_buffer.pop(0)
                    
                    # Calculate energy
                    energy = self._check_audio_energy(data)
                    
                    # Process with Vosk (final results only)
                    if self.recognizer.AcceptWaveform(data):
                        result = json.loads(self.recognizer.Result())
                        text = result.get("text", "").lower().strip()
                        
                        if text:
                            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                            
                            # Check if this matches wake word
                            is_wake_word = self._is_wake_word_match(text)
                            
                            if is_wake_word:
                                # Check debounce
                                if self._should_process_detection():
                                    # WAKE WORD DETECTED!
                                    self.last_detection_time = time.time()
                                    
                                    # Save audio clip
                                    clip_filename = f"detection_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
                                    audio_path = self._save_audio_clip(
                                        self.current_audio_buffer.copy(), 
                                        clip_filename
                                    )
                                    
                                    # Log the detection
                                    self._log_event("WAKE WORD DETECTION", text, energy, timestamp, is_wake_word=True)
                                    
                                    # Wait for user input (false positive marker)
                                    print(f"\n>>> Audio saved to: {audio_path}")
                                    print(">>> Press 'f' for False Positive (timeout 15s): ", end='', flush=True)
                                    
                                    is_false_positive = False
                                    wait_timeout = 15.0
                                    start_time = time.time()
                                    
                                    # Use msvcrt for reliable non-blocking input on Windows
                                    if os.name == 'nt':
                                        import msvcrt
                                        while (time.time() - start_time) < wait_timeout:
                                            if msvcrt.kbhit():
                                                char = msvcrt.getch()
                                                if char.lower() == b'f':
                                                    print("f")  # Echo
                                                    is_false_positive = True
                                                    # Consume any rapid extra keys
                                                    while msvcrt.kbhit(): msvcrt.getch()
                                                    break
                                                else:
                                                    # Any other key acts as "skip/confirm" logic
                                                    print(" (ok)")
                                                    break
                                            await asyncio.sleep(0.05)
                                    else:
                                        # Basic fallback for non-Windows
                                        import select
                                        try:
                                            r, _, _ = select.select([sys.stdin], [], [], wait_timeout)
                                            if r:
                                                if sys.stdin.readline().strip().lower().startswith('f'):
                                                    is_false_positive = True
                                        except:
                                            pass
                                    
                                    print()  # Newline
                                    
                                    try:
                                        if is_false_positive:
                                            with open(self.log_file, 'a', encoding='utf-8') as f:
                                                f.write(f"  >>> MARKED AS FALSE POSITIVE by user <<<\n")
                                                f.write(f"  >>> Audio clip: {clip_filename}\n\n")
                                            print(f"  ✓ Marked as FALSE POSITIVE (Total: {self.false_positive_count})")
                                        else:
                                            self.true_positive_count += 1
                                            with open(self.log_file, 'a', encoding='utf-8') as f:
                                                f.write(f"  >>> USER CONFIRMED: Actually spoke the wake word <<<\n")
                                                f.write(f"  >>> Audio clip: {clip_filename}\n\n")
                                            print(f"  ✓ MARKED AS USER SPOKE (Total: {self.true_positive_count})")
                                    
                                    except Exception as e:
                                        logger.debug(f"Input handling error: {e}")
                                        self.true_positive_count += 1
                                    
                                    print("\nContinuing to listen...\n")
                            
                            else:
                                # Regular transcription (not wake word)
                                self._log_event("TRANSCRIPTION", text, energy, timestamp, is_wake_word=False)
                    
                    # Small delay
                    await asyncio.sleep(0.01)
                    
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.error(f"Error in debug loop: {e}")
                    await asyncio.sleep(0.5)
            
        except KeyboardInterrupt:
            logger.info("\nStopping debugger...")
        except Exception as e:
            logger.error(f"Fatal error in debugger: {e}", exc_info=True)
        finally:
            # Cleanup
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
            
            # Write summary
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write("\n" + "=" * 80 + "\n")
                f.write("DEBUG SESSION SUMMARY\n")
                f.write(f"Ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"True Positives: {self.true_positive_count}\n")
                f.write(f"False Positives: {self.false_positive_count}\n")
                f.write("=" * 80 + "\n")
            
            logger.info("=" * 80)
            logger.info("DEBUG SESSION COMPLETE")
            logger.info(f"True Positives: {self.true_positive_count}")
            logger.info(f"False Positives: {self.false_positive_count}")
            logger.info(f"Log file: {self.log_file}")
            logger.info(f"Audio clips: {self.audio_log_dir}")
            logger.info("=" * 80)


async def main():
    """Entry point"""
    debugger = WakeWordDebugger()
    await debugger.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
