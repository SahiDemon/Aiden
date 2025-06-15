#!/usr/bin/env python3
"""
Improved build script for Aiden executable
"""
import os
import sys
import shutil
import subprocess

def create_icon():
    """Create icon for the executable"""
    try:
        from PIL import Image, ImageDraw
        
        size = 256
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # Create a nice gradient circle
        margin = 20
        draw.ellipse(
            [margin, margin, size-margin, size-margin], 
            fill=(0, 120, 255, 255),
            outline=(255, 255, 255, 255),
            width=8
        )
        
        # Add "AI" text
        text_x = size // 2 - 40
        text_y = size // 2 - 40
        draw.text((text_x, text_y), "AI", fill=(255, 255, 255, 255))
        
        # Save as ICO with multiple sizes
        image.save('aiden_icon.ico', format='ICO', 
                  sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)])
        print("✅ Icon created successfully")
        return True
        
    except Exception as e:
        print(f"⚠️  Could not create icon: {e}")
        return False

def build_executable():
    """Build the executable with PyInstaller"""
    
    print("=== Building Aiden Executable ===")
    
    # Create icon
    create_icon()
    
    # Build command with improved settings
    cmd = [
        'pyinstaller',
        'aiden_tray.py',
        '--name=Aiden',
        '--onefile',
        '--windowed',
        '--noconsole',
        '--icon=aiden_icon.ico',
        
        # Add data files
        '--add-data=config;config',
        '--add-data=sounds;sounds', 
        '--add-data=dashboard;dashboard',
        '--add-data=src;src',
        
        # Hidden imports for dependencies
        '--hidden-import=pystray._win32',
        '--hidden-import=PIL._tkinter_finder',
        '--hidden-import=win10toast',
        '--hidden-import=edge_tts',
        '--hidden-import=pygame',
        '--hidden-import=pyttsx3',
        '--hidden-import=flask',
        '--hidden-import=flask_socketio',
        '--hidden-import=requests',
        '--hidden-import=numpy',
        '--hidden-import=winsound',
        
        # Collect packages that have data files
        '--collect-all=edge_tts',
        '--collect-all=flask',
        '--collect-submodules=pygame',
        
        # Output settings
        '--distpath=dist',
        '--workpath=build',
        '--clean',
        
        # Runtime options
        '--runtime-tmpdir=temp'
    ]
    
    print("Building executable...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ Build completed successfully!")
        print(f"Executable created: dist/Aiden.exe")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed!")
        print(f"Error: {e}")
        if e.stdout:
            print(f"STDOUT: {e.stdout}")
        if e.stderr:
            print(f"STDERR: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def post_build_setup():
    """Setup additional files after build"""
    try:
        print("Setting up post-build files...")
        
        # Create necessary directories in dist
        dist_dirs = ['temp', 'logs', 'sounds', 'config']
        for dir_name in dist_dirs:
            dist_path = os.path.join('dist', dir_name)
            os.makedirs(dist_path, exist_ok=True)
            print(f"✅ Created directory: {dist_path}")
        
        # Copy sound files if they exist
        if os.path.exists('sounds'):
            for file in os.listdir('sounds'):
                if file.endswith('.mp3'):
                    src = os.path.join('sounds', file)
                    dst = os.path.join('dist', 'sounds', file)
                    shutil.copy2(src, dst)
                    print(f"✅ Copied sound: {file}")
        
        # Copy essential config files
        config_files = ['config/config.json', 'config/user_profile.json']
        for config_file in config_files:
            if os.path.exists(config_file):
                dst = os.path.join('dist', config_file)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(config_file, dst)
                print(f"✅ Copied config: {config_file}")
        
        # Create launcher batch file
        batch_content = '''@echo off
title Aiden AI Assistant
echo Starting Aiden AI Assistant...
echo.
echo Look for the Aiden icon in your system tray!
echo Right-click the icon to activate the assistant.
echo.
start "" "Aiden.exe"
echo Aiden is now running in the background.
echo You can close this window.
pause
'''
        
        with open('dist/Start_Aiden.bat', 'w') as f:
            f.write(batch_content)
        
        print("✅ Created Start_Aiden.bat launcher")
        
        # Create a readme file
        readme_content = '''Aiden AI Assistant
==================

Installation:
1. Extract all files to a folder
2. Double-click "Start_Aiden.bat" or "Aiden.exe"
3. Look for the blue "AI" icon in your system tray
4. Right-click the tray icon to access options

Usage:
- Click "Activate Assistant" to start voice interaction
- Click "Open Dashboard" to view the web interface
- Press the * key for quick voice activation
- Say "stop" or "exit" to end conversations

Features:
- Voice-activated AI assistant
- App control and file management
- Web dashboard interface
- ESP32 fan control support
- Conversation memory

Created by Sahindu Gayanuka
'''
        
        with open('dist/README.txt', 'w') as f:
            f.write(readme_content)
        
        print("✅ Created README.txt")
        return True
        
    except Exception as e:
        print(f"⚠️  Post-build setup error: {e}")
        return False

def main():
    """Main build process"""
    print("Aiden AI Assistant - Executable Builder")
    print("=" * 50)
    
    # Check prerequisites
    if not os.path.exists('aiden_tray.py'):
        print("❌ Error: aiden_tray.py not found!")
        print("Make sure you're in the Aiden project directory.")
        return
    
    # Install build dependencies
    print("Installing build dependencies...")
    deps = ['PyInstaller', 'pystray', 'Pillow', 'win10toast']
    for dep in deps:
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', dep], 
                         check=True, capture_output=True)
            print(f"✅ {dep} installed/verified")
        except subprocess.CalledProcessError:
            print(f"⚠️  Could not install {dep}")
    
    # Build the executable
    if build_executable():
        # Post-build setup
        if post_build_setup():
            print("\n🎉 Build completed successfully!")
            print("\nFiles created in 'dist' folder:")
            print("- Aiden.exe (main executable)")
            print("- Start_Aiden.bat (launcher)")
            print("- README.txt (instructions)")
            print("- config/ (configuration files)")
            print("- sounds/ (audio files)")
            print("\nTo run Aiden:")
            print("1. Go to the 'dist' folder")
            print("2. Double-click 'Start_Aiden.bat'")
            print("3. Look for the AI icon in your system tray")
            print("4. Right-click to activate!")
        else:
            print("⚠️  Build completed but post-setup had issues")
    else:
        print("❌ Build failed!")

if __name__ == "__main__":
    main() 