#!/usr/bin/env python3
"""
Quick test for information handler routing
"""
import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))

from utils.config_manager import ConfigManager
from utils.voice_system import VoiceSystem
from utils.command_dispatcher import CommandDispatcher

def test_info_handler():
    print("Testing information handler routing...")
    
    config_manager = ConfigManager()
    voice_system = VoiceSystem(config_manager)
    dispatcher = CommandDispatcher(config_manager, voice_system)
    
    # Test app listing query
    print('\nTesting app listing query...')
    result = dispatcher._handle_information({
        'query': 'list installed applications', 
        'original_query': 'show available apps'
    })
    print(f'App listing result: {result}')
    
    # Test project listing query
    print('\nTesting project listing query...')
    result = dispatcher._handle_information({
        'query': 'list my projects', 
        'original_query': 'show my projects'
    })
    print(f'Project listing result: {result}')
    
    print("\n✅ Information handler test completed!")

if __name__ == "__main__":
    test_info_handler() 