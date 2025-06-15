import sys
import os
sys.path.append('src')

from utils.powershell_app_launcher import PowerShellAppLauncher

print("=== TESTING DISCORD LAUNCH DEBUG ===")

launcher = PowerShellAppLauncher()

# Remove hardcoded paths to force PowerShell usage
launcher.hardcoded_paths = {}

print("Testing PowerShell command for Discord...")
result = launcher._run_powershell_command("launch", ["discord"])

print(f"Return code: {result['return_code']}")
print(f"Success: {result['success']}")
print(f"Execution time: {result['execution_time']}")
print(f"STDOUT:\n{result['stdout']}")
print(f"STDERR:\n{result['stderr']}")

print("\n=== PARSING OUTPUT ===")
app_info = launcher._parse_powershell_output(result['stdout'])
print(f"Parsed app info: {app_info}")

print("\n=== FULL LAUNCH TEST ===")
launch_result = launcher.launch_app("discord")
print(f"Launch result: {launch_result}") 