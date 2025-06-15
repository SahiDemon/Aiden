import sys
import os
sys.path.append('src')

from utils.fast_app_finder import FastAppFinder

print("=== TESTING FAST APP FINDER ===")

finder = FastAppFinder()

# Test Discord
print("\n1. Testing Discord search:")
result = finder.find_app("discord")
print(f"Success: {result['success']}")
print(f"Path: {result.get('path', 'N/A')}")
print(f"Method: {result['method']}")
print(f"Time: {result['execution_time']:.3f}s")

# Test Discord launch
print("\n2. Testing Discord launch:")
launch_result = finder.launch_app("discord")
print(f"Launch success: {launch_result['success']}")
print(f"Message: {launch_result['message']}")
print(f"Method: {launch_result['method']}")
print(f"Time: {launch_result['execution_time']:.3f}s")

# Test Chrome
print("\n3. Testing Chrome:")
chrome_result = finder.find_app("chrome")
print(f"Chrome success: {chrome_result['success']}")
print(f"Chrome path: {chrome_result.get('path', 'N/A')}")
print(f"Chrome method: {chrome_result['method']}")
print(f"Chrome time: {chrome_result['execution_time']:.3f}s")

# Test unknown app
print("\n4. Testing unknown app:")
unknown_result = finder.find_app("unknownapp123")
print(f"Unknown success: {unknown_result['success']}")
print(f"Unknown method: {unknown_result['method']}")
print(f"Unknown time: {unknown_result['execution_time']:.3f}s") 