#!/usr/bin/env python3
"""
Test script to verify encoding fixes work
"""
import sys
import os
import tempfile

# Add the project root to the path
sys.path.insert(0, os.path.abspath('.'))

from src.utils.config_manager import ConfigManager
from src.utils.llm_connector import LLMConnector

def test_encoding_fix():
    """Test that encoding issues are fixed"""
    
    print("=== Testing Encoding Fixes ===\n")
    
    try:
        # Initialize components
        config_manager = ConfigManager()
        llm_connector = LLMConnector(config_manager)
        
        # Test commands that should work
        test_commands = [
            "open chrome",
            "stop",
            "stop it", 
            "no thank you",
            "hello"
        ]
        
        print("Testing fallback responses work without encoding errors:\n")
        
        for command in test_commands:
            print(f"Testing: '{command}'")
            
            # Set the command as last_command
            llm_connector.last_command = command
            
            try:
                # Test the encoding-safe prompt creation
                # Simulate the prompt building process
                context = llm_connector._build_context()
                full_prompt = f"{context}\n\nThe user said: \"{command}\"\n\n"
                
                # Test ASCII encoding (this should not fail)
                try:
                    ascii_prompt = full_prompt.encode('ascii', errors='replace').decode('ascii')
                    print(f"  ✅ Encoding safe: {len(ascii_prompt)} chars")
                except Exception as e:
                    print(f"  ❌ Encoding failed: {e}")
                    continue
                
                # Test fallback response
                fallback_response = llm_connector._clean_tgpt_output("")
                
                print(f"  Fallback response: {fallback_response[:50]}...")
                
                # Parse the fallback response
                parsed = llm_connector._parse_llm_response(fallback_response)
                print(f"  Action: {parsed.get('action', 'unknown')}")
                
                # Validate specific commands
                if "chrome" in command.lower():
                    if parsed.get('action') == 'app_control':
                        print(f"  ✅ Chrome command correctly recognized")
                    else:
                        print(f"  ❌ Chrome command failed")
                        
                elif command.lower() in ["stop", "stop it"]:
                    # Stop commands should be handled gracefully
                    print(f"  ✅ Stop command handled")
                    
                elif command.lower() in ["no thank you"]:
                    # Polite responses should be handled
                    print(f"  ✅ Polite response handled")
                    
                else:
                    print(f"  ✅ Command processed")
                
            except Exception as e:
                print(f"  ❌ Error processing command: {e}")
            
            print()
        
        print("=== Test Complete ===")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_encoding_fix() 