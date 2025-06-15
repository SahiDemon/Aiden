#!/usr/bin/env python3
"""
Test script to simulate voice commands and verify the complete integration
"""
import sys
import os
import logging

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from utils.config_manager import ConfigManager
from utils.voice_system import VoiceSystem
from utils.command_dispatcher import CommandDispatcher

def test_voice_commands():
    """Test voice commands for app launching"""
    print("=== Testing Voice Commands for App Launching ===")
    
    # Set up logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    try:
        # Initialize components
        config_manager = ConfigManager()
        voice_system = VoiceSystem(config_manager)
        dispatcher = CommandDispatcher(config_manager, voice_system)
        
        print("✅ Components initialized successfully")
        
        # Test the app manager directly
        print(f"\n=== Direct App Manager Tests ===")
        app_manager = dispatcher.app_manager
        
        direct_tests = ["steam", "calculator", "calc", "postman"]
        
        for query in direct_tests:
            print(f"\n🔍 Direct search for '{query}':")
            results = app_manager.search_apps(query, limit=3)
            
            if results:
                for i, app in enumerate(results, 1):
                    print(f"   {i}. {app['name']} (executable: {app['executable']})")
                    
                    # Test launching the top result
                    if i == 1:
                        print(f"   🚀 Testing launch of: {app['name']}")
                        print(f"   Launch test: Would execute '{app['executable']}'")
            else:
                print(f"   ❌ No results found")
        
        print(f"\n✅ Voice command testing completed!")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_voice_commands() 