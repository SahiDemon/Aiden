#!/usr/bin/env python3
"""
Simple demo of Aiden's new app management features
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

print("🚀 AIDEN AI - INTELLIGENT APP MANAGEMENT DEMO 🚀")
print("=" * 50)

try:
    from utils.config_manager import ConfigManager
    from utils.app_manager import AppManager
    from utils.command_dispatcher import CommandDispatcher
    from utils.voice_system import VoiceSystem
    
    # Initialize
    config_manager = ConfigManager()
    app_manager = AppManager(config_manager)
    
    print("\n📱 DISCOVERING YOUR APPS...")
    apps = app_manager.get_installed_apps()
    print(f"✅ Found {len(apps)} installed applications!")
    
    print("\n🔍 TESTING INTELLIGENT SEARCH...")
    test_searches = ["chrome", "vscode", "discord", "chrom"]  # Last one is a typo
    
    for search in test_searches:
        results = app_manager.search_apps(search, limit=1)
        if results:
            print(f"✅ '{search}' → {results[0]['name']}")
        else:
            print(f"❌ '{search}' → Not found")
    
    print("\n📂 APP CATEGORIES...")
    categories = app_manager.get_app_categories()
    for cat, cat_apps in categories.items():
        if cat_apps:
            print(f"✅ {cat}: {len(cat_apps)} apps")
    
    print("\n🎤 VOICE COMMAND EXAMPLES...")
    print("You can now say:")
    print("• 'Open Chrome' - Launches your browser")
    print("• 'Start Discord' - Opens Discord")
    print("• 'Show available apps' - Lists all apps")
    print("• 'Launch calculator' - Opens calculator")
    
    print("\n🎉 INTEGRATION COMPLETE!")
    print("Aiden can now intelligently find and launch any of your")
    print(f"{len(apps)} installed applications using voice commands!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc() 