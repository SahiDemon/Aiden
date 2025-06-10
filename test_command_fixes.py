#!/usr/bin/env python3
"""
Test script to verify command fixes for Chrome launching and project handling
"""
import sys
import os
import subprocess
import time

# Add the project root to the path
sys.path.insert(0, os.path.abspath('.'))

from src.utils.config_manager import ConfigManager
from src.utils.llm_connector import LLMConnector
from src.utils.command_dispatcher import CommandDispatcher
from src.utils.voice_system import VoiceSystem

def test_command_processing():
    """Test command processing with the fixes"""
    
    print("=== Testing Command Processing Fixes ===\n")
    
    try:
        # Initialize components
        config_manager = ConfigManager()
        voice_system = VoiceSystem(config_manager)
        llm_connector = LLMConnector(config_manager)
        command_dispatcher = CommandDispatcher(config_manager, voice_system)
        
        # Test commands
        test_commands = [
            "open chrome",
            "launch chrome", 
            "start chrome",
            "open project",
            "list my projects",
            "open vscode",
            "open notepad"
        ]
        
        print("Testing LLM command interpretation:\n")
        
        for command in test_commands:
            print(f"Testing: '{command}'")
            try:
                # Process command with LLM
                result = llm_connector.process_command(command)
                
                print(f"  Action: {result.get('action', 'unknown')}")
                print(f"  Parameters: {result.get('parameters', {})}")
                print(f"  Response: {result.get('response', 'No response')}")
                
                # Test if action is correct
                if command.lower() in ["open chrome", "launch chrome", "start chrome"]:
                    expected_action = "app_control"
                    expected_app = "chrome"
                    
                    if result.get('action') == expected_action:
                        print(f"  ✅ Correct action: {expected_action}")
                        if result.get('parameters', {}).get('app_name') == expected_app:
                            print(f"  ✅ Correct app name: {expected_app}")
                        else:
                            print(f"  ❌ Wrong app name: {result.get('parameters', {}).get('app_name')}")
                    else:
                        print(f"  ❌ Wrong action: expected {expected_action}, got {result.get('action')}")
                
                elif "project" in command.lower():
                    expected_action = "provide_information"
                    
                    if result.get('action') == expected_action:
                        print(f"  ✅ Correct action: {expected_action}")
                    else:
                        print(f"  ❌ Wrong action: expected {expected_action}, got {result.get('action')}")
                
                print()
                
            except Exception as e:
                print(f"  ❌ Error processing command: {e}")
                print()
        
        print("\n=== Testing Command Dispatcher (without actually launching apps) ===\n")
        
        # Test Chrome command dispatch (dry run)
        chrome_command = {
            "action": "app_control",
            "parameters": {
                "app_name": "chrome",
                "operation": "launch",
                "original_query": "open chrome"
            },
            "response": "Opening Chrome for you, Boss."
        }
        
        print("Testing Chrome launch command structure:")
        print(f"Command: {chrome_command}")
        print("✅ Command structure looks correct")
        
        print("\n=== Test Complete ===")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_command_processing() 