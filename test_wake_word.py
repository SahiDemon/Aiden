#!/usr/bin/env python3
"""
Test script for Aiden Wake Word Detection
Tests the wake word detection system in isolation
"""
import sys
import os
import time
import threading

# Add project root to path
sys.path.insert(0, os.path.abspath('.'))

# Import required components
from src.utils.config_manager import ConfigManager
from src.utils.voice_system import VoiceSystem
from src.utils.wake_word_detector import WakeWordDetector

class WakeWordTester:
    """Test harness for wake word detection"""
    
    def __init__(self):
        """Initialize the test components"""
        print("🔧 Initializing Wake Word Test Components...")
        
        # Initialize core components
        try:
            self.config_manager = ConfigManager()
            print("✅ ConfigManager initialized")
        except Exception as e:
            print(f"❌ ConfigManager failed: {e}")
            return
            
        try:
            self.voice_system = VoiceSystem(self.config_manager)
            print("✅ VoiceSystem initialized")
        except Exception as e:
            print(f"❌ VoiceSystem failed: {e}")
            return
        
        # Test counter
        self.wake_word_detections = 0
        self.test_running = False
        
    def on_wake_word_detected(self):
        """Callback when wake word is detected"""
        self.wake_word_detections += 1
        print(f"🎯 WAKE WORD DETECTED #{self.wake_word_detections}!")
        print(f"   ✨ This is where Aiden would start listening for your command")
        
        # Play a confirmation message
        try:
            self.voice_system.speak(f"Wake word detected {self.wake_word_detections} times! I'm listening...")
        except Exception as e:
            print(f"   ⚠️ Voice response failed: {e}")
    
    def test_config_access(self):
        """Test configuration access"""
        print("\n🔍 Testing Configuration Access...")
        try:
            voice_config = self.config_manager.get_config("voice")
            print(f"✅ Voice config loaded: {len(voice_config)} settings")
            print(f"   📱 Sound effects enabled: {voice_config.get('use_sound_effects', 'Not set')}")
            return True
        except Exception as e:
            print(f"❌ Config access failed: {e}")
            return False
    
    def test_sound_files(self):
        """Test sound file availability"""
        print("\n🔊 Testing Sound Files...")
        sounds_dir = "sounds"
        wake_sounds = ["mmm1.MP3", "mmm2.MP3"]
        
        for sound in wake_sounds:
            sound_path = os.path.join(sounds_dir, sound)
            if os.path.exists(sound_path):
                print(f"✅ Found: {sound_path}")
            else:
                print(f"❌ Missing: {sound_path}")
        
        # Test pygame availability
        try:
            import pygame
            print("✅ pygame available for sound effects")
            return True
        except ImportError:
            print("❌ pygame not available - sound effects won't work")
            return False
    
    def test_speech_recognition(self):
        """Test speech recognition availability"""
        print("\n🎤 Testing Speech Recognition...")
        try:
            import speech_recognition as sr
            print("✅ SpeechRecognition library available")
            
            # Test microphone access
            recognizer = sr.Recognizer()
            mics = sr.Microphone.list_microphone_names()
            print(f"✅ Found {len(mics)} microphones")
            if len(mics) > 0:
                print(f"   🎙️ Default: {mics[0]}")
            
            return True
        except ImportError:
            print("❌ SpeechRecognition library not available")
            return False
        except Exception as e:
            print(f"⚠️ Speech recognition test warning: {e}")
            return True  # Continue anyway
    
    def test_wake_word_detector_init(self):
        """Test wake word detector initialization"""
        print("\n🎯 Testing Wake Word Detector Initialization...")
        try:
            self.wake_word_detector = WakeWordDetector(
                self.config_manager,
                self.voice_system,
                self.on_wake_word_detected
            )
            print("✅ WakeWordDetector initialized successfully")
            
            # Test status
            status = self.wake_word_detector.get_status()
            print(f"   📊 Status: {status}")
            
            return True
        except Exception as e:
            print(f"❌ WakeWordDetector initialization failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_detection_test(self, duration=30):
        """Run the actual wake word detection test"""
        print(f"\n🎙️ Starting Wake Word Detection Test ({duration} seconds)...")
        print("📋 Instructions:")
        print("   1. Say 'Aiden' to test wake word detection")
        print("   2. You should hear sound effects and voice confirmation")
        print("   3. Press Ctrl+C to stop early")
        print("\n🔄 Starting detection...")
        
        try:
            # Start wake word detection
            success = self.wake_word_detector.start_listening()
            if not success:
                print("❌ Failed to start wake word detection")
                return False
            
            self.test_running = True
            print("✅ Wake word detection started!")
            print("🎤 Listening for 'Aiden'... (speak now)")
            
            # Run for specified duration
            start_time = time.time()
            while self.test_running and (time.time() - start_time) < duration:
                time.sleep(0.5)
                # Show progress dots
                if int(time.time() - start_time) % 5 == 0:
                    elapsed = int(time.time() - start_time)
                    remaining = duration - elapsed
                    print(f"⏱️ Still listening... ({remaining}s remaining, {self.wake_word_detections} detections)")
                    time.sleep(1)  # Avoid rapid printing
            
            print(f"\n⏰ Test completed!")
            print(f"🎯 Total wake word detections: {self.wake_word_detections}")
            
            return True
            
        except KeyboardInterrupt:
            print(f"\n⏹️ Test stopped by user")
            print(f"🎯 Total wake word detections: {self.wake_word_detections}")
            return True
        except Exception as e:
            print(f"❌ Detection test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            self.test_running = False
            try:
                self.wake_word_detector.stop_listening()
                print("🔇 Wake word detection stopped")
            except:
                pass
    
    def run_full_test(self):
        """Run complete test suite"""
        print("=" * 50)
        print("🎯 AIDEN WAKE WORD DETECTION TEST")
        print("=" * 50)
        
        tests = [
            ("Config Access", self.test_config_access),
            ("Sound Files", self.test_sound_files),
            ("Speech Recognition", self.test_speech_recognition),
            ("Wake Word Detector Init", self.test_wake_word_detector_init),
        ]
        
        print("\n📋 Running Component Tests...")
        failed_tests = []
        
        for test_name, test_func in tests:
            try:
                if test_func():
                    print(f"✅ {test_name}: PASSED")
                else:
                    print(f"❌ {test_name}: FAILED")
                    failed_tests.append(test_name)
            except Exception as e:
                print(f"💥 {test_name}: ERROR - {e}")
                failed_tests.append(test_name)
        
        if failed_tests:
            print(f"\n❌ Some tests failed: {failed_tests}")
            print("🛠️ Please fix these issues before continuing")
            return False
        
        print("\n✅ All component tests passed!")
        
        # Ask user if they want to run the detection test
        print("\n🎤 Ready to test actual wake word detection?")
        response = input("Press Enter to start detection test (or 'n' to skip): ").strip().lower()
        
        if response not in ['n', 'no', 'skip']:
            return self.run_detection_test(30)
        else:
            print("⏭️ Skipping detection test")
            return True

def main():
    """Main test function"""
    try:
        tester = WakeWordTester()
        tester.run_full_test()
    except KeyboardInterrupt:
        print("\n⏹️ Test interrupted by user")
    except Exception as e:
        print(f"💥 Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🏁 Test completed!")

if __name__ == "__main__":
    main() 