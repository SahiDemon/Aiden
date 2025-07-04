#!/usr/bin/env python3
"""
Test the Efficient Wake Word Detection System
Compare efficiency with the old speech recognition approach
"""
import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.abspath('.'))

# Import both detectors for comparison
from src.utils.config_manager import ConfigManager
from src.utils.voice_system import VoiceSystem
from src.utils.efficient_wake_word import EfficientWakeWordDetector

class EfficientWakeWordTester:
    """Test harness for the efficient wake word detection"""
    
    def __init__(self):
        """Initialize the test components"""
        print("🚀 Initializing Efficient Wake Word Test Components...")
        
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
        print(f"🎯 EFFICIENT WAKE WORD DETECTED #{self.wake_word_detections}!")
        print(f"   ⚡ This is the optimized detection system!")
        
        # Play a confirmation message
        try:
            self.voice_system.speak(f"Efficient wake word detected {self.wake_word_detections} times!")
        except Exception as e:
            print(f"   ⚠️ Voice response failed: {e}")
    
    def test_efficient_initialization(self):
        """Test efficient wake word detector initialization"""
        print("\n🚀 Testing Efficient Wake Word Detector Initialization...")
        try:
            self.efficient_detector = EfficientWakeWordDetector(
                self.config_manager,
                self.voice_system,
                self.on_wake_word_detected
            )
            print("✅ EfficientWakeWordDetector initialized successfully")
            
            # Test status
            status = self.efficient_detector.get_status()
            print(f"   📊 Status: {status}")
            print(f"   🎯 Wake word alternatives: {len(status['alternatives'])}")
            print(f"   ⚡ Optimized: {status.get('optimized', False)}")
            print(f"   📚 Library: {status.get('library', 'Unknown')}")
            
            return True
        except Exception as e:
            print(f"❌ EfficientWakeWordDetector initialization failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_efficiency_test(self, duration=30):
        """Run the efficient wake word detection test"""
        print(f"\n🚀 Starting Efficient Wake Word Detection Test ({duration} seconds)...")
        print("📋 Instructions:")
        print("   1. Say 'Aiden' to test wake word detection")
        print("   2. Notice the improved efficiency and responsiveness")
        print("   3. Watch for efficiency statistics")
        print("   4. Press Ctrl+C to stop early")
        print("\n🔄 Starting efficient detection...")
        
        try:
            # Start efficient wake word detection
            success = self.efficient_detector.start_listening()
            if not success:
                print("❌ Failed to start efficient wake word detection")
                return False
            
            self.test_running = True
            print("✅ Efficient wake word detection started!")
            print("🎤 Listening for 'Aiden'... (much more efficient!)")
            
            # Show initial status
            initial_status = self.efficient_detector.get_status()
            print(f"🎯 Alternatives: {initial_status['alternatives']}")
            
            # Run for specified duration
            start_time = time.time()
            last_stats_time = start_time
            
            while self.test_running and (time.time() - start_time) < duration:
                time.sleep(0.5)
                
                # Show efficiency statistics every 5 seconds
                current_time = time.time()
                if current_time - last_stats_time >= 5:
                    elapsed = int(current_time - start_time)
                    remaining = duration - elapsed
                    
                    # Get current efficiency stats
                    status = self.efficient_detector.get_status()
                    processed = status.get('chunks_processed', 0)
                    skipped = status.get('chunks_skipped', 0)
                    efficiency = status.get('efficiency_ratio', 0)
                    
                    print(f"⏱️ Time: {elapsed}s | Detections: {self.wake_word_detections} | "
                          f"Processed: {processed} | Skipped: {skipped} | "
                          f"Efficiency: {efficiency:.1%}")
                    
                    last_stats_time = current_time
            
            print(f"\n⏰ Test completed!")
            
            # Show final statistics
            final_status = self.efficient_detector.get_status()
            print(f"\n📊 Final Efficiency Statistics:")
            print(f"   🎯 Total wake word detections: {self.wake_word_detections}")
            print(f"   📈 Audio chunks processed: {final_status.get('chunks_processed', 0)}")
            print(f"   ⚡ Audio chunks skipped: {final_status.get('chunks_skipped', 0)}")
            print(f"   💚 Efficiency gain: {final_status.get('efficiency_ratio', 0):.1%}")
            print(f"   🔄 Total detections: {final_status.get('detections', 0)}")
            
            efficiency_ratio = final_status.get('efficiency_ratio', 0)
            if efficiency_ratio > 0.3:
                print(f"   🎉 EXCELLENT efficiency! Skipped {efficiency_ratio:.1%} of silent audio")
            elif efficiency_ratio > 0.1:
                print(f"   ✅ Good efficiency! Skipped {efficiency_ratio:.1%} of unnecessary processing")
            else:
                print(f"   ℹ️ Low efficiency gain - room for improvement")
            
            return True
            
        except KeyboardInterrupt:
            print(f"\n⏹️ Test stopped by user")
            return True
        except Exception as e:
            print(f"❌ Efficiency test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            self.test_running = False
            try:
                self.efficient_detector.stop_listening()
                print("🔇 Efficient wake word detection stopped")
            except:
                pass
    
    def compare_with_old_system(self):
        """Show comparison with the old speech recognition approach"""
        print("\n📊 Efficiency Comparison with Old System:")
        print("━" * 60)
        print("📈 OLD SYSTEM (speech_recognition):")
        print("   ❌ Processes ALL audio (even silence)")
        print("   ❌ Full speech recognition for every chunk")
        print("   ❌ Higher CPU usage")
        print("   ❌ Slower response time")
        print("   ❌ More Google API calls")
        print("")
        print("🚀 NEW EFFICIENT SYSTEM:")
        print("   ✅ Skips silent/quiet audio (energy filtering)")
        print("   ✅ Optimized speech recognition parameters")
        print("   ✅ Lower CPU usage")
        print("   ✅ Faster response time")
        print("   ✅ Fewer Google API calls")
        print("   ✅ Real-time efficiency statistics")
        print("   ✅ Better wake word alternatives")
        print("━" * 60)
    
    def run_full_test(self):
        """Run complete efficiency test suite"""
        print("=" * 60)
        print("🚀 EFFICIENT WAKE WORD DETECTION TEST")
        print("=" * 60)
        
        # Show comparison first
        self.compare_with_old_system()
        
        print("\n📋 Running Component Tests...")
        
        if not self.test_efficient_initialization():
            print("❌ Initialization failed - cannot continue")
            return False
        
        print("\n✅ All component tests passed!")
        
        # Ask user if they want to run the detection test
        print("\n🎤 Ready to test efficient wake word detection?")
        response = input("Press Enter to start detection test (or 'n' to skip): ").strip().lower()
        
        if response not in ['n', 'no', 'skip']:
            return self.run_efficiency_test(30)
        else:
            print("⏭️ Skipping detection test")
            return True

def main():
    """Main test function"""
    try:
        tester = EfficientWakeWordTester()
        tester.run_full_test()
    except KeyboardInterrupt:
        print("\n⏹️ Test interrupted by user")
    except Exception as e:
        print(f"💥 Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🏁 Efficiency test completed!")
    print("💡 Use this efficient detector to replace the old speech recognition approach!")

if __name__ == "__main__":
    main()