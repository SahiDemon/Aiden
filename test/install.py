#!/usr/bin/env python3
"""
Installation script for Aiden AI Desktop Agent
This script sets up the virtual environment and installs dependencies
"""
import os
import sys
import subprocess
import platform

def print_step(message):
    """Print a step message with formatting"""
    print("\n" + "="*80)
    print(f"  {message}")
    print("="*80)

def run_command(command, shell=True):
    """Run a shell command and print output"""
    print(f"> {command}")
    result = subprocess.run(command, shell=shell, capture_output=True, text=True)
    
    if result.stdout:
        print(result.stdout)
    
    if result.stderr:
        print(f"ERROR: {result.stderr}")
        
    return result.returncode == 0

def main():
    """Main installation function"""
    print_step("Aiden AI Desktop Agent - Installation")
    
    # Detect Python version
    python_version = platform.python_version()
    print(f"Detected Python {python_version}")
    
    if sys.version_info < (3, 9):
        print("ERROR: Python 3.9 or higher is required")
        sys.exit(1)
    
    # Determine virtual environment activation command
    if platform.system() == "Windows":
        venv_activate = ".venv\\Scripts\\activate"
        python_cmd = "python"
    else:
        venv_activate = "source .venv/bin/activate"
        python_cmd = "python3"
    
    # Create virtual environment
    print_step("Creating virtual environment")
    venv_cmd = f"{python_cmd} -m venv .venv"
    if not run_command(venv_cmd):
        print("ERROR: Failed to create virtual environment")
        sys.exit(1)
    
    # Install dependencies
    print_step("Installing dependencies")
    
    if platform.system() == "Windows":
        pip_cmd = f".venv\\Scripts\\pip install -r requirements.txt"
    else:
        pip_cmd = f".venv/bin/pip install -r requirements.txt"
        
    if not run_command(pip_cmd):
        print("ERROR: Failed to install dependencies")
        sys.exit(1)
    
    # Check for tgpt
    print_step("Checking for tgpt")
    tgpt_exists = False
    
    if platform.system() == "Windows":
        tgpt_check = "where tgpt"
    else:
        tgpt_check = "which tgpt"
        
    tgpt_result = subprocess.run(tgpt_check, shell=True, capture_output=True, text=True)
    tgpt_exists = tgpt_result.returncode == 0
    
    if tgpt_exists:
        print("tgpt found in PATH")
    else:
        print("WARNING: tgpt not found in PATH")
        print("Please install tgpt from https://github.com/aandrew-me/tgpt")
        print("and ensure it's available in your PATH before running Aiden")
    
    # Installation complete
    print_step("Installation complete!")
    print("\nTo run Aiden:")
    if platform.system() == "Windows":
        print(f"1. {venv_activate}")
        print("2. python -m src.main")
    else:
        print(f"1. {venv_activate}")
        print("2. python -m src.main")
    
    print("\nPress the * (asterisk) key to activate Aiden and speak your command!")

if __name__ == "__main__":
    main()
