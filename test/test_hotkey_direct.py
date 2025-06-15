#!/usr/bin/env python3
"""
Direct test for hotkey detection to debug capture issues
"""
import sys
import os
import time
import threading

# Add project root to path
sys.path.insert(0, os.path.abspath('.'))

try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
    print("✅ pynput is available")
except ImportError as e:
    PYNPUT_AVAILABLE = False
    print(f"❌ pynput is NOT available: {e}")

def test_direct_hotkey():
    """Test direct hotkey detection"""
    print("\n=== Direct Hotkey Detection Test ===")
    
    if not PYNPUT_AVAILABLE:
        print("❌ Cannot test - pynput not available")
        print("Run: pip install pynput")
        return
    
    print("🎯 Starting direct keyboard listener...")
    print("Press the * key to test detection")
    print("Press ESC to stop test")
    
    def on_press(key):
        try:
            print(f"Key pressed: {key}")
            
            # Check for asterisk in multiple ways
            if hasattr(key, 'char'):
                print(f"  - Character: '{key.char}'")
                if key.char == '*':
                    print("🎉 ASTERISK DETECTED!")
                    return
            
            # Check for escape to stop
            if key == keyboard.Key.esc:
                print("ESC pressed - stopping test")
                return False
                
        except AttributeError:
            print(f"Special key: {key}")
            if key == keyboard.Key.esc:
                return False
    
    def on_release(key):
        if key == keyboard.Key.esc:
            return False
    
    try:
        print("🔄 Starting listener...")
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            print("✅ Listener started - Press * or ESC")
            listener.join()
        print("🛑 Listener stopped")
        
    except Exception as e:
        print(f"❌ Error: {e}")

def test_our_hotkey_listener():
    """Test our actual hotkey listener"""
    print("\n=== Testing Our Hotkey Listener ===")
    
    try:
        from src.utils.config_manager import ConfigManager
        from src.utils.hotkey_listener import HotkeyListener
        
        config_manager = ConfigManager()
        
        activation_count = 0
        def test_callback():
            nonlocal activation_count
            activation_count += 1
            print(f"🎉 HOTKEY ACTIVATED! (Count: {activation_count})")
        
        print("🔄 Creating hotkey listener...")
        hotkey_listener = HotkeyListener(config_manager, test_callback)
        
        print("🔄 Starting hotkey listener...")
        success = hotkey_listener.start_listening()
        
        if success:
            print("✅ Hotkey listener started successfully")
            print("Press * key to test...")
            print("Press Ctrl+C to stop")
            
            try:
                # Keep running until interrupted
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n🛑 Stopping...")
                hotkey_listener.stop_listening()
                print(f"Total activations: {activation_count}")
        else:
            print("❌ Failed to start hotkey listener")
            
    except Exception as e:
        print(f"❌ Error testing our hotkey listener: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=== HOTKEY DETECTION DEBUG ===")
    
    # Test 1: Direct pynput test
    test_direct_hotkey()
    
    # Test 2: Our hotkey listener
    test_our_hotkey_listener() 