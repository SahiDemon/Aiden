#!/usr/bin/env python3
"""
Test script for Aiden Dashboard API
Tests the backend API endpoints to verify functionality
"""
import requests
import json
import time
from datetime import datetime

def test_api():
    """Test the dashboard API endpoints"""
    base_url = "http://localhost:5000"
    
    print("🧪 Testing Aiden Dashboard API")
    print("=" * 40)
    
    # Test 1: System Status
    print("\n1️⃣ Testing system status...")
    try:
        response = requests.get(f"{base_url}/api/status", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Status: {data.get('status', 'unknown')}")
            print(f"📊 Components: {len(data.get('components', {}))}")
        else:
            print(f"❌ Status check failed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection failed: {e}")
        print("💡 Make sure the dashboard backend is running!")
        return False
    
    # Test 2: Configuration
    print("\n2️⃣ Testing configuration...")
    try:
        response = requests.get(f"{base_url}/api/config", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ Configuration loaded successfully")
                print(f"🎤 Voice engine: {data['config']['voice']['tts_engine']}")
                print(f"👤 User: {data['user_profile']['personal']['name']}")
            else:
                print(f"❌ Config error: {data.get('error', 'Unknown')}")
        else:
            print(f"❌ Config request failed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Config test failed: {e}")
    
    # Test 3: ESP32 Status
    print("\n3️⃣ Testing ESP32 status...")
    try:
        response = requests.get(f"{base_url}/api/esp32/status", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ ESP32 connected: {data.get('connected', False)}")
            print(f"🌐 IP Address: {data.get('ip_address', 'Unknown')}")
        else:
            print(f"❌ ESP32 status failed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ ESP32 test failed: {e}")
    
    # Test 4: Send a test message
    print("\n4️⃣ Testing message sending...")
    try:
        test_message = {"message": "Hello Aiden, this is a test from the API"}
        response = requests.post(
            f"{base_url}/api/conversation/send",
            json=test_message,
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ Test message sent successfully")
                print("🎯 Check your terminal for Aiden's response")
            else:
                print(f"❌ Message failed: {data.get('error', 'Unknown')}")
        else:
            print(f"❌ Message request failed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Message test failed: {e}")
    
    # Test 5: Conversation History
    print("\n5️⃣ Testing conversation history...")
    try:
        response = requests.get(f"{base_url}/api/conversation/history", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                history_count = len(data.get('history', []))
                current_count = len(data.get('current_conversation', []))
                print(f"✅ History loaded: {history_count} total interactions")
                print(f"💬 Current conversation: {current_count} messages")
            else:
                print(f"❌ History error: {data.get('error', 'Unknown')}")
        else:
            print(f"❌ History request failed: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ History test failed: {e}")
    
    print("\n" + "=" * 40)
    print("🎉 API testing complete!")
    print("\n💡 Next steps:")
    print("   • Install Node.js to enable the web dashboard")
    print("   • Or use the API directly for custom integrations")
    print("   • The backend is working and ready for connections!")
    
    return True

def main():
    """Main test function"""
    print("🚀 Starting Aiden Dashboard API Test")
    print("📋 This will test the backend API without requiring the frontend")
    print("⏰ Make sure you've started the dashboard with: python start_dashboard.py --backend-only")
    
    input("\n📍 Press Enter when the dashboard backend is running...")
    
    success = test_api()
    
    if success:
        print("\n🎯 Want to test fan control? (y/n): ", end="")
        choice = input().lower().strip()
        
        if choice in ['y', 'yes']:
            print("\n🌀 Testing ESP32 fan control...")
            try:
                # Test fan on
                response = requests.post(
                    "http://localhost:5000/api/esp32/control",
                    json={"action": "turn_on"},
                    timeout=5
                )
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ Fan control: {data.get('message', 'Success')}")
                else:
                    print(f"❌ Fan control failed: {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"❌ Fan test failed: {e}")

if __name__ == '__main__':
    main() 