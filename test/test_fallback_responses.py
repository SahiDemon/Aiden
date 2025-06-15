#!/usr/bin/env python3
"""
Test script to verify fallback responses work correctly for common commands
"""
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.abspath('.'))

from src.utils.config_manager import ConfigManager
from src.utils.llm_connector import LLMConnector

def test_fallback_responses():
    """Test the fallback responses directly"""
    
    print("=== Testing Fallback Responses ===\n")
    
    try:
        # Initialize components
        config_manager = ConfigManager()
        llm_connector = LLMConnector(config_manager)
        
        # Test commands that should trigger fallback responses
        test_commands = [
            "open chrome",
            "launch chrome", 
            "start chrome",
            "open vscode",
            "open edge",
            "open firefox",
            "open notepad",
            "open calculator",
            "open explorer",
            "open terminal",
            "open project",
            "list my projects",
            "search for python tutorials",
            "hello",
            "how are you",
            "what time is it"
        ]
        
        print("Testing fallback response generation:\n")
        
        for command in test_commands:
            print(f"Testing: '{command}'")
            
            # Set the command as last_command
            llm_connector.last_command = command
            
            # Simulate a short/empty response from tgpt to trigger fallback
            fallback_response = llm_connector._clean_tgpt_output("")
            
            print(f"  Fallback response: {fallback_response[:100]}...")
            
            # Parse the fallback response
            try:
                parsed = llm_connector._parse_llm_response(fallback_response)
                print(f"  Action: {parsed.get('action', 'unknown')}")
                print(f"  App name: {parsed.get('parameters', {}).get('app_name', 'N/A')}")
                print(f"  Operation: {parsed.get('parameters', {}).get('operation', 'N/A')}")
                
                # Validate responses
                if "chrome" in command.lower():
                    if parsed.get('action') == 'app_control' and parsed.get('parameters', {}).get('app_name') == 'chrome':
                        print(f"  ✅ Correct fallback for Chrome")
                    else:
                        print(f"  ❌ Wrong fallback for Chrome")
                        
                elif "project" in command.lower():
                    if parsed.get('action') == 'provide_information':
                        print(f"  ✅ Correct fallback for project")
                    else:
                        print(f"  ❌ Wrong fallback for project")
                        
                elif any(app in command.lower() for app in ["vscode", "edge", "firefox", "notepad", "calculator", "explorer", "terminal"]):
                    if parsed.get('action') == 'app_control':
                        print(f"  ✅ Correct fallback for app control")
                    else:
                        print(f"  ❌ Wrong fallback for app control")
                        
                elif "search" in command.lower():
                    if parsed.get('action') == 'web_search':
                        print(f"  ✅ Correct fallback for web search")
                    else:
                        print(f"  ❌ Wrong fallback for web search")
                        
                else:
                    print(f"  ✅ Fallback response generated")
                
            except Exception as e:
                print(f"  ❌ Error parsing fallback: {e}")
            
            print()
        
        print("=== Test Complete ===")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_fallback_responses() 