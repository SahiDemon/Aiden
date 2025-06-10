# ESP32 Fan Control for Aiden AI Desktop Agent

This document explains how to set up and use the ESP32 fan control feature with Aiden.

## Overview

The ESP32 fan control feature allows you to control a fan connected to an ESP32 microcontroller using voice commands to Aiden. You can turn the fan on/off, change modes, and adjust speed.

## Prerequisites

1. An ESP32 microcontroller with a functioning web server
2. The fan control firmware installed on the ESP32 (as provided in test_esp32.py)
3. The ESP32 connected to the same network as your computer
4. The `requests` Python package installed

## Configuration

1. Ensure your ESP32 is powered on and connected to your network
2. Find the IP address of your ESP32 (check your router or the ESP32 serial output)
3. Update the IP address in the `config.json` file:

```json
"general": {
  "esp32": {
    "ip_address": "192.168.1.6",  // Replace with your ESP32's IP address
    "enabled": true
  }
}
```

## Voice Commands

You can control the fan using the following voice commands:

### Turn On/Off
- "Turn on the fan"
- "Turn off the fan"
- "Start the fan"
- "Stop the fan"

### Change Mode
- "Change the fan mode"
- "Switch the fan mode"
- "Cycle the fan mode"

### Adjust Speed
- "Set the fan to low speed" (or speed 1)
- "Set the fan to medium speed" (or speed 2)
- "Set the fan to high speed" (or speed 3)
- "Speed up the fan"

## Technical Details

The ESP32 fan control uses a simple HTTP API:
- `http://<ESP32_IP>/on` - Turn on the fan
- `http://<ESP32_IP>/off` - Turn off the fan
- `http://<ESP32_IP>/mode` - Change the fan mode

The communication is done via HTTP GET requests using the Python `requests` library.

## Troubleshooting

If you experience issues with the fan control:

1. Check that the ESP32 is powered on and connected to your network
2. Verify the IP address in your config.json file is correct
3. Try accessing the ESP32 from a web browser (e.g., http://192.168.1.6/on)
4. Check the logs for any connection errors
5. Make sure the ESP32 firmware is properly installed and running

## Example Sequence

To test if your fan control is working:

1. Activate Aiden with the hotkey
2. Say "Turn on the fan"
3. Aiden should respond with "I've turned on the fan, Boss"
4. Say "Change the fan mode"
5. Aiden should respond with "I've changed the fan mode, Boss"
6. Say "Turn off the fan"
7. Aiden should respond with "I've turned off the fan, Boss"
