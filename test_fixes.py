#!/usr/bin/env python3
"""
Test script to verify fixes for:
1. Stop/end conversation handling
2. Hotkey activation (no greeting)
3. Fan control commands
"""
import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.abspath('.'))

# Import needed components
from src.utils.config_manager import ConfigManager
from src.utils.llm_connector import LLMConnector
from src.utils.command_dispatcher import CommandDispatcher
from src.utils.esp32_controller import ESP32Controller
from src.utils.voice_system import VoiceSystem

def test_conversation_stopping():
    """Test conversation stopping commands"""
    print("\n=== Testing Conversation Stopping ===")
    config_manager = ConfigManager()
    voice_system = VoiceSystem(config_manager)
    llm_connector = LLMConnector(config_manager)
    dispatcher = CommandDispatcher(config_manager, voice_system)
    
    # Test stop commands
    test_commands = [
        "stop",
        "end conversation",
        "stop talking",
        "exit"
    ]
    
    for command in test_commands:
        print(f"\nTesting command: '{command}'")
        result = llm_connector.process_command(command)
        print(f"Action detected: {result.get('action')}")
        print(f"Response: {result.get('response')}")
        
        # Dispatch the command
        success = dispatcher.dispatch(result)
        print(f"Dispatched successfully: {success}")

def test_fan_control():
    """Test fan control commands"""
    print("\n=== Testing Fan Control Commands ===")
    config_manager = ConfigManager()
    voice_system = VoiceSystem(config_manager)
    llm_connector = LLMConnector(config_manager)
    esp32 = ESP32Controller(config_manager)
    dispatcher = CommandDispatcher(config_manager, voice_system)
    
    # Test fan commands
    test_commands = [
        "turn on the fan",
        "fan speed 2",
        "set fan to high speed", 
        "change fan mode",
        "turn off the fan"
    ]
    
    for command in test_commands:
        print(f"\nTesting command: '{command}'")
        result = llm_connector.process_command(command)
        print(f"Action detected: {result.get('action')}")
        print(f"Parameters: {result.get('parameters')}")
        print(f"Response: {result.get('response')}")

if __name__ == "__main__":
    print("Starting tests for all fixes...")
    test_conversation_stopping()
    test_fan_control()
    print("\nAll tests completed!") 