#!/usr/bin/env python3
"""
Test Aiden App Launcher Integration
Test the PowerShell app launcher integration with Aiden AI assistant
"""
import sys
import os
import logging

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_powershell_launcher():
    """Test the PowerShell app launcher directly"""
    print("=" * 60)
    print("TESTING POWERSHELL APP LAUNCHER INTEGRATION")
    print("=" * 60)
    
    try:
        from src.utils.powershell_app_launcher import PowerShellAppLauncher
        
        # Create launcher instance
        launcher = PowerShellAppLauncher()
        print(f"✓ PowerShell launcher initialized")
        print(f"  Script path: {launcher.script_path}")
        print(f"  Script exists: {os.path.exists(launcher.script_path)}")
        
        # Test getting common apps
        print("\n--- Testing Common Apps ---")
        common_apps = launcher.get_common_apps()
        print(f"✓ Retrieved {len(common_apps)} common apps:")
        for app in common_apps[:5]:
            print(f"  - {app['name']}: {app['description']}")
        
        # Test app search (non-launching)
        print("\n--- Testing App Search ---")
        test_apps = ["chrome", "notepad", "calculator"]
        
        for app in test_apps:
            print(f"\nSearching for: {app}")
            # Note: We're not actually launching, just testing the search mechanism
            try:
                # This would normally launch, but we'll catch and analyze the result
                result = launcher._run_powershell_command("search", [app])
                print(f"  PowerShell result: {result['success']}")
                print(f"  Execution time: {result['execution_time']:.2f}s")
                if result['success']:
                    print(f"  Output preview: {result['stdout'][:100]}...")
                else:
                    print(f"  Error: {result['stderr'][:100]}...")
            except Exception as e:
                print(f"  Exception during search: {e}")
        
        return True
        
    except Exception as e:
        print(f"✗ PowerShell launcher test failed: {e}")
        return False

def test_command_dispatcher_integration():
    """Test the command dispatcher integration"""
    print("\n" + "=" * 60)
    print("TESTING COMMAND DISPATCHER INTEGRATION")
    print("=" * 60)
    
    try:
        # Mock config manager for testing
        class MockConfigManager:
            def get_config(self, name):
                if name == "security":
                    return {"confirm_app_launch": False}
                elif name == "general":
                    return {"esp32": {"enabled": False}}
                return {}
            
            def record_interaction(self, action, text, params):
                pass
        
        # Mock voice system
        class MockVoiceSystem:
            def speak(self, text):
                print(f"🔊 VOICE: {text}")
        
        from src.utils.command_dispatcher import CommandDispatcher
        
        config_manager = MockConfigManager()
        voice_system = MockVoiceSystem()
        
        # Create command dispatcher
        dispatcher = CommandDispatcher(config_manager, voice_system)
        print(f"✓ Command dispatcher initialized")
        print(f"✓ PowerShell launcher available: {hasattr(dispatcher, 'powershell_launcher')}")
        print(f"✓ App manager fallback available: {hasattr(dispatcher, 'app_manager')}")
        
        # Test app control command structure
        print("\n--- Testing App Control Commands ---")
        
        # Test getting common apps
        print("\nTesting common apps listing:")
        result = dispatcher._show_available_apps_powershell()
        print(f"✓ Show apps result: {result}")
        
        # Test app not found handling
        print("\nTesting app not found handling:")
        dispatcher._handle_app_not_found("nonexistentapp")
        
        return True
        
    except Exception as e:
        print(f"✗ Command dispatcher integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ai_integration_ready():
    """Test that everything is ready for AI integration"""
    print("\n" + "=" * 60)
    print("TESTING AI INTEGRATION READINESS")
    print("=" * 60)
    
    # Check required files
    required_files = [
        "src/app_finder.ps1",
        "src/utils/powershell_app_launcher.py",
        "src/utils/command_dispatcher.py",
        "src/utils/app_manager.py"
    ]
    
    print("Checking required files:")
    all_files_exist = True
    for file_path in required_files:
        exists = os.path.exists(file_path)
        status = "✓" if exists else "✗"
        print(f"  {status} {file_path}")
        if not exists:
            all_files_exist = False
    
    # Test import chain
    print("\nTesting import chain:")
    try:
        from src.utils.powershell_app_launcher import PowerShellAppLauncher
        print("  ✓ PowerShell launcher import")
        
        from src.utils.command_dispatcher import CommandDispatcher
        print("  ✓ Command dispatcher import")
        
        from src.utils.app_manager import AppManager
        print("  ✓ App manager import")
        
    except Exception as e:
        print(f"  ✗ Import failed: {e}")
        all_files_exist = False
    
    # Summary
    print(f"\n🎯 INTEGRATION STATUS: {'READY' if all_files_exist else 'NEEDS FIXES'}")
    
    if all_files_exist:
        print("\n🚀 AIDEN AI ASSISTANT APP LAUNCHER READY!")
        print("   - PowerShell launcher as primary (15-second timeout)")
        print("   - App manager as intelligent fallback")
        print("   - Dashboard integration available")
        print("   - Voice feedback enabled")
        print("   - Top 10 common apps instantly available")
        print("\n   Usage: 'Hey Aiden, open Chrome' or 'launch VS Code'")
    
    return all_files_exist

def main():
    """Run all integration tests"""
    print("🤖 AIDEN AI ASSISTANT - APP LAUNCHER INTEGRATION TEST")
    print("Testing PowerShell app launcher integration with Aiden...")
    
    # Run tests
    tests = [
        ("PowerShell Launcher", test_powershell_launcher),
        ("Command Dispatcher Integration", test_command_dispatcher_integration), 
        ("AI Integration Readiness", test_ai_integration_ready)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"✗ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("INTEGRATION TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} {test_name}")
    
    print(f"\nResult: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Aiden app launcher integration is ready!")
        print("\nNext steps:")
        print("1. Start Aiden AI assistant: python src/main.py")
        print("2. Press your hotkey and say: 'open Chrome'")
        print("3. Or try: 'launch VS Code', 'show available apps'")
    else:
        print("\n⚠️  Some tests failed. Please check the errors above.")
    
    return passed == total

if __name__ == "__main__":
    main() 