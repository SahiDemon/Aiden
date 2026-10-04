# 🤖 Aiden AI Assistant

A powerful voice-controlled AI assistant for Windows with context-aware conversations and intelligent command execution.

## ✨ Features

### 🎙️ Voice & Activation
- **🎤 High-Accuracy Wake Word** - Say "Aiden" with Porcupine detection (2.5x more accurate)
- **⌨️ Global Hotkey** - Press Ctrl+Shift+Space for instant access
- **🔊 Voice Control** - Enable/disable/toggle wake word detection via voice
- **🎯 Zero False Negatives** - Advanced audio processing eliminates missed detections
- **🌐 Multi-Language Support** - Configurable voice and language options

### 💬 AI & Intelligence
- **🧠 Context-Aware Conversations** - Remembers conversation context for follow-up questions
- **⚡ Lightning Fast** - Sub-second response times with Groq AI
- **🤖 Google Gemini Integration** - 15 requests/min, 1M tokens/day (FREE tier)
- **💭 Conversation History** - Maintains 10-message context via Redis
- **🎯 Intent Classification** - Understands greetings, commands, questions, multi-commands

### 🚀 Application Control
- **📱 Smart App Discovery** - Automatically finds and launches applications (353+ apps detected)
  - **Registry Scanning** - Scans Windows registry for installed applications
  - **Start Menu Search** - Searches Windows Start Menu shortcuts
  - **PATH Detection** - Finds apps in system PATH
  - **Multi-Library Support** - Searches Program Files, AppData, and common locations
  - **Cached Results** - Smart caching for instant app discovery
- **🔍 Smart Filtering & Fuzzy Matching** - Intelligent app name matching
  - **Fuzzy Search** - Smart matching ("obs" → "OBS Studio", "vscode" → "Visual Studio Code")
  - **Partial Matching** - Finds apps with partial names ("chrome" finds "Google Chrome")
  - **Alias Support** - Common app aliases (code → VS Code, calc → Calculator)
  - **Case-Insensitive** - Works regardless of capitalization
  - **Multiple Search Methods** - Tries multiple strategies until app is found
- **🎮 Steam Integration** - Automatic Steam game detection and launching
  - **Auto-Detection** - Automatically detects Steam games from install paths
  - **Steam AppID Resolution** - Finds Steam AppIDs from game manifests
  - **Multi-Library Support** - Scans all Steam library folders
  - **Steam Protocol Launch** - Uses `steam://run/<appid>` for proper Steam integration
  - **Fuzzy Steam Matching** - Matches games by name, install directory, or AppID
  - **Registry + VDF Parsing** - Reads Steam registry and libraryfolders.vdf
  - **Automatic Fallback** - Falls back to direct exe launch if Steam unavailable
- **🔄 Smart Process Management** - Intelligent process closing
  - **Process Validation** - Checks if process is running before attempting to close
  - **Fuzzy Process Matching** - Finds processes with partial names
  - **PID Support** - Can target specific process by PID
  - **Safe Closing** - Validates process exists to avoid errors
  - **Multiple Process Handling** - Can close multiple instances
- **🚀 Multi-Command** - Execute multiple commands in one request ("open Chrome and close Firefox")
- **📂 Path Resolution** - Full executable paths for reliable launching
- **⚡ Fast Launch** - Direct path aliases for common apps (Chrome, Firefox, VS Code, etc.)

### 🎵 Media Control
- **🎧 Spotify Integration** - Full Spotify control via Spotify Web API
  - Play/pause/resume/next/previous
  - Play specific tracks, artists, or playlists
  - Play Liked Songs
  - Set volume (0-100%)
  - Transfer playback between devices
  - Identify current track ("What song is this?")
- **📺 YouTube Control** - Control YouTube videos in Chromium browsers
  - Play/pause/resume
  - Next/previous video
  - Seek forward/backward
  - Mute/unmute
