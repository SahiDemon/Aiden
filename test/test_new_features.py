#!/usr/bin/env python3
"""
Test script for new Aiden features:
- Smart action cards
- App listing and launching
- Project management
- Website detection and opening
- Conversational AI fallback
"""

import sys
import os
import logging

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from utils.config_manager import ConfigManager
from utils.voice_system import VoiceSystem
from utils.command_dispatcher import CommandDispatcher
from utils.llm_connector import LLMConnector

def test_app_listing():
    """Test app listing functionality"""
    print("=== Testing App Listing ===")
    
    config_manager = ConfigManager()
    voice_system = VoiceSystem(config_manager)
    dispatcher = CommandDispatcher(config_manager, voice_system)
    
    # Test showing available apps
    parameters = {"app_name": "", "operation": "launch", "original_query": "open app"}
    result = dispatcher._handle_app_control(parameters)
    print(f"App listing result: {result}")
    
    # Test specific app request
    parameters = {"app_name": "chrome", "operation": "launch", "original_query": "open chrome"}
    result = dispatcher._handle_app_control(parameters)
    print(f"Chrome launch result: {result}")

def test_website_detection():
    """Test website detection and opening"""
    print("\n=== Testing Website Detection ===")
    
    config_manager = ConfigManager()
    voice_system = VoiceSystem(config_manager)
    dispatcher = CommandDispatcher(config_manager, voice_system)
    
    # Test YouTube request
    parameters = {"app_name": "youtube", "operation": "launch", "original_query": "open youtube"}
    result = dispatcher._handle_app_control(parameters)
    print(f"YouTube opening result: {result}")

def test_project_management():
    """Test project listing and creation"""
    print("\n=== Testing Project Management ===")
    
    config_manager = ConfigManager()
    voice_system = VoiceSystem(config_manager)
    dispatcher = CommandDispatcher(config_manager, voice_system)
    
    # Test project listing
    parameters = {"app_name": "project", "operation": "launch", "original_query": "show my projects"}
    result = dispatcher._handle_app_control(parameters)
    print(f"Project listing result: {result}")

def test_conversational_ai():
    """Test conversational AI capabilities"""
    print("\n=== Testing Conversational AI ===")
    
    config_manager = ConfigManager()
    llm_connector = LLMConnector(config_manager)
    
    # Test general conversation
    conversational_queries = [
        "How are you doing today?",
        "What do you think about coding?",
        "Can you help me learn Python?",
        "Tell me something interesting"
    ]
    
    for query in conversational_queries:
        print(f"\nQuery: {query}")
        try:
            result = llm_connector.process_command(query)
            print(f"Action: {result['action']}")
            print(f"Response: {result['response']}")
            print(f"Parameters: {result['parameters']}")
        except Exception as e:
            print(f"Error: {e}")

def test_system_app_detection():
    """Test system app detection"""
    print("\n=== Testing System App Detection ===")
    
    config_manager = ConfigManager()
    voice_system = VoiceSystem(config_manager)
    dispatcher = CommandDispatcher(config_manager, voice_system)
    
    # Get available apps
    apps = dispatcher._get_system_apps()
    print(f"Found {len(apps)} available apps:")
    for app in apps[:5]:  # Show first 5
        print(f"  - {app['name']} ({app['path']})")

def main():
    """Run all tests"""
    print("Testing Aiden New Features")
    print("=" * 50)
    
    try:
        test_system_app_detection()
        test_app_listing()
        test_website_detection()
        test_project_management()
        test_conversational_ai()
        
        print("\n" + "=" * 50)
        print("All tests completed!")
        
    except Exception as e:
        print(f"Test error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 