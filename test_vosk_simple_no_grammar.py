#!/usr/bin/env python3
"""
Simple Vosk Wake Word Test - No Grammar Restrictions
Uses the full vocabulary for better wake word detection
"""
import time
import json
import threading
import random

# Check for required imports
try:
    import vosk
    import pyaudio
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    print("❌ Vosk or PyAudio not available")

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

class SimpleVoskWakeWord:
    """Simplified Vosk wake word detector without grammar restrictions"""
    
    def __init__(self):
        self.is_listening = False
        self.should_stop = False
        self.detections = 0
        
        # Wake word alternatives
        self.wake_words = ["aiden", "hayden", "aden", "eden", "aided", "aidan", "hidden", "eating"]
        
        # Audio settings
        self.sample_rate = 16000
        self.chunk_size = 4000
        
        # Vosk components
        self.model = None
        self.recognizer = None
        self.audio_stream = None
        self.detection_thread = None
        
        # Sound effects
        self.sound_system_ready = False
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.init()
                self.sound_system_ready = True
            except:
                pass
        
        # Initialize model
        self._init_model()
    
    def _init_model(self):
        """Initialize Vosk model"""
        if not VOSK_AVAILABLE:
            return False
            
        model_path = "vosk_models/vosk-model-small-en-us-0.15"
        try:
            print(f"🧠 Loading Vosk model...")
            self.model = vosk.Model(model_path)
            self.recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)
            print(f"✅ Model loaded successfully!")
            return True
        except Exception as e:
            print(f"❌ Model error: {e}")
            return False
    
    def start_listening(self):
        """Start wake word detection"""
        if not self.model:
            print("❌ Model not loaded")
            return False
            
        self.is_listening = True
        self.should_stop = False
        self.detections = 0
        
        self.detection_thread = threading.Thread(target=self._detection_loop, daemon=True)
        self.detection_thread.start()
        
        print("🎯 Vosk wake word detection started!")
        return True
    
    def stop_listening(self):
        """Stop detection"""
        self.should_stop = True
        self.is_listening = False
        
        if self.audio_stream:
            try:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
            except:
                pass
                
        print("🔇 Detection stopped")
    
    def _detection_loop(self):
        """Main detection loop"""
        try:
            audio = pyaudio.PyAudio()
            
            self.audio_stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size
            )
            
            print(f"🎤 Audio stream started (16kHz)")
            
            while not self.should_stop:
                try:
                    # Read audio
                    data = self.audio_stream.read(self.chunk_size, exception_on_overflow=False)
                    
                    # Process with Vosk
                    if self.recognizer.AcceptWaveform(data):
                        # Final result
                        result = json.loads(self.recognizer.Result())
                        self._process_result(result, final=True)
                    else:
                        # Partial result
                        result = json.loads(self.recognizer.PartialResult())
                        self._process_result(result, final=False)
                            
                except Exception as e:
                    print(f"⚠️  Audio error: {e}")
                    time.sleep(0.1)
                    
        except Exception as e:
            print(f"❌ Fatal error: {e}")
        finally:
            if self.audio_stream:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
            audio.terminate()
    
    def _process_result(self, result, final=False):
        """Process recognition result"""
        if final:
            text = result.get('text', '').lower().strip()
        else:
            text = result.get('partial', '').lower().strip()
        
        if text:
            confidence = result.get('confidence', 0.0)
            prefix = "🗣️ " if final else "👂"
            print(f"{prefix} {text} {f'(conf: {confidence:.1%})' if final else ''}")
            
            # Check for wake words (only in final results)
            if final:
                for wake_word in self.wake_words:
                    if wake_word in text:
                        print(f"🎯 WAKE WORD: '{wake_word}' in '{text}' (conf: {confidence:.1%})")
                        self._handle_detection(wake_word, text, confidence)
                        break
    
    def _handle_detection(self, wake_word, full_text, confidence):
        """Handle wake word detection"""
        self.detections += 1
        
        # Play sound
        self._play_sound()
        
        print(f"🎉 DETECTION #{self.detections}: '{wake_word}'")
        time.sleep(1)  # Brief pause
    
    def _play_sound(self):
        """Play detection sound"""
        if not self.sound_system_ready:
            return
            
        try:
            sounds = ["sounds/mmm1.MP3", "sounds/mmm2.MP3"]
            for sound_file in sounds:
                try:
                    sound = pygame.mixer.Sound(sound_file)
                    sound.play()
                    print(f"🔊 *mmm*")
                    break
                except:
                    continue
        except Exception as e:
            print(f"🔇 Sound error: {e}")

def main():
    print("🎯 Simple Vosk Wake Word Test (Full Vocabulary)")
    print("=" * 55)
    
    detector = SimpleVoskWakeWord()
    
    if not detector.start_listening():
        print("❌ Failed to start detection")
        return
    
    print("🗣️  Say 'Aiden' or any variation...")
    print("   Wake words: aiden, hayden, aden, eden, aided, aidan")
    print("   Press Ctrl+C to stop...")
    print()
    
    try:
        start_time = time.time()
        
        while True:
            time.sleep(1)
            
            # Status every 15 seconds
            elapsed = time.time() - start_time
            if int(elapsed) % 15 == 0 and int(elapsed) > 0:
                print(f"⏱️  Status: {detector.detections} detections in {elapsed:.0f}s")
                
    except KeyboardInterrupt:
        print("\n⏹️  Stopping...")
    finally:
        detector.stop_listening()
        
        total_time = time.time() - start_time
        print("\n" + "=" * 55)
        print("📊 Results:")
        print(f"   🎯 Detections: {detector.detections}")
        print(f"   ⏱️  Time: {total_time:.1f}s")
        if detector.detections > 0:
            rate = detector.detections / total_time * 60
            print(f"   📈 Rate: {rate:.1f} detections/minute")

if __name__ == "__main__":
    main() 