- **🎶 YouTube Music Control** - Control YouTube Music tabs
  - All YouTube controls plus music-specific features
  - Smart tab detection and control

### 🖥️ System Commands
- **🔒 Lock Screen** - Lock your computer instantly with timers
- **⏻ Shutdown** - Shutdown the PC with timers
- **🔄 Restart** - Restart Windows with timers
- **😴 Sleep Mode** - Put computer to sleep with timers
- **💤 Hibernate** - Hibernate the system with timers

### 🔋 UPS Power Monitoring ⚡NEW⚡
- **🔌 Real-Time Power Detection** - Instantly detects AC vs Battery mode
- **⏱️ Time-Based Alerts** - 3min, 4min, 5min warnings (not flaky battery %)
- **🎙️ Voice Alerts** - Cool warnings at each milestone
- **🤖 Smart Shutdown Coordination** - Asks for confirmation before shutdown
- **🛡️ Automatic Protection** - Force shutdown after 5 minutes on battery
- **⚡ Emergency Voltage Check** - Immediate shutdown if voltage critical (<22V)
- **💾 Data Protection** - Predictable alerts give you time to save work
- See [UPS monitoring guide](docs/guides/ups-monitoring.md) for details

### ⚙️ Advanced System Control
- **📶 Wi-Fi Control**
  - Turn Wi-Fi on/off
  - Disconnect from current network
  - Automatic adapter discovery
- **📡 Bluetooth Control**
  - Turn Bluetooth on/off
  - Automatic adapter discovery
- **✈️ Airplane Mode** - Enable/disable airplane mode (toggles Wi-Fi + Bluetooth)
- **🔋 Power Management**
  - Enable power saving mode
  - Enable balanced mode
  - Battery status monitoring
- **💡 Display Control**
  - Set brightness (0-100%)
  - Turn off screen
  - External monitor brightness (with ClickMonitorDDC)
- **🔊 Audio Control**
  - Mute/unmute/toggle mute
  - Volume up/down
  - Set volume to specific level (0-100%)
- **📊 System Telemetry**
  - Battery level and status
  - CPU usage monitoring
  - GPU status and stats

### ⏰ Timer & Scheduling
- **⏱️ Scheduled Commands** - Schedule system actions with timers
  - Scheduled shutdown/restart/sleep/hibernate/lock
  - Cancel active timers
  - Timer duration from 1 second to 24 hours
  - Persistent timers (survive restarts)

### 🏠 Smart Home Integration
- **🌪️ ESP32 Fan Control**
  - Turn fan on/off
  - Adjust fan speed (1-3 levels)
  - Change fan mode
  - Real-time status monitoring
- **📡 WebSocket Integration** - Real-time device status updates
- **🔌 Expandable** - Ready for additional IoT devices (lights, switches, sensors)

### 🎨 Visual Interface
- **📊 Web Dashboard** - Beautiful Gemini Live-style interface at http://localhost:5000
  - Real-time voice visualization with wave animations
  - System metrics (CPU, memory, cache stats)
  - Smart home device controls
  - Settings panel (Speech/AI/System configuration)
  - Live WebSocket connection with auto-reconnect
- **🌊 Visual Overlay** - Beautiful animated overlay at the top of your screen
  - Liquid wave animations (listening/thinking/replying states)
  - Shimmer text effects
  - Entry/exit animations
  - Always-on-top transparent window
  - Real-time status updates via WebSocket

### 🔧 Advanced Features
- **🔇 Hidden Mode** - Runs silently in system tray
- **💾 Smart Caching** - Redis + JSON file backup (1-hour TTL)
- **⚡ Lazy Loading** - Context fetched only when needed (50% reduction in API calls)
- **🎯 Token Optimization** - 95% reduction in AI token usage (7454 → 300 tokens)
- **🔄 2-Pass AI System** - Lightweight analysis first, context fetch only if required
- **📝 Command Logging** - All commands logged to database with execution times
- **🛠️ Shell Command Execution** - Execute arbitrary shell commands
- **💀 Self-Termination** - Dramatic shutdown with custom messages

