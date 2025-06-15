#!/usr/bin/env python3
"""
Test app commands through the command dispatcher
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from utils.config_manager import ConfigManager
    from utils.voice_system import VoiceSystem
    from utils.command_dispatcher import CommandDispatcher
    
    print("🚀 Testing App Commands through Command Dispatcher...")
    
    # Initialize components
    config_manager = ConfigManager()
    voice_system = VoiceSystem(config_manager)
    dispatcher = CommandDispatcher(config_manager, voice_system)
    
    # Test app search functionality
    print("\n=== Testing App Search ===")
    test_apps = ["chrome", "vscode", "notepad", "calculator", "nonexistent"]
    
    for app_name in test_apps:
        results = dispatcher.app_manager.search_apps(app_name, limit=1)
        if results:
            app = results[0]
            print(f"✅ '{app_name}' → Found: {app['name']} (v{app['version']})")
        else:
            print(f"❌ '{app_name}' → Not found")
    
    # Test command processing (simulation)
    print("\n=== Testing Command Processing ===")
    test_commands = [
        {
            "action": "app_control",
            "parameters": {
                "app_name": "chrome",
                "operation": "launch"
            }
        },
        {
            "action": "app_control", 
            "parameters": {
                "app_name": "calculator",
                "operation": "launch"
            }
        },
        {
            "action": "app_control",
            "parameters": {
                "app_name": "",  # Empty name should show available apps
                "operation": "launch"
            }
        }
    ]
    
    for i, command in enumerate(test_commands):
        app_name = command["parameters"]["app_name"]
        print(f"\nTest {i+1}: Processing app command for '{app_name}'...")
        
        if not app_name:
            print("✅ Empty app name - would show available apps")
        else:
            # Test the intelligent search
            results = dispatcher.app_manager.search_apps(app_name, limit=1)
            if results:
                print(f"✅ Would launch: {results[0]['name']}")
            else:
                print(f"❌ App not found: {app_name}")
    
    # Test categories
    print("\n=== Testing App Categories ===")
    categories = dispatcher.app_manager.get_app_categories()
    total_apps = sum(len(apps) for apps in categories.values())
    
    print(f"Total apps across all categories: {total_apps}")
    for category, apps in categories.items():
        if apps:
            print(f"✅ {category}: {len(apps)} apps")
            # Show first app in each category
            if apps:
                print(f"   Example: {apps[0]['name']}")
    
    print("\n🎉 Command Dispatcher integration test completed successfully!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc() 