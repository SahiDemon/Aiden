"""
Advanced Wake Word False Positive Debugger
Monitors BOTH Porcupine and Vosk simultaneously
Shows exactly what each model is detecting in real-time
"""
import asyncio
import json
import os
import sys
import time
import threading
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


class AdvancedWakeWordDebugger:
    """
    Advanced debugger that monitors both Porcupine and Vosk
    Shows what each model detects and helps identify false positive patterns
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.wake_word = self.settings.app.wake_word.lower()
        
        # Vosk model for continuous transcription
        self.model_path = self.settings.speech.vosk_model_path or "vosk_models/vosk-model-small-en-us-0.15"
        self.vosk_model = None
        self.vosk_recognizer = None
        
        # Porcupine (if available)
        self.porcupine = None
        self.use_porcupine = self.settings.speech.use_porcupine and self.settings.speech.porcupine_access_key
        
        # Audio
        self.audio = None
        self.stream = None
        self.sample_rate = 16000
        self.frame_length = 512  # For Porcupine
        
        # Logging
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_file = f"logs/wake_word_debug_{timestamp}.txt"
        self.audio_log_dir = f"logs/wake_word_audio_{timestamp}"
        os.makedirs(self.audio_log_dir, exist_ok=True)
        
        # Detection tracking
        self.vosk_detections = 0
        self.porcupine_detections = 0
        self.false_positives = 0
        self.true_positives = 0
        
        # Audio buffer (for saving clips)
        self.audio_buffer = []
        self.buffer_duration = 5.0  # seconds
        
        # For Vosk processing (needs larger chunks)
        self.vosk_buffer = b''
        self.vosk_chunk_size = 4000
        
        logger.info(f"Advanced Wake Word Debugger initialized")
        logger.info(f"Monitoring for wake word: '{self.wake_word}'")
        logger.info(f"Porcupine: {'ENABLED' if self.use_porcupine else 'DISABLED'}")
        logger.info(f"Log file: {self.log_file}")
        
        # Create log file
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("ADVANCED WAKE WORD DEBUG LOG\n")
            f.write(f"Wake Word: '{self.wake_word}'\n")
            f.write(f"Porcupine: {'ENABLED' if self.use_porcupine else 'DISABLED'}\n")
            f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
    
    def _load_vosk(self):
        """Load Vosk model"""
        try:
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Vosk model not found at: {self.model_path}")
            
            logger.info(f"Loading Vosk model from: {self.model_path}")
            self.vosk_model = vosk.Model(self.model_path)
            self.vosk_recognizer = vosk.KaldiRecognizer(self.vosk_model, self.sample_rate)
            self.vosk_recognizer.SetWords(True)
            
            logger.info("✓ Vosk model loaded")
            
        except Exception as e:
            logger.error(f"Failed to load Vosk: {e}")
            raise
    
    def _load_porcupine(self):
        """Load Porcupine model"""
        if not self.use_porcupine:
            return
        
        try:
            import pvporcupine
            
            access_key = self.settings.speech.porcupine_access_key
            model_path = self.settings.speech.porcupine_model_path
            sensitivity = self.settings.speech.porcupine_sensitivity
            
            if os.path.exists(model_path):
                self.porcupine = pvporcupine.create(
                    access_key=access_key,
                    keyword_paths=[model_path],
                    sensitivities=[sensitivity]
                )
                logger.info(f"✓ Porcupine loaded with custom model (sensitivity={sensitivity})")
            else:
                self.porcupine = pvporcupine.create(
                    access_key=access_key,
                    keywords=["computer"],
                    sensitivities=[sensitivity]
                )
                logger.warning("⚠ Using Porcupine with 'computer' keyword (custom model not found)")
            
            self.sample_rate = self.porcupine.sample_rate
            self.frame_length = self.porcupine.frame_length
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to load Porcupine: {error_msg}")
            
            # Check for version mismatch
            if "different version" in error_msg or "4.0.0" in error_msg or "3.0.0" in error_msg:
                logger.error("=" * 80)
                logger.error("PORCUPINE VERSION MISMATCH DETECTED!")
                logger.error("=" * 80)
                logger.error("Your model file version doesn't match the library version.")
                logger.error("")
                logger.error("Quick Fix Options:")
                logger.error("  1. Run: .\\fix_porcupine_version.ps1")
                logger.error("  2. Or disable Porcupine: Add SPEECH_USE_PORCUPINE=false to .env")
                logger.error("  3. Or upgrade: pip install --upgrade pvporcupine==3.0.5")
                logger.error("=" * 80)
            
            logger.warning("Continuing with Vosk only")
            self.use_porcupine = False
    
    def _log_event(self, source: str, event_type: str, text: str, energy: float, extra: str = ""):
        """Log an event"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        log_msg = f"[{timestamp}] [{source}] {event_type}\n"
        log_msg += f"  Text: '{text}'\n"
        log_msg += f"  Energy: {energy:.2f}\n"
        if extra:
            log_msg += f"  {extra}\n"
        log_msg += "\n"
        
        # Write to file
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_msg)
        
        # Print to console
        print(f"\n[{timestamp}] [{source}] {event_type}")
        print(f"  Text: '{text}'")
        print(f"  Energy: {energy:.2f}")
        if extra:
            print(f"  {extra}")
    
    def _save_audio_clip(self, filename: str):
        """Save current audio buffer to WAV file"""
        try:
            filepath = os.path.join(self.audio_log_dir, filename)
            
            # Combine audio chunks
            audio_bytes = b''.join(self.audio_buffer)
            
            # Save as WAV
            with wave.open(filepath, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_bytes)
            
            return filepath
            
        except Exception as e:
            logger.error(f"Error saving audio: {e}")
            return None
    
    def _calculate_energy(self, audio_data: bytes) -> float:
        """Calculate RMS energy"""
        try:
            audio_frame = np.frombuffer(audio_data, dtype=np.int16)
            rms = np.sqrt(np.mean(audio_frame.astype(np.float32) ** 2))
            return rms
        except:
            return 0.0
    
    def _play_detection_sound(self):
        """Play a beep sound when detection occurs"""
        try:
            import winsound
            # Play a beep: frequency=1000Hz, duration=200ms
            winsound.Beep(1000, 200)
        except Exception as e:
            # Fallback: print bell character
            print('\a', end='', flush=True)
    
    def _is_wake_word(self, text: str) -> bool:
        """Check if text matches wake word"""
        text = text.lower().strip()
        wake = self.wake_word.lower()
        
        # Exact match
        if wake in text:
            return True
        
        # Variations
        if wake == "aiden":
            variations = ["aidan", "ayden", "aden", "hey aiden", "ok aiden", "aid in", "aiding", "hayden"]
            for v in variations:
                if v in text:
                    return True
        
        # Fuzzy match
        if len(wake) >= 4:
            from difflib import SequenceMatcher
            for word in text.split():
                if abs(len(word) - len(wake)) <= 1:
                    similarity = SequenceMatcher(None, wake, word).ratio()
                    if similarity >= 0.85:  # Slightly more lenient for debugging
                        return True
        
        return False
    
    def _mark_detection(self, source: str, text: str, energy: float):
        """Handle a wake word detection"""
        # Play detection sound
        self._play_detection_sound()
        
        # Save audio clip
        clip_name = f"{source.lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        audio_path = self._save_audio_clip(clip_name)
        
        # Log
        self._log_event(
            source, 
            "*** WAKE WORD DETECTED ***", 
            text, 
            energy,
            f"Audio: {clip_name}"
        )
        
        # Update counters
        if source == "PORCUPINE":
            self.porcupine_detections += 1
        else:
            self.vosk_detections += 1
        
        # Ask user
        print(f"\n{'='*80}")
        print(f">>> WAKE WORD DETECTED by {source}")
        print(f">>> Audio saved: {audio_path}")
        print(f">>> Was this a FALSE POSITIVE?")
        print(f">>> Press 'f' for False Positive (timeout 15s): ", end='', flush=True)
        
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
                        print("f") # Echo
                        is_false_positive = True
                        # Consume any rapid extra keys
                        while msvcrt.kbhit(): msvcrt.getch()
                        break
                    else:
                        # Any other key acts as "skip/confirm" logic
                        print(" (ok)") 
                        break
                time.sleep(0.05)
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
        
        print() # Newline
        
        if is_false_positive:
            self.false_positives += 1
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"  >>> USER MARKED AS FALSE POSITIVE <<<\n\n")
            print(f"\n✗ FALSE POSITIVE (Total: {self.false_positives})")
        else:
            self.true_positives += 1
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"  >>> USER CONFIRMED: Actually spoke the wake word <<<\n\n")
            print(f"\n✓ MARKED AS USER SPOKE (Total: {self.true_positives})")
        
        print(f"{'='*80}\n")
        print("Continuing to listen...\n")
    
    async def run(self):
        """Main debug loop"""
        try:
            # Load models
            self._load_vosk()
            self._load_porcupine()
            
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
            
            print("\n" + "=" * 80)
            print("ADVANCED WAKE WORD DEBUGGER")
            print("=" * 80)
            print(f"Wake Word: '{self.wake_word}'")
            print(f"Porcupine: {'ENABLED' if self.use_porcupine else 'DISABLED'}")
            print(f"Vosk: ENABLED")
            print("\nSpeak normally - everything will be transcribed")
            print("When wake word is detected, mark it as false positive if needed")
            print("Press Ctrl+C to stop")
            print("=" * 80 + "\n")
            
            # Main loop
            while True:
                try:
                    # Read audio frame
                    audio_frame = self.stream.read(self.frame_length, exception_on_overflow=False)
                    
                    # Add to buffer
                    self.audio_buffer.append(audio_frame)
                    max_chunks = int(self.buffer_duration * self.sample_rate / self.frame_length)
                    if len(self.audio_buffer) > max_chunks:
                        self.audio_buffer.pop(0)
                    
                    # Calculate energy
                    energy = self._calculate_energy(audio_frame)
                    
                    # Process with Porcupine (if enabled)
                    if self.use_porcupine and self.porcupine:
                        try:
                            audio_array = np.frombuffer(audio_frame, dtype=np.int16)
                            keyword_index = self.porcupine.process(audio_array)
                            
                            if keyword_index >= 0:
                                # Porcupine detected wake word!
                                self._mark_detection("PORCUPINE", f"[Porcupine Detection #{keyword_index}]", energy)
                        
                        except Exception as e:
                            logger.error(f"Porcupine error: {e}")
                    
                    # Process with Vosk (accumulate frames)
                    self.vosk_buffer += audio_frame
                    
                    # Process Vosk when we have enough data
                    if len(self.vosk_buffer) >= self.vosk_chunk_size:
                        try:
                            if self.vosk_recognizer.AcceptWaveform(self.vosk_buffer):
                                result = json.loads(self.vosk_recognizer.Result())
                                text = result.get("text", "").strip()
                                
                                if text:
                                    # Check if wake word
                                    if self._is_wake_word(text):
                                        # Vosk detected wake word!
                                        self._mark_detection("VOSK", text, energy)
                                    else:
                                        # Regular transcription
                                        self._log_event("VOSK", "Transcription", text, energy)
                            
                            # Clear buffer
                            self.vosk_buffer = b''
                        
                        except Exception as e:
                            logger.error(f"Vosk error: {e}")
                            self.vosk_buffer = b''
                    
                    # Small delay
                    await asyncio.sleep(0.001)
                
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.error(f"Loop error: {e}")
                    await asyncio.sleep(0.1)
        
        except KeyboardInterrupt:
            print("\n\nStopping...")
        
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
            
            if self.porcupine:
                try:
                    self.porcupine.delete()
                except:
                    pass
            
            # Summary
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write("\n" + "=" * 80 + "\n")
                f.write("SESSION SUMMARY\n")
                f.write(f"Ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Porcupine Detections: {self.porcupine_detections}\n")
                f.write(f"Vosk Detections: {self.vosk_detections}\n")
                f.write(f"True Positives: {self.true_positives}\n")
                f.write(f"False Positives: {self.false_positives}\n")
                f.write("=" * 80 + "\n")
            
            print("\n" + "=" * 80)
            print("SESSION SUMMARY")
            print("=" * 80)
            print(f"Porcupine Detections: {self.porcupine_detections}")
            print(f"Vosk Detections: {self.vosk_detections}")
            print(f"True Positives: {self.true_positives}")
            print(f"False Positives: {self.false_positives}")
            if self.true_positives + self.false_positives > 0:
                accuracy = (self.true_positives / (self.true_positives + self.false_positives)) * 100
                print(f"Accuracy: {accuracy:.1f}%")
            print(f"\nLog: {self.log_file}")
            print(f"Audio: {self.audio_log_dir}")
            print("=" * 80 + "\n")


async def main():
    debugger = AdvancedWakeWordDebugger()
    await debugger.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
