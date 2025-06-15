#!/usr/bin/env python3
"""
Simple test for App Manager integration
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from utils.app_manager import AppManager
    from utils.config_manager import ConfigManager
    
    print("🚀 Testing App Manager Integration...")
    
    # Initialize
    config_manager = ConfigManager()
    app_manager = AppManager(config_manager)
    
    # Test getting apps
    print("Getting installed applications...")
    apps = app_manager.get_installed_apps()
    print(f"✅ Found {len(apps)} installed applications")
    
    # Test search
    print("\nTesting search for 'chrome'...")
    results = app_manager.search_apps("chrome", limit=3)
    if results:
        print(f"✅ Found: {results[0]['name']}")
    else:
        print("❌ Chrome not found")
    
    # Test categories
    print("\nTesting categories...")
    categories = app_manager.get_app_categories()
    for cat, cat_apps in categories.items():
        if cat_apps:
            print(f"✅ {cat}: {len(cat_apps)} apps")
    
    print("\n🎉 App Manager integration test completed successfully!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc() 