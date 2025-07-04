#!/usr/bin/env python3
"""
Speech Recognition Debug Test
Tests what the speech recognition system is actually hearing
"""
import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.abspath('.'))

try:
    import speech_recognition as sr
except ImportError:
    print("❌ speech_recognition library not installed")
    sys.exit(1)

class SpeechDebugger:
    """Debug speech recognition to see what's being heard"""
    
    def __init__(self):
        """Initialize speech recognition"""
        self.recognizer = sr.Recognizer()
        
        # Use the same parameters as wake word detector
        self.recognizer.energy_threshold = 800
        self.recognizer.pause_threshold = 0.4
        self.recognizer.phrase_threshold = 0.2
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.non_speaking_duration = 0.2
        
        print("🎤 Speech Recognition Debug Test")
        print("=" * 40)
        
    def test_microphone_levels(self):
        """Test microphone input levels"""
        print("\n🔊 Testing Microphone Levels...")
        
        try:
            with sr.Microphone() as source:
                print("📏 Measuring ambient noise levels...")
                self.recognizer.adjust_for_ambient_noise(source, duration=2)
                print(f"   🎚️ Energy threshold after adjustment: {self.recognizer.energy_threshold}")
                
                print("\n🎙️ Speak loudly now to test microphone levels...")
                for i in range(5):
                    try:
                        print(f"   Test {i+1}/5: Speak now...")
                        audio = self.recognizer.listen(source, timeout=3, phrase_time_limit=2)
                        print(f"   ✅ Audio captured! Length: {len(audio.frame_data)} bytes")
                        
                        # Try to recognize
                        try:
                            text = self.recognizer.recognize_google(audio, language="en-US")
                            print(f"   🎯 Recognized: '{text}'")
                        except sr.UnknownValueError:
                            print(f"   ⚠️ Audio captured but not recognized as speech")
                        except sr.RequestError as e:
                            print(f"   ❌ Recognition service error: {e}")
                            
                    except sr.WaitTimeoutError:
                        print(f"   ⏰ No speech detected in timeout period")
                    
                    time.sleep(0.5)
                    
        except Exception as e:
            print(f"❌ Microphone test failed: {e}")
            
    def test_wake_word_recognition(self):
        """Test specific wake word recognition"""
        print("\n🎯 Testing Wake Word Recognition...")
        print("Say 'Aiden' or variations: 'Eden', 'Aden', 'Hayden'")
        
        wake_words = ["aiden", "eden", "aden", "hayden"]
        
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                
                for attempt in range(10):
                    print(f"\n🎤 Attempt {attempt + 1}/10: Say 'Aiden' now...")
                    
                    try:
                        audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=3)
                        print("   ✅ Audio captured, processing...")
                        
                        try:
                            text = self.recognizer.recognize_google(audio, language="en-US").lower().strip()
                            print(f"   📝 Full recognition: '{text}'")
                            
                            # Check for wake words
                            found_wake_word = False
                            for word in wake_words:
                                if word in text:
                                    print(f"   🎉 WAKE WORD FOUND: '{word}' in '{text}'")
                                    found_wake_word = True
                                    break
                            
                            if not found_wake_word:
                                print(f"   ℹ️ No wake word detected in: '{text}'")
                                
                        except sr.UnknownValueError:
                            print("   ⚠️ Speech not understood")
                        except sr.RequestError as e:
                            print(f"   ❌ Recognition error: {e}")
                            
                    except sr.WaitTimeoutError:
                        print("   ⏰ No speech detected - try speaking louder/clearer")
                        
        except Exception as e:
            print(f"❌ Wake word test failed: {e}")
            
    def test_continuous_recognition(self):
        """Test continuous recognition like the wake word detector"""
        print("\n🔄 Testing Continuous Recognition...")
        print("This mimics the wake word detector behavior")
        print("Press Ctrl+C to stop")
        
        detections = 0
        attempts = 0
        
        try:
            while True:
                attempts += 1
                print(f"\n🎤 Listening attempt #{attempts}...")
                
                try:
                    with sr.Microphone() as source:
                        # Quick ambient adjustment
                        self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                        
                        try:
                            audio = self.recognizer.listen(source, timeout=2, phrase_time_limit=2)
                            
                            try:
                                text = self.recognizer.recognize_google(audio, language="en-US").lower().strip()
                                print(f"   📝 Heard: '{text}'")
                                
                                # Check for wake words
                                wake_words = ["aiden", "eden", "aden", "hayden"]
                                for word in wake_words:
                                    if word in text:
                                        detections += 1
                                        print(f"   🎯 WAKE WORD #{detections}: '{word}' detected!")
                                        
                            except sr.UnknownValueError:
                                print("   👂 Listening...")
                            except sr.RequestError as e:
                                print(f"   ⚠️ Service error: {e}")
                                
                        except sr.WaitTimeoutError:
                            print("   👂 Listening...")
                            
                except Exception as e:
                    print(f"   ❌ Error: {e}")
                    
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print(f"\n⏹️ Test stopped!")
            print(f"📊 Results: {detections} wake word detections in {attempts} attempts")
            
    def run_all_tests(self):
        """Run complete diagnostic test suite"""
        print("🔍 Starting Speech Recognition Diagnostics...")
        
        print("\n" + "="*50)
        self.test_microphone_levels()
        
        print("\n" + "="*50)
        self.test_wake_word_recognition()
        
        print("\n" + "="*50)
        response = input("\nRun continuous test? (y/n): ").strip().lower()
        if response in ['y', 'yes']:
            self.test_continuous_recognition()

def main():
    """Main function"""
    debugger = SpeechDebugger()
    debugger.run_all_tests()

if __name__ == "__main__":
    main() 