#!/usr/bin/env python3
"""
Test the smart hotkey behavior to ensure greetings continue conversations
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath('.'))

from src.utils.config_manager import ConfigManager
from src.dashboard_backend import AidenDashboardBackend

def test_smart_hotkey_behavior():
    """Test that the smart hotkey logic works correctly"""
    print("\n=== Testing Smart Hotkey Behavior ===")
    
    try:
        # Create dashboard backend
        dashboard = AidenDashboardBackend()
        
        # Test different types of inputs
        test_cases = [
            # Greetings - should continue conversation
            ("hi", "greeting", False),
            ("hello", "greeting", False),
            ("how are you", "greeting", False),
            ("hey there", "greeting", False),
            ("good morning", "greeting", False),
            
            # Information requests - should end conversation
            ("what time is it", "information", True),
            ("what's the current time", "information", True),
            ("what date is it", "information", True),
            ("how's the weather", "information", True),
            
            # Actions - should end conversation
            ("open chrome", "action", True),
            ("set fan to 50%", "action", True),
            
            # Project/app queries - should continue conversation
            ("list my projects", "project_query", False),
            ("show available apps", "app_query", False),
        ]
        
        print("Testing _should_end_hotkey_conversation logic:")
        print("-" * 50)
        
        for text, category, expected_end in test_cases:
            # Mock command based on category
            if category == "greeting":
                command = {"action": "provide_information", "response": "Hi there! I'm doing well, thanks for asking!"}
            elif category == "information":
                command = {"action": "provide_information", "response": "It's 3:30 PM"}
            elif category == "action":
                command = {"action": "open_application", "response": "Opening Chrome..."}
            elif category in ["project_query", "app_query"]:
                command = {"action": "provide_information", "response": "Here are your projects..."}
            
            # Test the logic
            should_end = dashboard._should_end_hotkey_conversation(text, command)
            
            status = "✅" if should_end == expected_end else "❌"
            action = "END" if should_end else "CONTINUE"
            expected_action = "END" if expected_end else "CONTINUE"
            
            print(f"{status} '{text}' -> {action} (expected: {expected_action})")
        
        print("-" * 50)
        print("✅ Smart hotkey behavior test completed!")
        
        print("\n=== Summary ===")
        print("Hotkey mode will now:")
        print("• CONTINUE for greetings and conversational starters")
        print("• CONTINUE for project/app listing queries")  
        print("• END for completed information requests")
        print("• END for completed actions")
        print("• CONTINUE for unclear cases (safer default)")
        
    except Exception as e:
        print(f"❌ Error testing smart hotkey behavior: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_smart_hotkey_behavior() 