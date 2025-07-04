#!/usr/bin/env python3
"""
Test script for Vosk-based wake word detection
This uses proper trained models instead of generic speech recognition
"""
import time
import sys
import os
import logging

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.vosk_wake_word import VoskWakeWordDetector

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SimpleConfigManager:
    """Simple config manager for testing"""
    def get_config(self, key):
        configs = {
            "voice": {
                "use_sound_effects": True
            }
        }
        return configs.get(key, {})

def on_wake_word_detected():
    """Callback when wake word is detected"""
    print("🎉 WAKE WORD DETECTED BY VOSK! Ready for command...")
    time.sleep(0.5)  # Brief pause before next detection

def main():
    print("🎯 Testing Vosk Wake Word Detection with Trained Models")
    print("=" * 60)
    
    # Create simple config manager
    config_manager = SimpleConfigManager()
    
    # Initialize Vosk wake word detector
    print("🔧 Initializing Vosk wake word detector...")
    detector = VoskWakeWordDetector(
        config_manager=config_manager,
        voice_system=None,
        on_wake_word_detected=on_wake_word_detected
    )
    
    # Get status
    status = detector.get_status()
    print(f"📊 Detector Status:")
    for key, value in status.items():
        print(f"   {key}: {value}")
    print()
    
    # Check if model is loaded
    if not status.get('model_loaded', False):
        print("❌ Model not loaded. Vosk wake word detector cannot start.")
        return
    
    # Start detection
    print("🎤 Starting Vosk wake word detection...")
    success = detector.start_listening()
    
    if not success:
        print("❌ Failed to start Vosk wake word detection")
        return
    
    print("✅ Vosk wake word detection started!")
    print()
    print("🗣️  Say 'Aiden' (or variations like 'Hayden', 'Eden', etc.)")
    print("   This uses OFFLINE trained models - much more accurate!")
    print("   Press Ctrl+C to stop...")
    print()
    
    try:
        # Run for testing
        start_time = time.time()
        last_status_time = start_time
        
        while True:
            time.sleep(0.1)
            
            # Show status every 10 seconds
            current_time = time.time()
            if current_time - last_status_time >= 10:
                status = detector.get_status()
                elapsed = current_time - start_time
                print(f"⏱️  Status after {elapsed:.0f}s - Detections: {status['detections']}, "
                      f"Listening: {status['listening']}")
                last_status_time = current_time
                
    except KeyboardInterrupt:
        print("\n⏹️  Stopping test...")
        
    finally:
        # Stop detection
        detector.stop_listening()
        
        # Final statistics
        final_status = detector.get_status()
        total_time = time.time() - start_time
        
        print("\n" + "=" * 60)
        print("📊 Final Results:")
        print(f"   🎯 Total detections: {final_status['detections']}")
        print(f"   ⏱️  Total time: {total_time:.1f}s")
        print(f"   🎛️  Confidence threshold: {final_status['confidence_threshold']}")
        print(f"   📡 Offline: {final_status['offline']}")
        print(f"   🧠 Library: {final_status['library']}")
        
        if total_time > 0 and final_status['detections'] > 0:
            rate = final_status['detections'] / total_time * 60
            print(f"   📈 Detection rate: {rate:.1f} per minute")

if __name__ == "__main__":
    main() 