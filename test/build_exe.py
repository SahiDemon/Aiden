#!/usr/bin/env python3
"""
Build script to create Aiden executable using PyInstaller
"""
import os
import sys
import shutil

def build_executable():
    """Build the Aiden executable"""
    
    print("=== Building Aiden Executable ===")
    
    # Create icon if it doesn't exist
    create_icon()
    
    # Define the build command
    build_cmd = [
        'pyinstaller',
        'aiden_tray.py',
        '--name=Aiden',
        '--onefile',
        '--windowed',
        '--noconsole',
        '--icon=aiden_icon.ico',
        '--add-data=config;config',
        '--add-data=sounds;sounds',
        '--add-data=dashboard;dashboard',
        '--add-data=src;src',
        '--hidden-import=pystray._win32',
        '--hidden-import=win10toast',
        '--hidden-import=edge_tts',
        '--hidden-import=pygame',
        '--hidden-import=flask',
        '--hidden-import=flask_socketio',
        '--distpath=dist',
        '--workpath=build'
    ]
    
    # Join command for execution
    cmd_str = ' '.join(build_cmd)
    
    print("Building executable...")
    print(f"Command: {cmd_str}")
    
    try:
        result = os.system(cmd_str)
        if result == 0:
            print("\n✅ Build completed successfully!")
            print(f"Executable created: dist/Aiden.exe")
            copy_additional_files()
            return True
        else:
            print(f"❌ Build failed with code: {result}")
            return False
        
    except Exception as e:
        print(f"❌ Build failed: {e}")
        return False

def create_icon():
    """Create a simple icon file"""
    try:
        from PIL import Image, ImageDraw
        
        size = 256
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        margin = 20
        draw.ellipse(
            [margin, margin, size-margin, size-margin], 
            fill=(0, 120, 255, 255),
            outline=(255, 255, 255, 255),
            width=8
        )
        
        text_x = size // 2 - 40
        text_y = size // 2 - 40
        draw.text((text_x, text_y), "AI", fill=(255, 255, 255, 255))
        
        image.save('aiden_icon.ico', format='ICO')
        print("✅ Icon created: aiden_icon.ico")
        
    except Exception as e:
        print(f"⚠️  Could not create icon: {e}")

def copy_additional_files():
    """Copy additional files to dist folder"""
    try:
        dist_dir = 'dist'
        
        folders_to_create = ['temp', 'logs']
        
        for folder in folders_to_create:
            dst = os.path.join(dist_dir, folder)
            os.makedirs(dst, exist_ok=True)
            print(f"✅ Created {dst}")
        
        # Create a batch file to run the exe
        with open('dist/run_aiden.bat', 'w') as f:
            f.write('@echo off\n')
            f.write('echo Starting Aiden AI Assistant...\n')
            f.write('start "" "Aiden.exe"\n')
            f.write('echo Aiden is now running in the system tray!\n')
            f.write('pause\n')
        
        print("✅ Created run_aiden.bat")
        
    except Exception as e:
        print(f"⚠️  Error copying files: {e}")

def main():
    """Main build function"""
    print("Aiden Executable Builder")
    print("========================")
    
    if not os.path.exists('aiden_tray.py'):
        print("❌ Error: aiden_tray.py not found!")
        return
    
    success = build_executable()
    
    if success:
        print("\n🎉 Build completed successfully!")
        print("\nTo run Aiden:")
        print("1. Go to the 'dist' folder")
        print("2. Run 'Aiden.exe' or 'run_aiden.bat'")
        print("3. Look for the Aiden icon in your system tray")
        print("4. Right-click the icon to activate the assistant")
    else:
        print("\n❌ Build failed!")

if __name__ == "__main__":
    main() 