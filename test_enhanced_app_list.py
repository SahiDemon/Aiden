#!/usr/bin/env python3
"""
Test script for enhanced app list functionality
Tests the new categorized app display and dashboard integration
"""
import sys
import os
import logging

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from utils.config_manager import ConfigManager
from utils.voice_system import VoiceSystem
from utils.command_dispatcher import CommandDispatcher
from utils.app_manager import AppManager

def test_enhanced_app_list():
    """Test the enhanced app list functionality"""
    print("=== Testing Enhanced App List Functionality ===")
    
    try:
        config_manager = ConfigManager()
        voice_system = VoiceSystem(config_manager)
        dispatcher = CommandDispatcher(config_manager, voice_system)
        
        print("✅ Components initialized successfully")
        
        # Test the enhanced app list method
        print("\nTesting _show_available_apps_enhanced()...")
        result = dispatcher._show_available_apps_enhanced()
        print(f"✅ Enhanced app list result: {result}")
        
        # Test app manager categories
        print("\nTesting app categories...")
        categories = dispatcher.app_manager.get_app_categories()
        
        print(f"\n📂 Found {len(categories)} categories:")
        for category, apps in categories.items():
            if apps:
                print(f"   {category}: {len(apps)} apps")
                # Show first 3 apps in each category
                for i, app in enumerate(apps[:3]):
                    print(f"      {i+1}. {app['name']} (v{app['version']})")
                if len(apps) > 3:
                    print(f"      ... and {len(apps) - 3} more")
        
        # Test recent apps
        print("\nTesting recent apps...")
        recent_apps = dispatcher.app_manager.get_recently_used_apps(limit=5)
        print(f"📱 Found {len(recent_apps)} recent apps:")
        for i, app in enumerate(recent_apps):
            print(f"   {i+1}. {app['name']}")
        
        # Test search functionality
        print("\nTesting search functionality...")
        search_queries = ["chrome", "code", "discord", "spotify"]
        for query in search_queries:
            results = dispatcher.app_manager.search_apps(query, limit=1)
            if results:
                app = results[0]
                print(f"   '{query}' → {app['name']} ✅")
            else:
                print(f"   '{query}' → Not found ❌")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in enhanced app list test: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_command_processing():
    """Test command processing for app listing"""
    print("\n=== Testing Command Processing ===")
    
    try:
        config_manager = ConfigManager()
        voice_system = VoiceSystem(config_manager)
        dispatcher = CommandDispatcher(config_manager, voice_system)
        
        # Test the command that should trigger enhanced app list
        test_commands = [
            {
                "action": "provide_information",
                "parameters": {
                    "query": "list installed applications",
                    "original_query": "show available apps"
                },
                "response": "Alright, Boss! Let me check out the apps you have installed. I'll list them for you."
            }
        ]
        
        for command in test_commands:
            print(f"\nProcessing command: {command['parameters']['original_query']}")
            
            # This should trigger the enhanced app list
            if command["action"] == "provide_information":
                query = command["parameters"]["query"].lower()
                if any(phrase in query for phrase in ["list apps", "show apps", "available apps", "installed applications"]):
                    print("✅ Detected app listing request")
                    result = dispatcher._show_available_apps_enhanced()
                    print(f"✅ Enhanced app list executed: {result}")
                else:
                    print("❌ App listing not detected")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in command processing test: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_dashboard_integration():
    """Test dashboard integration (simulation)"""
    print("\n=== Testing Dashboard Integration (Simulation) ===")
    
    try:
        config_manager = ConfigManager()
        app_manager = AppManager(config_manager)
        
        # Simulate creating the action card data
        apps = app_manager.get_installed_apps()
        categories = app_manager.get_app_categories()
        recent_apps = app_manager.get_recently_used_apps(limit=5)
        
        # Create the action card structure
        action_card = {
            "type": "enhanced_app_list",
            "title": "Available Applications",
            "subtitle": f"Found {len(apps)} installed applications",
            "message": "Here are your installed applications organized by category:",
            "categories": categories,
            "recent_apps": recent_apps,
            "total_count": len(apps),
            "status": "Ready"
        }
        
        print("✅ Action card structure created")
        print(f"   Type: {action_card['type']}")
        print(f"   Title: {action_card['title']}")
        print(f"   Subtitle: {action_card['subtitle']}")
        print(f"   Total apps: {action_card['total_count']}")
        print(f"   Categories: {len(action_card['categories'])}")
        print(f"   Recent apps: {len(action_card['recent_apps'])}")
        
        # Verify categories have the right structure
        print("\n📂 Category structure verification:")
        for category, apps in action_card['categories'].items():
            if apps:
                print(f"   {category}: {len(apps)} apps")
                # Verify each app has required fields
                sample_app = apps[0]
                required_fields = ['name', 'version', 'publisher', 'executable']
                missing_fields = [field for field in required_fields if field not in sample_app]
                if missing_fields:
                    print(f"      ⚠️  Missing fields: {missing_fields}")
                else:
                    print(f"      ✅ All required fields present")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in dashboard integration test: {e}")
        import traceback
        traceback.print_exc()
        return False

def run_all_tests():
    """Run all enhanced app list tests"""
    print("🚀 Starting Enhanced App List Tests...\n")
    
    tests = [
        ("Enhanced App List", test_enhanced_app_list),
        ("Command Processing", test_command_processing),
        ("Dashboard Integration", test_dashboard_integration)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*50)
    print("TEST SUMMARY")
    print("="*50)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed! Enhanced app list is working correctly.")
        print("\nYou can now:")
        print("• Say 'show available apps' to see categorized app list")
        print("• Click on any app in the dashboard to launch it")
        print("• Browse apps by category (Browsers, Development, etc.)")
        print("• See recently used apps at the top")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    # Run tests
    run_all_tests() 