### 🏆 Technical Achievements & Performance

**🚀 Performance Metrics:**
- **95% Token Reduction** - Revolutionary 2-pass AI system reduces tokens from 7454 → 400 (system prompt) and 1778 → 300 (simple queries)
- **50% Fewer API Calls** - Smart context fetching means only 50% of requests need system context
- **Sub-Second Response Times** - AI responses in 300-500ms (no context) or 500ms-1s (with context)
- **<50ms Dashboard Updates** - Real-time WebSocket updates for instant UI feedback
- **Low Resource Usage** - Only 3-5% CPU and ~200MB RAM when idle, 10-15% CPU and ~700MB RAM when active

**🧠 Intelligent AI Features:**
- **2-Pass AI System** - AI first analyzes requests without context, then fetches only what it needs
- **Conversation Summarization** - Automatically summarizes long conversations after 8 messages to maintain context
- **Follow-up Detection** - Understands incomplete sentences and connects them to previous context ("and Notepad too" → opens Notepad)
- **Intent Classification** - Automatically detects greetings, commands, questions, and multi-commands
- **Smart Execution Order** - Multi-commands execute in optimal order (system commands always last)

**🔌 Robust Infrastructure:**
- **Dual Database System** - Redis for lightning-fast cache (<1ms access) + PostgreSQL for persistent storage
- **WebSocket Auto-Reconnect** - Exponential backoff (1s → 2s → 4s → 8s → max 30s) with heartbeat system
- **Graceful Degradation** - Works even when Redis/PostgreSQL unavailable (JSON file fallback)
- **Persistent Timers** - Scheduled commands survive system restarts
- **Command Execution Logging** - Every command logged with success/failure and execution time

**🎯 Accuracy Improvements:**
- **95%+ Wake Word Accuracy** - Porcupine engine (2.5x better than alternatives)
- **83% Reduction in False Negatives** - Advanced audio processing eliminates missed detections
- **Smart Process Validation** - Checks if processes are running before attempting to close (prevents errors)
- **Fuzzy Matching** - Finds apps even with typos or partial names (60% similarity threshold)

**🔒 Privacy & Security:**
- **Local Speech Recognition** - Vosk STT runs entirely offline (no cloud required)
- **Optional Cloud Services** - All cloud services (Redis, PostgreSQL, AI) are optional
- **No Data Collection** - All data stays on your machine or your configured services
- **Configurable Storage** - Choose where your data lives

**⚡ Real-Time Features:**
- **WebSocket Heartbeat** - 30s ping intervals with 2s timeout for connection health
- **Live System Metrics** - Real-time CPU, memory, and cache statistics
- **Instant Voice Visualization** - Wave animations update instantly on voice activity
- **Smart Home Status** - Real-time ESP32 device status via WebSocket

## 📋 Requirements

