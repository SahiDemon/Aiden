# 🤖 Aiden AI Dashboard

A modern, voice-first web interface for the Aiden AI assistant with dark theme and professional design.

## ✨ Features

### 🎤 Voice-First Interface
- **Real-time voice interaction** with animated visualizers
- **Hotkey activation** using the `*` key (unchanged from original)
- **Natural conversation flow** with follow-up questions
- **Visual feedback** for listening and speaking states

### 💬 Chat Interface
- **ChatGPT-style conversation view** with message bubbles
- **Voice and text input support** seamlessly integrated
- **Message history** with timestamps and interaction types
- **Typing indicators** and real-time updates

### 🌀 ESP32 Fan Control
- **Dedicated fan control section** separate from chat
- **One-click controls** for turn on/off and mode changes
- **Connection status monitoring** with visual indicators
- **Real-time feedback** for all fan operations

### ⚙️ Configuration Management
- **Live settings editor** accessible through the dashboard
- **Voice configuration** (TTS engine, voice selection, speed, volume)
- **Speech recognition settings** (engine, timeout, thresholds)
- **AI behavior customization** (system prompt, personality)
- **User profile management** (name, preferences, interaction history)

### 🎨 Modern UI/UX
- **Dark theme** with professional blue/orange accents
- **Responsive design** works on desktop and mobile
- **Smooth animations** using Framer Motion
- **Material-UI components** for consistency
- **Real-time status indicators** and connection monitoring

## 🚀 Quick Start

### Prerequisites
- Python 3.8+ with all Aiden dependencies installed
- Node.js 16+ and npm (for React frontend)
- Your existing Aiden configuration

### Installation

1. **Install additional Python dependencies:**
```bash
pip install -r requirements.txt
```

2. **Launch the dashboard:**
```bash
python start_dashboard.py
```

This will:
- Install npm dependencies automatically
- Build the React frontend
- Start both the dashboard backend and main Aiden system
- Open the web interface at `http://localhost:5000`

### Options

```bash
# Dashboard only (no main Aiden system)
python start_dashboard.py --dashboard-only

# Skip frontend build (if already built)
python start_dashboard.py --skip-build

# Custom port
python start_dashboard.py --port 8080
```

## 🚀 Fast Startup Options

If you've already built the React dashboard before, you can skip the rebuild process for much faster startup:

### Option 1: Automatic Fast Mode
```bash
python start_dashboard.py --fast
```
This will automatically use your existing build if available, or build if needed.

### Option 2: Skip Build Entirely
```bash
python start_dashboard.py --skip-build
```
This completely skips the build step (requires an existing build).

### Option 3: Development Mode
```bash
python start_dashboard.py --dev
```
Perfect for developers - enables fast startup, debug mode, and runs on port 5000.

### Option 4: Quick Shortcuts
For even easier access, use the provided scripts:

**Fast Startup:**
- Windows: `start_fast.bat`
- Linux/Mac: `./start_fast.sh`

**Development Mode:**
- Windows: `start_dev.bat`
- Linux/Mac: `./start_dev.sh`

### Build Time Comparison
- **Normal startup**: ~30-60 seconds (includes npm build)
- **Fast startup**: ~5-10 seconds (skips rebuild)
- **Skip build**: ~3-5 seconds (no build check)

### When to Use Each Option
- **Normal mode**: First time setup or after code changes
- **Fast mode** (`--fast`): Daily usage when no frontend changes
- **Development mode** (`--dev`): Active development with debug enabled
- **Skip build** (`--skip-build`): When you're certain build is current
- **Backend only** (`--backend-only`): Testing API without frontend

## 🎯 Usage

### Voice Interaction
1. **Hotkey Method**: Press `*` key anywhere (original method still works)
2. **Dashboard Method**: Click the microphone button in the header
3. **Speak naturally**: "Hey, open Chrome" or "Turn on the fan"
4. **Follow-up**: Aiden will ask if you need anything else

### Text Interaction
1. Type messages in the chat input field
2. Press Enter to send
3. All text commands work the same as voice commands

### Fan Control
1. Check connection status in the Fan Control panel
2. Use dedicated buttons for fan operations
3. Voice commands also work: "Turn on the fan", "Change fan mode"

### Settings
1. Click the gear icon in the header
2. Modify any configuration in real-time
3. Changes take effect immediately
4. All settings are saved to your config files

## 📱 Mobile Support

The dashboard is fully responsive and works great on mobile devices:
- Access via `http://YOUR_IP:5000` from any device on your network
- Touch-friendly controls
- Optimized layouts for smaller screens

## 🔧 Technical Details

### Architecture
- **Backend**: Flask + SocketIO for real-time communication
- **Frontend**: React + Material-UI + Framer Motion
- **Integration**: Seamless connection to existing Aiden components

### File Structure
```
dashboard/
├── public/          # Static assets
├── src/
│   ├── components/  # React components
│   │   ├── VoiceChat.js       # Main chat interface
│   │   ├── FanControl.js      # ESP32 fan controls
│   │   ├── SystemStatus.js    # Status monitoring
│   │   ├── ConfigPanel.js     # Settings management
│   │   └── VoiceVisualizer.js # Audio visualization
│   ├── App.js       # Main app component
│   └── index.js     # Entry point
src/
└── dashboard_backend.py  # Flask backend API
```

### API Endpoints
- `GET /api/status` - System status
- `GET /api/config` - Current configuration
- `POST /api/config` - Update configuration
- `GET /api/conversation/history` - Chat history
- `POST /api/conversation/send` - Send text message
- `POST /api/voice/start-listening` - Start voice mode
- `GET /api/esp32/status` - ESP32 connection status
- `POST /api/esp32/control` - Control fan

### WebSocket Events
- `voice_status` - Voice listening state updates
- `new_message` - Real-time chat messages
- `hotkey_activated` - Hotkey press notifications
- `command_executed` - Command completion events
- `esp32_action` - Fan control confirmations

## 🎨 Customization

### Changing the Theme
Edit `dashboard/src/index.js` to modify the Material-UI theme:
```javascript
const darkTheme = createTheme({
  palette: {
    primary: { main: '#4c82f7' },  // Change primary color
    secondary: { main: '#f7c94c' }, // Change secondary color
    // ... other theme options
  }
});
```

### Adding New Features
1. Add backend endpoints in `src/dashboard_backend.py`
2. Create React components in `dashboard/src/components/`
3. Update the main App.js to include new components

## 🐛 Troubleshooting

### Dashboard won't start
1. Check Python dependencies: `pip install -r requirements.txt`
2. Check Node.js installation: `node --version`
3. Try rebuilding: `python start_dashboard.py --skip-build=false`

### Voice not working
1. Check microphone permissions in your browser
2. Verify the original Aiden voice system works
3. Check browser console for errors

### ESP32 fan control not working
1. Verify ESP32 IP address in config
2. Check network connectivity
3. Test direct HTTP requests to ESP32

### Configuration changes not saving
1. Check file permissions in config directory
2. Verify backend has write access
3. Look for error messages in terminal

## 🔮 Future Enhancements

- **Multi-user support** with authentication
- **Plugin system** for extending functionality
- **Voice training** for better recognition
- **Advanced analytics** and usage statistics
- **Mobile app** with native voice processing
- **Integration** with more IoT devices

## 📞 Support

If you encounter issues:
1. Check the terminal output for error messages
2. Enable debug mode: modify `backend.run(debug=True)` in start_dashboard.py
3. Check browser developer console for frontend errors
4. Verify all original Aiden functionality works independently

---

**Enjoy your new modern Aiden AI experience! 🚀** 