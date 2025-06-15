#!/usr/bin/env python3
"""
Test script to verify the hotkey activation fix (no greeting)
"""
import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.abspath('.'))

# Import components to simulate hotkey activation
from src.utils.config_manager import ConfigManager
from src.utils.voice_system import VoiceSystem
from src.dashboard_backend import AidenDashboardBackend

def test_hotkey_activation():
    """Test that hotkey activation doesn't play a greeting"""
    print("\n=== Testing Hotkey Activation (No Greeting) ===")
    
    # Create the necessary components
    config_manager = ConfigManager()
    voice_system = VoiceSystem(config_manager)
    
    # Test the voice_system directly
    print("\nTesting voice_system.say_greeting() (should only play sound, no speech):")
    voice_system.say_greeting()
    
    print("\nTesting voice_system.play_ready_sound() (should play the ready sound):")
    voice_system.play_ready_sound()
    
    print("\nSetup complete - press '*' to test the hotkey activation")
    print("Check if a greeting is spoken (it should NOT be)")

if __name__ == "__main__":
    test_hotkey_activation()
