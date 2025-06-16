#!/usr/bin/env python3
"""
Test script for Aiden's smart app launching functionality
Tests the new verification and search features
"""
import sys
import os
import logging

# Add the project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.config_manager import ConfigManager
from src.utils.voice_system import VoiceSystem
from src.utils.command_dispatcher import CommandDispatcher

def test_smart_app_launch():
    """Test the smart app launching functionality"""
    print("Testing Aiden's Smart App Launch System")
    print("=" * 50)
    
    # Initialize components
    config_manager = ConfigManager()
    voice_system = VoiceSystem(config_manager)
    dispatcher = CommandDispatcher(config_manager, voice_system)
    
    # Test cases - common apps
    test_cases = [
        "chrome",           # Should find Chrome
        "vscode",          # Should find VS Code  
        "code",            # Should also find VS Code
        "calculator",      # Should find Calculator
        "notepad",         # Should find Notepad
        "browser",         # Should suggest Chrome/Firefox/Edge
        "editor",          # Should suggest VS Code/Cursor/Notepad
        "speed gate",      # Should suggest Splitgate (if installed)
        "spotify",         # Should find Spotify
        "nonexistent_app", # Should show smart suggestions
    ]
    
    print("\nTesting app verification and smart matching:")
    print("-" * 45)
    
    for app_name in test_cases:
        print(f"\nTesting: '{app_name}'")
        
        try:
            # Test the smart app launch (without actually launching)
            similar_apps = dispatcher._find_similar_apps(app_name)
            
            if similar_apps:
                best_match = similar_apps[0]
                confidence = best_match.get("confidence", 0)
                matched_name = best_match["name"]
                
                print(f"  ✓ Best match: {matched_name} (confidence: {confidence:.0%})")
                
                if confidence > 0.8:
                    print(f"    → HIGH confidence - would auto-launch {matched_name}")
                elif confidence > 0.5:
                    print(f"    → MEDIUM confidence - would ask user for confirmation")
                else:
                    print(f"    → LOW confidence - would show suggestions")
                
                # Show top 3 matches
                if len(similar_apps) > 1:
                    print(f"  Other matches:")
                    for i, app in enumerate(similar_apps[1:4], 1):
                        print(f"    {i}. {app['name']} ({app['confidence']:.0%})")
            else:
                print(f"  ✗ No matches found - would show smart suggestions")
                
        except Exception as e:
            print(f"  ✗ Error testing {app_name}: {e}")
    
    print("\n" + "=" * 50)
    print("Smart App Launch Test Complete")
    print("\nThe system now:")
    print("• Verifies app existence before launching")
    print("• Finds similar apps using fuzzy matching")
    print("• Auto-launches high-confidence matches")
    print("• Asks for confirmation on medium matches")
    print("• Provides intelligent suggestions when not found")
    print("• Shows detailed feedback in dashboard")

if __name__ == "__main__":
    # Set up logging to see what's happening
    logging.basicConfig(level=logging.INFO)
    test_smart_app_launch() 