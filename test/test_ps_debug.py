import subprocess
import os
import time

print("=== TESTING POWERSHELL EXECUTION ===")

# Test the exact command that Python is running
script_path = os.path.join("src", "app_finder.ps1")
print(f"Script path: {script_path}")
print(f"Script exists: {os.path.exists(script_path)}")

cmd = [
    "powershell",
    "-ExecutionPolicy", "Bypass",
    "-File", script_path,
    "launch",
    "discord"
]

print(f"Command: {' '.join(cmd)}")

try:
    start_time = time.time()
    print("Starting PowerShell process...")
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=40,
        encoding='utf-8',
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    )
    
    execution_time = time.time() - start_time
    
    print(f"Execution completed in {execution_time:.2f} seconds")
    print(f"Return code: {result.returncode}")
    print(f"STDOUT:\n{result.stdout}")
    print(f"STDERR:\n{result.stderr}")
    
except subprocess.TimeoutExpired as e:
    print(f"Process timed out after {time.time() - start_time:.2f} seconds")
    print(f"Error: {e}")
except Exception as e:
    print(f"Error: {e}")

print("\n=== TESTING SIMPLE VERSION ===")
# Test a simpler PowerShell command
try:
    simple_result = subprocess.run(
        ["powershell", "-Command", "Write-Output 'Hello from PowerShell'"],
        capture_output=True,
        text=True,
        timeout=5
    )
    print(f"Simple command result: {simple_result.stdout.strip()}")
except Exception as e:
    print(f"Simple command failed: {e}") 