#!/usr/bin/env python3
"""
Dependency Fixer for Aiden
Checks and installs missing dependencies, especially PyAudio which is commonly problematic
"""
import subprocess
import sys
import os

def run_command(command, description):
    """Run a command and return success status"""
    print(f"\n{description}...")
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Success: {description}")
            return True
        else:
            print(f"❌ Failed: {description}")
            print(f"Error: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Exception during {description}: {e}")
        return False

def check_import(module_name, package_name=None):
    """Check if a module can be imported"""
    if package_name is None:
        package_name = module_name
    
    try:
        __import__(module_name)
        print(f"✅ {package_name} is available")
        return True
    except ImportError:
        print(f"❌ {package_name} is not available")
        return False

def main():
    print("🔧 Aiden Dependency Fixer")
    print("=" * 40)
    
    # Check Python version
    python_version = sys.version_info
    print(f"Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    if python_version < (3, 8):
        print("❌ Python 3.8 or higher is required")
        return
    
    # Check current dependencies
    print("\n📋 Checking current dependencies...")
    
    dependencies = {
        'speech_recognition': 'SpeechRecognition',
        'pynput': 'pynput',
        'edge_tts': 'edge-tts',
        'pyttsx3': 'pyttsx3',
        'pygame': 'pygame',
        'flask': 'Flask',
        'flask_socketio': 'Flask-SocketIO',
        'requests': 'requests',
        'psutil': 'psutil',
        'PIL': 'Pillow',
        'pystray': 'pystray'
    }
    
    missing_deps = []
    for module, package in dependencies.items():
        if not check_import(module, package):
            missing_deps.append(package)
    
    # Special check for PyAudio (often problematic)
    pyaudio_available = check_import('pyaudio', 'PyAudio')
    if not pyaudio_available:
        missing_deps.append('PyAudio')
    
    if not missing_deps:
        print("\n✅ All dependencies are available!")
    else:
        print(f"\n❌ Missing dependencies: {', '.join(missing_deps)}")
        
        # Try to install missing dependencies
        print("\n🔧 Attempting to install missing dependencies...")
        
        # Update pip first
        run_command(f'"{sys.executable}" -m pip install --upgrade pip', "Updating pip")
        
        # Install regular dependencies
        regular_deps = [dep for dep in missing_deps if dep != 'PyAudio']
        if regular_deps:
            deps_str = ' '.join(regular_deps)
            run_command(f'"{sys.executable}" -m pip install {deps_str}', f"Installing {deps_str}")
        
        # Special handling for PyAudio on Windows
        if 'PyAudio' in missing_deps and sys.platform == "win32":
            print("\n🎤 Installing PyAudio for Windows...")
            
            # Try different methods for PyAudio installation
            methods = [
                (f'"{sys.executable}" -m pip install PyAudio', "Installing PyAudio directly"),
                (f'"{sys.executable}" -m pip install pipwin && "{sys.executable}" -m pipwin install pyaudio', "Installing PyAudio via pipwin"),
                (f'"{sys.executable}" -m pip install --only-binary=all PyAudio', "Installing PyAudio (binary only)"),
            ]
            
            for command, description in methods:
                if run_command(command, description):
                    break
            else:
                print("\n❌ PyAudio installation failed with all methods.")
                print("Manual installation options:")
                print("1. Download PyAudio wheel from: https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio")
                print("2. Install with: pip install downloaded_wheel_file.whl")
                print("3. Or use conda: conda install pyaudio")
        
        elif 'PyAudio' in missing_deps:
            # Non-Windows systems
            if sys.platform == "darwin":  # macOS
                print("\n🎤 For macOS, try: brew install portaudio && pip install PyAudio")
            elif sys.platform.startswith("linux"):  # Linux
                print("\n🎤 For Linux, try: sudo apt-get install portaudio19-dev && pip install PyAudio")
            
            run_command(f'"{sys.executable}" -m pip install PyAudio', "Installing PyAudio")
    
    # Final verification
    print("\n🧪 Final verification...")
    all_good = True
    
    for module, package in dependencies.items():
        if not check_import(module, package):
            all_good = False
    
    if not check_import('pyaudio', 'PyAudio'):
        all_good = False
    
    if all_good:
        print("\n🎉 All dependencies are now properly installed!")
        print("\n✅ You can now run Aiden:")
        print("   python aiden_tray.py")
    else:
        print("\n⚠️  Some dependencies are still missing.")
        print("Please check the error messages above and install them manually.")
    
    print("\n📝 Additional notes:")
    print("- If PyAudio still fails, speech recognition may not work")
    print("- Make sure your microphone permissions are enabled")
    print("- Run as administrator if you encounter permission issues")

if __name__ == "__main__":
    main() 