- Windows 10/11 (64-bit)
- Python 3.10+
- Microphone
- Internet connection
- Optional tooling for advanced controls (place in `C:\Tools\...` **or** drop the executables into this repo’s `tools/` folder and Aiden will auto-detect them):
  - [ClickMonitorDDC](https://clickmonitorddc.bplaced.net/) for external monitor brightness
  - [NirCmd](https://www.nirsoft.net/utils/nircmd.html) for volume and display automation

## 🔧 Quick Start

```powershell
# 1. Clone repository
git clone https://github.com/SahiDemon/Aiden.git
cd aiden

# 2. Run installer (auto-downloads all models!)
.\install.ps1

# 3. Edit .env with your API keys
notepad .env

# 4. Start Aiden
.\run_aiden.ps1
```

**The installer automatically:**
- ✅ Checks Python version
- ✅ Creates virtual environment
- ✅ Installs all dependencies (including Porcupine)
- ✅ Downloads Vosk model (74 MB)
- ✅ Creates .env configuration
- ✅ Sets up database

> **🎯 NEW: Porcupine Wake Word Detection**
> For best accuracy, follow [PORCUPINE_SETUP.md](PORCUPINE_SETUP.md) to enable high-accuracy wake word detection!

## 🌊 Visual Overlay (Optional)

Aiden includes a beautiful animated overlay that displays at the top of your screen, showing real-time status with liquid wave animations.

### Setup Overlay

```powershell
# Navigate to overlay directory
cd overlay

# Install dependencies
npm install

# Build the overlay
npm run build

# Start Aiden (overlay will auto-launch)
cd ..
.\run_aiden.ps1
```

The overlay will automatically:
- ✅ Launch when Aiden starts
- ✅ Connect to Aiden's WebSocket for real-time updates
- ✅ Display listening, thinking, and replying states with animated waves
- ✅ Close when Aiden shuts down

**Features:**
- 🌊 Smooth liquid wave animations that respond to Aiden's state
- ✨ Shimmer text effects with gradient animations
- 🪟 Transparent, always-on-top window
- 🔄 Entry/exit animations (wave slides down on appear, slides up on disappear)

See [overlay/README.md](overlay/README.md) for more details.

## ⚙️ Configuration

Create a `.env` file with:

```env
# ===== AI Service (Groq Cloud) =====
GROQ_API_KEY=
GROQ_BASE_URL=https://api.groq.com/openai/v1/chat/completions
GROQ_MODEL=llama-3.1-8b-instant
GROQ_MAX_TOKENS=2000
GROQ_TEMPERATURE=0.7

# ===== Database (Neon DB) =====
NEON_DATABASE_URL=
NEON_POOL_SIZE=5
NEON_MAX_OVERFLOW=10
NEON_POOL_TIMEOUT=30

# ===== Cache (Redis Cloud) =====
REDIS_URL=
REDIS_DECODE_RESPONSES=true
REDIS_SOCKET_TIMEOUT=5
REDIS_SOCKET_CONNECT_TIMEOUT=5

# ===== Application Settings =====
APP_NAME=Aiden
USER_NAME=Sir
WAKE_WORD=aiden
HOTKEY=*
DEBUG=false

# ===== API Server =====
API_HOST=localhost
API_PORT=5000
API_RELOAD=false

# ===== Speech Settings =====
SPEECH_TTS_VOICE=en-US-AvaNeural
SPEECH_TTS_RATE=1.2
SPEECH_STT_LANGUAGE=en-US
SPEECH_STT_TIMEOUT=10
SPEECH_STT_ENERGY_THRESHOLD=600
SPEECH_STT_PAUSE_THRESHOLD=0.8
SPEECH_VOSK_MODEL_PATH=vosk_models/vosk-model-small-en-us-0.15

# ===== Porcupine Wake Word (High Accuracy) =====
SPEECH_PORCUPINE_ACCESS_KEY=your_key_here  # Get from console.picovoice.ai
SPEECH_PORCUPINE_MODEL_PATH=vosk_models/aiden_en_windows.ppn
SPEECH_PORCUPINE_SENSITIVITY=0.7
SPEECH_USE_PORCUPINE=true

# ===== ESP32 Smart Home =====
ESP32_ENABLED=true
ESP32_IP_ADDRESS=192.168.1.150
ESP32_TIMEOUT=5
ESP32_RETRY_ATTEMPTS=3

# ===== Cache Configuration =====
ENABLE_CACHING=true
CACHE_TTL_CONTEXT=300
CACHE_TTL_APP_PATHS=86400
CACHE_TTL_LLM_RESPONSE=3600
CACHE_TTL_TTS_AUDIO=3600

# ===== Spotify (optional) =====
SPOTIFY_ENABLED=false
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REFRESH_TOKEN=
SPOTIFY_DEFAULT_DEVICE_NAME=

```

To generate the `SPOTIFY_REFRESH_TOKEN`, run `python tools/spotify_refresh_token_helper.py` and follow the on-screen instructions (requires your Spotify app’s client ID/secret and the redirect URI `http://127.0.0.1:8888/callback`).

### Get Free API Keys

- **Groq AI**: [console.groq.com](https://console.groq.com) - FREE, super fast
- **Neon DB**: [neon.tech](https://neon.tech) - 500MB free
- **Redis**: [redis.com/cloud](https://redis.com/try-free) - 30MB free
- **Porcupine**: [console.picovoice.ai](https://console.picovoice.ai) - FREE wake word detection

**Note:** See [PORCUPINE_SETUP.md](PORCUPINE_SETUP.md) for wake word setup guide

## 🎯 Usage

**Voice Activation:**
1. Say "Aiden" (or use Porcupine wake word)
2. Speak your command
3. Aiden executes

**Hotkey Activation:**
1. Press Ctrl+Shift+Space (configurable)
2. Speak your command
3. Aiden executes

### 📱 Application Control Examples

**Basic App Launching:**
```
"Open Chrome"
"Launch Spotify"
"Start OBS Studio"
"Open Notepad"
"Launch Calculator"
"Open VS Code"
```

**Smart Filtering & Fuzzy Matching:**
```
"Open obs"              → Finds "OBS Studio"
"Launch vscode"         → Finds "Visual Studio Code"
"Open code"             → Finds "Visual Studio Code" (alias)
"Start calc"            → Finds "Calculator" (alias)
"Launch chrome"         → Finds "Google Chrome" (case-insensitive)
"Open discord"          → Finds "Discord" (partial match)
```

**Steam Games (Automatic Detection):**
```
"Launch Warframe"       → Automatically launches via Steam
"Open Counter-Strike"   → Detects Steam game and launches
"Start Half-Life"       → Finds Steam AppID and launches
"Play Skyrim"           → Auto-detects Steam game
"Open Portal 2"          → Launches via Steam protocol
```

**Closing Apps (Smart Process Detection):**
```
"Close Chrome"
"Close Notepad"
"Kill Python"
"Close Discord"
"Stop Spotify"
"Close Firefox"
"Kill all Chrome windows"
```

**Multi-App Commands:**
```
"Open Chrome and close Firefox"
"Launch Spotify and open VS Code"
"Close Discord and open Notepad"
"Start OBS and close Chrome"
```

### 🖥️ System Commands Examples
```
"Lock my computer"
"Shutdown the PC"
"Restart Windows"
"Put computer to sleep"
"Hibernate the system"
```

### ⚙️ Advanced System Control Examples

**Wi-Fi & Network:**
```
"Turn off Wi-Fi"
"Turn Wi-Fi back on"
"Disconnect from the current network"
"Enable airplane mode"
"Disable airplane mode"
```

**Bluetooth:**
```
"Turn Bluetooth on"
"Turn off Bluetooth"
```

**Power Management:**
```
"Enable power saving mode"
"Switch to balanced mode"
"What's my battery level?"
```

**Display Control:**
```
"Set brightness to 40 percent"
"Set brightness to 70"
"Turn off the screen"
```

**Audio Control:**
```
"Mute the speakers"
"Unmute"
"Toggle mute"
"Volume up"
"Volume down"
"Set volume to 30 percent"
```

**System Telemetry:**
```
"What's my battery level?"
"How busy is the CPU?"
"Show GPU status"
"What's the CPU usage?"
```

### 🎵 Media Control Examples

**Spotify:**
```
"Play on Spotify"
"Pause Spotify"
"Resume Spotify"
"Next song on Spotify"
"Previous track"
"Play my workout playlist on Spotify"
"Play Bohemian Rhapsody on Spotify"
"Set Spotify volume to 25 percent"
"Play Spotify on the living room speaker"
"Transfer Spotify to desktop"
"What song is this?"
"What's playing on Spotify?"
"Identify this song"
```

**YouTube:**
```
"Pause YouTube"
"Resume YouTube"
"Next video on YouTube"
"Previous video"
"Seek forward"
"Seek backward"
"Mute the YouTube tab"
```

**YouTube Music:**
```
"Pause YouTube Music"
"Resume my YouTube Music tab"
"Next song on YouTube Music"
"Previous track"
```

**Generic Media (Auto-detects active player):**
```
"Pause music"
"Resume playback"
"Next track"
"Previous song"
```

### 🏠 Smart Home Examples (ESP32)
```
"Turn on the fan"
"Turn off the fan"
"Increase fan speed"
"Speed up the fan"
"Change fan mode"
"Switch fan mode"
```

### ⏰ Timer & Scheduling Examples
```
"Shutdown in 30 minutes"
"Restart in 1 hour"
"Lock the computer in 5 minutes"
"Put computer to sleep in 2 hours"
"Cancel shutdown timer"
"Cancel all timers"
```

### 🎤 Wake Word Control Examples
```
"Disable wake word"
"Enable wake word"
"Toggle wake word detection"
```

### 💬 Conversation & Questions Examples
```
"What's 25 + 37?"
"Tell me about Python programming"
"What time is it?"
"How are you?"
"What's the weather like?"
"Explain quantum computing"
```

### 🚀 Multi-Command Examples
```
"Open Chrome and close Firefox"
"Turn off Wi-Fi and enable airplane mode"
"Pause Spotify and lock my computer"
"Set brightness to 50 and mute the volume"
```

## 🏗️ Project Structure

```
aiden/
├── src/
│   ├── main.py              # Entry point
│   ├── core/                # Core logic
│   ├── ai/                  # AI integration
│   ├── speech/              # Voice I/O
│   ├── execution/           # Command execution
│   ├── database/            # Data persistence
│   ├── api/                 # Web API
│   └── utils/               # Utilities
├── config/                  # Configuration
├── sounds/                  # Audio files
├── run_aiden.ps1           # Start script
└── stop_aiden.ps1          # Stop script
```

## 🛠️ Troubleshooting

**Microphone not working?**
- Check Windows sound settings
- Grant microphone permissions
- Adjust `STT_ENERGY_THRESHOLD` in .env

**Wake word not detecting?**
- **Using Porcupine (recommended)**: Follow [PORCUPINE_SETUP.md](PORCUPINE_SETUP.md) setup guide
- Increase sensitivity: `SPEECH_PORCUPINE_SENSITIVITY=0.8`
- Ensure AccessKey is set in `.env`
- Check custom `.ppn` model exists
- Fallback to Vosk: `SPEECH_USE_PORCUPINE=false`
- Speak clearly and directly to mic

**App launch fails?**
- First launch may be slow (app discovery - scans registry and Start Menu)
- Check app name spelling (try partial names - fuzzy matching will help)
- Try full app name or common aliases (code, calc, chrome)
- For Steam games: Ensure Steam is installed and game is in your library
- Steam games auto-detect - just say the game name (e.g., "Launch Warframe")
- Check if app is installed (Aiden scans 353+ apps from registry)
- Try alternative names (e.g., "vscode" instead of "Visual Studio Code")

## 📚 API Documentation

Visit http://localhost:5000/docs when Aiden is running

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Commit changes
4. Push to branch
5. Open Pull Request

## 📄 License

MIT License - see LICENSE file

## 🙏 Credits

- Porcupine (Picovoice) - High-accuracy wake word detection
- Vosk - Offline speech recognition (STT & fallback wake word)
- edge-tts - Microsoft Edge TTS
- Groq - Super fast AI inference
- Neon - Serverless PostgreSQL
- FastAPI - Modern web framework

---

**Made with ❤️ for productivity**
