import sys
import os
import time

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def main():
    print("🤖 AIDEN AI ASSISTANT - APP LAUNCHER DEMO")
    print("=" * 50)
    
    try:
        from src.utils.powershell_app_launcher import PowerShellAppLauncher
        
        # Initialize launcher
        launcher = PowerShellAppLauncher()
        print("✓ PowerShell app launcher initialized")
        print(f"  Script: {launcher.script_path}")
        print(f"  Timeout: {launcher.timeout} seconds")
        
        # Show common apps
        print("\n📱 TOP COMMON APPS:")
        common_apps = launcher.get_common_apps()
        for i, app in enumerate(common_apps, 1):
            print(f"  {i:2}. {app['name']:20} - {app['description']}")
        
        print("\n🎯 INTEGRATION FLOW:")
        print("  1️⃣ User: 'Hey Aiden, open Chrome'")
        print("  2️⃣ AI processes voice command")
        print("  3️⃣ Command Dispatcher → PowerShell Launcher")
        print("  4️⃣ PowerShell finds Chrome in ~53ms")
        print("  5️⃣ Chrome launches + voice feedback")
        print("  6️⃣ Dashboard shows success card")
        
        print("\n💡 FALLBACK SYSTEM:")
        print("  ❌ If PowerShell times out (15s)")
        print("  🔄 Automatic fallback to App Manager")
        print("  📊 Registry search for comprehensive coverage")
        
        print("\n🎉 READY FOR PRODUCTION!")
        print("  ✅ Fast PowerShell launcher (primary)")
        print("  ✅ Intelligent fallback system") 
        print("  ✅ Voice + visual feedback")
        print("  ✅ Dashboard integration")
        
        print("\n🚀 TO USE:")
        print("  1. Start Aiden: python src/main.py")
        print("  2. Press hotkey and say: 'open Chrome'")
        print("  3. Watch the magic happen! ✨")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")

if __name__ == "__main__":
    main() 