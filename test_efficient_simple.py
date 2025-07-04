#!/usr/bin/env python3
"""
Simple test for Efficient Wake Word Detection
"""
import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.abspath('.'))

print("🚀 Loading Efficient Wake Word Detection...")

try:
    from src.utils.config_manager import ConfigManager
    from src.utils.voice_system import VoiceSystem
    from src.utils.efficient_wake_word import EfficientWakeWordDetector
    print("✅ All modules loaded successfully")
except Exception as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

def main():
    """Simple test of efficient wake word detection"""
    
    print("\n🔧 Initializing components...")
    
    # Initialize components
    config = ConfigManager()
    voice = VoiceSystem(config)
    
    # Detection counter
    detections = 0
    
    def on_wake_word():
        global detections
        detections += 1
        print(f"\n🎉 WAKE WORD DETECTED #{detections}!")
        print("   ⚡ Efficient detection working!")
        
    # Create efficient detector
    detector = EfficientWakeWordDetector(config, voice, on_wake_word)
    
    # Show status
    status = detector.get_status()
    print(f"\n📊 Detector Status:")
    print(f"   🎯 Wake word alternatives: {len(status['alternatives'])}")
    print(f"   ⚡ Optimized: {status.get('optimized', False)}")
    print(f"   📚 Library: {status.get('library', 'Unknown')}")
    
    print(f"\n🎤 Starting efficient wake word detection...")
    print(f"Say any of these words: {', '.join(status['alternatives'][:5])}...")
    print(f"Press Ctrl+C to stop")
    
    try:
        # Start detection
        detector.start_listening()
        
        # Run for 30 seconds or until interrupted
        start_time = time.time()
        while time.time() - start_time < 30:
            time.sleep(1)
            
            # Show efficiency stats every 5 seconds
            if int(time.time() - start_time) % 5 == 0:
                current_status = detector.get_status()
                processed = current_status.get('chunks_processed', 0)
                skipped = current_status.get('chunks_skipped', 0)
                efficiency = current_status.get('efficiency_ratio', 0)
                
                print(f"⏱️ {int(time.time() - start_time)}s | "
                      f"Detections: {detections} | "
                      f"Processed: {processed} | "
                      f"Skipped: {skipped} | "
                      f"Efficiency: {efficiency:.1%}")
        
        print(f"\n✅ Test completed!")
        
    except KeyboardInterrupt:
        print(f"\n⏹️ Test stopped by user")
    
    finally:
        detector.stop_listening()
        
        # Final stats
        final_status = detector.get_status()
        print(f"\n📊 Final Results:")
        print(f"   🎯 Total detections: {detections}")
        print(f"   📈 Chunks processed: {final_status.get('chunks_processed', 0)}")
        print(f"   ⚡ Chunks skipped: {final_status.get('chunks_skipped', 0)}")
        print(f"   💚 Efficiency gain: {final_status.get('efficiency_ratio', 0):.1%}")

if __name__ == "__main__":
    main() 