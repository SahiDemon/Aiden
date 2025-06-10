#!/usr/bin/env python3
"""
Simple test to verify our fixes work
"""
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.abspath('.'))

def test_simple_fallback():
    """Test that our fallback logic works correctly"""
    print("=== Testing Simple Fallback Logic ===\n")
    
    try:
        from src.utils.config_manager import ConfigManager
        from src.utils.llm_connector import LLMConnector
        
        # Initialize components
        config_manager = ConfigManager()
        llm_connector = LLMConnector(config_manager)
        
        # Test commands
        test_commands = [
            "open chrome",
            "stop",
            "stop it", 
            "no thank you"
        ]
        
        for command in test_commands:
            print(f"Testing: '{command}'")
            
            # Set the command
            llm_connector.last_command = command
            
            # Test the fallback response (simulate empty tgpt response)
            fallback_response = llm_connector._clean_tgpt_output("")
            print(f"  Response: {fallback_response[:100]}...")
            
            # Parse the response
            parsed = llm_connector._parse_llm_response(fallback_response)
            print(f"  Action: {parsed.get('action', 'unknown')}")
            
            # Check specific commands
            if "chrome" in command.lower():
                expected_action = "app_control"
                if parsed.get('action') == expected_action:
                    print(f"  ✅ FIXED: Chrome correctly recognized as {expected_action}")
                else:
                    print(f"  ❌ STILL BROKEN: Chrome is {parsed.get('action')}, expected {expected_action}")
                    
            elif command.lower() in ["stop", "stop it"]:
                # Stop commands should now be handled gracefully
                if parsed.get('action') == 'provide_information':
                    print(f"  ✅ FIXED: Stop command handled gracefully")
                else:
                    print(f"  ❌ STILL BROKEN: Stop command is {parsed.get('action')}")
                    
            elif "no thank you" in command.lower():
                # Polite responses should be handled
                if parsed.get('action') == 'provide_information':
                    print(f"  ✅ FIXED: Polite response handled")
                else:
                    print(f"  ❌ STILL BROKEN: Polite response is {parsed.get('action')}")
            
            print()
        
        print("=== Test Complete ===")
        print("If you see ✅ FIXED messages, the issues are resolved!")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_simple_fallback() 