#!/usr/bin/env python3
"""
Test to verify that "open Chrome" correctly ends the conversation in hotkey mode
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath('.'))

from src.dashboard_backend import AidenDashboardBackend

def test_chrome_fix():
    """Test that "open Chrome" now correctly ends the conversation"""
    print("\n=== Testing Chrome Command Fix ===")
    
    try:
        # Create dashboard backend
        dashboard = AidenDashboardBackend()
        
        # Test the specific "open Chrome" case
        text = "open Chrome"
        command = {
            "action": "app_control",
            "parameters": {
                "app_name": "chrome",
                "operation": "launch",
                "original_query": "open Chrome"
            },
            "response": "Opening Chrome for you, Boss."
        }
        
        # Test the logic
        should_end = dashboard._should_end_hotkey_conversation(text, command)
        
        status = "✅" if should_end else "❌"
        action = "END" if should_end else "CONTINUE"
        
        print(f"{status} 'open Chrome' -> {action}")
        
        if should_end:
            print("✅ SUCCESS: Chrome command will now end the conversation!")
        else:
            print("❌ FAILED: Chrome command still continuing conversation")
        
        # Test a few more action types
        test_cases = [
            ("search for python tutorials", "web_search", True),
            ("create a new file", "file_operation", True),
            ("set fan speed to high", "fan_control", True),
            ("hi there", "provide_information", False),  # greeting should continue
        ]
        
        print("\nTesting other action types:")
        print("-" * 40)
        
        for text, action_type, expected_end in test_cases:
            command = {"action": action_type, "response": "test response"}
            should_end = dashboard._should_end_hotkey_conversation(text, command)
            
            status = "✅" if should_end == expected_end else "❌"
            action = "END" if should_end else "CONTINUE"
            expected_action = "END" if expected_end else "CONTINUE"
            
            print(f"{status} '{text}' -> {action} (expected: {expected_action})")
        
    except Exception as e:
        print(f"❌ Error testing chrome fix: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_chrome_fix() 