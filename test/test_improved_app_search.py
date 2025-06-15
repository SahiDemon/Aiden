#!/usr/bin/env python3
"""
Test script for improved app search and filtering
Tests the fixes for Steam, Calculator, and Postman issues
"""
import sys
import os
import logging

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from utils.app_manager import AppManager

def test_specific_apps():
    """Test the specific apps that were having issues"""
    print("=== Testing Improved App Search and Filtering ===")
    
    # Set up logging to see what's happening
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    try:
        app_manager = AppManager()
        
        # Test cases that were problematic
        test_queries = [
            "steam",
            "calculator", 
            "calc",
            "postman"
        ]
        
        print(f"\n📱 Found {len(app_manager.get_installed_apps())} total installed apps")
        
        for query in test_queries:
            print(f"\n🔍 Searching for: '{query}'")
            results = app_manager.search_apps(query, limit=5)
            
            if results:
                print(f"   Found {len(results)} matches:")
                for i, app in enumerate(results, 1):
                    app_name = app['name']
                    executable = app.get('executable', 'N/A')
                    install_location = app.get('install_location', 'N/A')
                    
                    # Check if this looks like an installer/uninstaller
                    is_unwanted = app_manager._is_unwanted_app_type(app_name)
                    unwanted_flag = " ⚠️ UNWANTED" if is_unwanted else " ✅ OK"
                    
                    print(f"   {i}. {app_name}{unwanted_flag}")
                    print(f"      Executable: {executable}")
                    print(f"      Location: {install_location[:60]}{'...' if len(install_location) > 60 else ''}")
                    
                    # Test if we would launch this app
                    if not is_unwanted:
                        print(f"      🚀 Would launch this app")
                    else:
                        print(f"      🚫 Would skip this app (installer/uninstaller)")
                    print()
            else:
                print(f"   ❌ No matches found for '{query}'")
        
        # Test the filtering improvements
        print("\n=== Testing Filtering Improvements ===")
        all_apps = app_manager.get_installed_apps()
        
        # Count different types
        total_apps = len(all_apps)
        unwanted_apps = [app for app in all_apps if app_manager._is_unwanted_app_type(app['name'])]
        good_apps = [app for app in all_apps if not app_manager._is_unwanted_app_type(app['name'])]
        
        print(f"📊 App Statistics:")
        print(f"   Total apps discovered: {total_apps}")
        print(f"   Unwanted apps filtered: {len(unwanted_apps)}")
        print(f"   Good apps available: {len(good_apps)}")
        
        # Show some examples of filtered apps
        if unwanted_apps:
            print(f"\n🚫 Examples of filtered unwanted apps:")
            for app in unwanted_apps[:5]:
                print(f"   - {app['name']}")
        
        # Show some examples of good apps
        if good_apps:
            print(f"\n✅ Examples of good apps available:")
            for app in good_apps[:10]:
                print(f"   - {app['name']}")
        
        print(f"\n✅ App search improvements test completed!")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_specific_apps() 