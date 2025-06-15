import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def main():
    print("AIDEN AI ASSISTANT - APP LAUNCHER INTEGRATION TEST")
    print("=" * 50)
    
    # Check required files
    required_files = [
        "src/app_finder.ps1",
        "src/utils/powershell_app_launcher.py", 
        "src/utils/command_dispatcher.py"
    ]
    
    print("Checking required files:")
    all_good = True
    for file_path in required_files:
        exists = os.path.exists(file_path)
        status = "✓" if exists else "✗"
        print(f"  {status} {file_path}")
        if not exists:
            all_good = False
    
    if not all_good:
        print("\n⚠️ Some required files are missing!")
        return
    
    # Test imports
    print("\nTesting imports:")
    try:
        from src.utils.powershell_app_launcher import PowerShellAppLauncher
        print("  ✓ PowerShell launcher import")
        
        launcher = PowerShellAppLauncher()
        print(f"  ✓ PowerShell launcher initialized")
        print(f"    Script path: {launcher.script_path}")
        
        common_apps = launcher.get_common_apps()
        print(f"  ✓ Retrieved {len(common_apps)} common apps")
        
    except Exception as e:
        print(f"  ✗ PowerShell launcher test failed: {e}")
        return
    
    try:
        from src.utils.command_dispatcher import CommandDispatcher
        print("  ✓ Command dispatcher import")
        
    except Exception as e:
        print(f"  ✗ Command dispatcher import failed: {e}")
        return
    
    print("\n🎉 SUCCESS! Aiden app launcher integration is ready!")
    print("\nHow to use:")
    print("1. Start Aiden: python src/main.py")
    print("2. Press your hotkey and say:")
    print("   - 'open Chrome'")
    print("   - 'launch VS Code'") 
    print("   - 'show available apps'")
    print("\nFeatures:")
    print("- PowerShell launcher (primary, 15-sec timeout)")
    print("- Fallback to app manager if needed")
    print("- Dashboard integration")
    print("- Voice feedback")
    print("- Top 10 common apps")

if __name__ == "__main__":
    main() 