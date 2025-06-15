# Smart ESP32 Fan Control for Aiden

This document describes the intelligent fan control system that leverages the ESP32's `/status` endpoint to provide smart, context-aware fan control.

## 🧠 Intelligence Features

### Smart Status Detection
The system now reads the ESP32's current status via the `/status` endpoint and intelligently parses the response to understand:
- **Fan State**: On, Off, or Unknown
- **Current Speed**: 1 (Low), 2 (Medium), 3 (High), or Mode Changed
- **Device Status**: Just started, last command executed, etc.

### Intelligent Speed Cycling
The ESP32 `/on` endpoint handles speed cycling automatically:
1. **Built-in intelligence** - ESP32 increments speed based on current state
2. **Automatic progression**: Off → Speed 1 → Speed 2 → Speed 3 → Speed 1
3. **Simplified control** - Single `/on` command for all speed cycling
4. **Status awareness** - System still reads status for user feedback

## 📡 ESP32 Endpoints Used

Based on your ESP32 code, the system utilizes:
- `GET /status` - Returns current fan status string
- `GET /on` - Turn on fan at speed 1
- `GET /speed2` - Set fan to speed 2
- `GET /speed3` - Set fan to speed 3
- `GET /mode` - Change fan mode
- `GET /off` - Turn off fan

## 🎯 Smart Features Implemented

### 1. Status Parsing
```python
# Example ESP32 status responses:
"Last command: ON / Speed 1"      → State: on, Speed: 1
"Last command: Speed 2"           → State: on, Speed: 2
"Last command: Speed 3"           → State: on, Speed: 3
"Last command: Power Off"         → State: off, Speed: 0
"Device just started..."          → State: unknown, Speed: unknown
```

### 2. Intelligent Cycling
```python
def cycle_speed(self):
    # The ESP32 /on endpoint handles speed incrementing automatically:
    # Off → Speed 1, Speed 1 → Speed 2, Speed 2 → Speed 3, Speed 3 → Speed 1
    return self.turn_on()  # Uses /on endpoint for smart cycling
```

### 3. Enhanced Voice Commands
The system now supports more natural commands:
- **"What's the fan status?"** → Returns detailed current state
- **"Cycle the fan speed"** → Intelligently moves to next speed
- **"Set fan to high speed"** → Directly sets to speed 3
- **"Check fan state"** → Gets human-readable status

### 4. Dashboard Integration
New API endpoints:
- `GET /api/esp32/smart-status` - Detailed status with parsing
- `POST /api/esp32/control` with `cycle_speed` action
- `POST /api/esp32/control` with `set_speed` action and speed parameter

## 🛠️ Implementation Details

### Enhanced ESP32Controller Methods

#### `get_status()` → Dict
```python
{
    'success': True,
    'raw_status': 'Last command: Speed 2',
    'parsed': {
        'state': 'on',
        'speed': '2',
        'message': 'Fan on speed 2'
    }
}
```

#### `get_human_readable_status()` → str
Returns user-friendly status messages:
- "Fan is ON at speed 2. Fan on speed 2"
- "Fan is currently OFF. Fan is off"
- "Unable to connect to fan (IP: 192.168.1.180). Error: Connection timeout"

#### `cycle_speed()` → bool
Uses the `/on` endpoint for automatic speed cycling (ESP32 handles the logic).

#### `set_speed(speed: int)` → bool
Sets specific speed (1, 2, or 3) using appropriate endpoints.

### Enhanced Command Dispatcher

The `_handle_fan_control()` method now:
1. **Handles status requests** with smart reporting
2. **Uses `/on` endpoint** for speed cycling (ESP32 handles logic)
3. **Supports specific speed setting** with `/speed2` and `/speed3` endpoints
4. **Provides better error handling** and logging

## 🧪 Testing

Run the comprehensive test:
```bash
python test_smart_fan_control.py
```

This test demonstrates:
- ✅ Smart status parsing
- ✅ Intelligent speed cycling
- ✅ Specific speed control
- ✅ Human-readable status
- ✅ Dashboard API integration
- ✅ Error handling and fallbacks

## 📱 Dashboard Features

The dashboard now shows:
- **Real-time fan status** with current speed
- **Smart control buttons** for cycling and specific speeds
- **Detailed diagnostics** including parsed status information
- **Visual indicators** for fan state and connectivity

## 🎮 Voice Control Examples

### Smart Status Checking
- **User**: "What's the fan status?"
- **Aiden**: "Fan is ON at speed 2. Fan on speed 2"

### Intelligent Speed Control
- **User**: "Cycle the fan speed"
- **Aiden**: Checks current speed (2) → Sets to speed 3
- **Result**: Fan intelligently increases to next speed

### Direct Speed Control  
- **User**: "Set fan to high speed"
- **Aiden**: Sets fan directly to speed 3 (high)

## 🔧 Configuration

Ensure your `config.json` has the ESP32 settings:
```json
{
  "general": {
    "esp32": {
      "ip_address": "192.168.1.180",
      "enabled": true
    }
  }
}
```

## 🚀 Benefits

1. **Context Awareness**: Commands now consider current fan state
2. **Smoother Control**: No more redundant commands or unexpected behavior
3. **Better User Experience**: Clear status feedback and predictable cycling
4. **Robust Error Handling**: Graceful fallbacks when status checking fails
5. **Dashboard Integration**: Visual feedback and control options
6. **Voice Command Enhancement**: More natural and intelligent responses

## 🔮 Future Enhancements

Potential improvements:
- **Temperature-based automation**: Adjust speed based on sensor data
- **Scheduling**: Automatic fan control based on time of day
- **Energy monitoring**: Track fan usage and power consumption
- **Multiple fan support**: Control different fans in different rooms
- **Advanced status**: More detailed ESP32 sensor integration

Your fan control system is now intelligent and context-aware! 🎉 