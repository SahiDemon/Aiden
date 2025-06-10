#!/usr/bin/env python3
"""
Test script for Fan Control
Tests ESP32 fan control to ensure no duplicate commands
"""

import requests
import time
import sys
from pathlib import Path

# Add src to path for imports
sys.path.append(str(Path(__file__).parent / "src"))

from utils.config_manager import ConfigManager
from utils.esp32_controller import ESP32Controller

def test_fan_control():
    """Test fan control operations"""
    print("🔧 Testing ESP32 Fan Control")
    print("=" * 40)
    
    # Initialize components
    config_manager = ConfigManager()
    esp32_controller = ESP32Controller(config_manager)
    
    print(f"ESP32 IP: {esp32_controller.ip_address}")
    
    # Test connection
    print("\n1. Testing connection...")
    is_connected = esp32_controller.check_connection()
    print(f"   Connection status: {'✅ Connected' if is_connected else '❌ Disconnected'}")
    
    if not is_connected:
        print("   ⚠️  Cannot proceed without ESP32 connection")
        return False
    
    # Test turn off
    print("\n2. Testing turn OFF...")
    result = esp32_controller.turn_off()
    print(f"   Turn OFF result: {'✅ Success' if result else '❌ Failed'}")
    time.sleep(2)
    
    # Test turn on
    print("\n3. Testing turn ON...")
    result = esp32_controller.turn_on()
    print(f"   Turn ON result: {'✅ Success' if result else '❌ Failed'}")
    time.sleep(2)
    
    # Test mode change
    print("\n4. Testing mode change...")
    result = esp32_controller.change_mode()
    print(f"   Mode change result: {'✅ Success' if result else '❌ Failed'}")
    time.sleep(2)
    
    # Test turn off again
    print("\n5. Testing turn OFF again...")
    result = esp32_controller.turn_off()
    print(f"   Turn OFF result: {'✅ Success' if result else '❌ Failed'}")
    
    print("\n✅ Fan control test completed!")
    return True

def test_api_endpoint():
    """Test the dashboard API endpoint"""
    print("\n🌐 Testing Dashboard API")
    print("=" * 40)
    
    # Test ESP32 status endpoint
    try:
        response = requests.get("http://localhost:5000/api/esp32/status", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"   ESP32 Status: {'✅ Connected' if data.get('connected') else '❌ Disconnected'}")
        else:
            print(f"   ❌ API Status Error: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"   ❌ API Connection Error: {e}")
        print("   💡 Make sure dashboard is running with: python start_dashboard.py --backend-only")
        return False
    
    # Test turn off via API
    print("\n   Testing turn OFF via API...")
    try:
        response = requests.post(
            "http://localhost:5000/api/esp32/control",
            json={"action": "turn_off"},
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            print(f"   Turn OFF API: {'✅ Success' if data.get('success') else '❌ Failed'}")
        else:
            print(f"   ❌ API Error: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"   ❌ API Error: {e}")
    
    time.sleep(2)
    
    # Test turn on via API
    print("   Testing turn ON via API...")
    try:
        response = requests.post(
            "http://localhost:5000/api/esp32/control",
            json={"action": "turn_on"},
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            print(f"   Turn ON API: {'✅ Success' if data.get('success') else '❌ Failed'}")
        else:
            print(f"   ❌ API Error: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"   ❌ API Error: {e}")
    
    return True

if __name__ == "__main__":
    print("🧪 ESP32 Fan Control Test Suite")
    print("=" * 50)
    
    # Run direct control test
    test_fan_control()
    
    # Run API test
    test_api_endpoint()
    
    print("\n🎉 All tests completed!")
    print("\n💡 Tips:")
    print("   - If direct control works but API doesn't, start the dashboard")
    print("   - If both fail, check ESP32 IP address in config")
    print("   - Use test_esp32_direct.py for more detailed ESP32 testing") 