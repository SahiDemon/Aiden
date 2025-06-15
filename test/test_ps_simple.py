import subprocess
import os
import time

print("=== TESTING SIMPLE POWERSHELL SEARCH ===")

script_path = os.path.join("src", "app_finder.ps1")

cmd = [
    "powershell",
    "-ExecutionPolicy", "Bypass",
    "-File", script_path,
    "search",
    "discord"
]

print(f"Testing search command: {' '.join(cmd)}")

try:
    start_time = time.time()
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=20,  # Shorter timeout for testing
        encoding='utf-8'
    )
    
    execution_time = time.time() - start_time
    
    print(f"Execution completed in {execution_time:.2f} seconds")
    print(f"Return code: {result.returncode}")
    print(f"STDOUT:\n{result.stdout}")
    print(f"STDERR:\n{result.stderr}")
    
except subprocess.TimeoutExpired as e:
    print(f"Process timed out after {time.time() - start_time:.2f} seconds")
    print("This confirms the PowerShell script hangs when called from Python")
except Exception as e:
    print(f"Error: {e}") 