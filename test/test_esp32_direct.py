#!/usr/bin/env python3
"""
Direct ESP32 Connection Test
Tests ESP32 connectivity without going through the dashboard
"""
import sys
import os

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from src.utils.config_manager import ConfigManager
from src.utils.esp32_controller import ESP32Controller
import requests
import time

def test_esp32_direct():
    """Test ESP32 connectivity directly"""
    print("🌀 Direct ESP32 Fan Test")
    print("=" * 30)
    
    # Initialize the ESP32 controller
    print("📋 Loading configuration...")
    config_manager = ConfigManager()
    esp32_controller = ESP32Controller(config_manager)
    
    ip_address = esp32_controller.ip_address
    print(f"🌐 ESP32 IP Address: {ip_address}")
    
    # Test 1: Basic connectivity
    print("\n1️⃣ Testing basic connectivity...")
    try:
        response = requests.get(f"http://{ip_address}", timeout=3)
        print(f"✅ HTTP Response: {response.status_code}")
        if response.text:
            print(f"📄 Response content: {response.text[:100]}...")
    except requests.exceptions.ConnectTimeout:
        print("❌ Connection timeout - ESP32 might be offline")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Connection error - Check IP address and network")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    # Test 2: Check connection method
    print("\n2️⃣ Testing connection check...")
    is_connected = esp32_controller.check_connection()
    print(f"✅ Connection check result: {is_connected}")
    
    # Test 3: Try fan commands
    print("\n3️⃣ Testing fan commands...")
    
    # Test turn on
    print("🔛 Testing turn on...")
    result = esp32_controller.turn_on()
    print(f"✅ Turn on result: {result}")
    time.sleep(1)
    
    # Test mode change
    print("🔄 Testing mode change...")
    result = esp32_controller.change_mode()
    print(f"✅ Mode change result: {result}")
    time.sleep(1)
    
    # Test turn off
    print("🔴 Testing turn off...")
    result = esp32_controller.turn_off()
    print(f"✅ Turn off result: {result}")
    
    print("\n" + "=" * 30)
    print("🎉 Direct ESP32 test complete!")
    
    print("\n💡 If the commands worked but dashboard shows disconnected:")
    print("   • The ESP32 is working fine")
    print("   • The issue is with the status checking method")
    print("   • You can still control the fan via voice or dashboard buttons")
    
    return True

def main():
    """Main test function"""
    print("🚀 Starting Direct ESP32 Test")
    print("📋 This tests your ESP32 fan directly without the dashboard")
    
    try:
        success = test_esp32_direct()
        if success:
            print("\n🎯 Test completed successfully!")
        else:
            print("\n💔 Test failed - check your ESP32 connection")
    except KeyboardInterrupt:
        print("\n🛑 Test stopped by user")
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main() 