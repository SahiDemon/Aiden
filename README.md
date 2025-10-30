# 🤖 Aiden AI Assistant

A powerful voice-controlled AI assistant for Windows with context-aware conversations and intelligent command execution.

## ✨ Features

- **🎤 High-Accuracy Wake Word** - Say "Aiden" with Porcupine detection (2.5x more accurate)
- **⌨️ Global Hotkey** - Press Ctrl+Shift+Space for instant access
- **💬 Context-Aware** - Remembers conversation context for follow-up questions
- **🚀 Multi-Command** - Execute multiple commands in one request
- **🧠 Smart Discovery** - Automatically finds and launches applications
- **⚡ Lightning Fast** - Sub-second response times with Groq AI
- **🔇 Hidden Mode** - Runs silently in system tray
- **📊 Web Dashboard** - Optional web interface at http://localhost:5000
- **🎯 Zero False Negatives** - Advanced audio processing eliminates missed detections

## 📋 Requirements

- Windows 10/11 (64-bit)
- Python 3.10+
- Microphone
- Internet connection

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
USER_NAME=Boss
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

```

### Get Free API Keys

- **Groq AI**: [console.groq.com](https://console.groq.com) - FREE, super fast
- **Neon DB**: [neon.tech](https://neon.tech) - 500MB free
- **Redis**: [redis.com/cloud](https://redis.com/try-free) - 30MB free
- **Porcupine**: [console.picovoice.ai](https://console.picovoice.ai) - FREE wake word detection

**Note:** See [PORCUPINE_SETUP.md](PORCUPINE_SETUP.md) for wake word setup guide

## 🎯 Usage

**Voice Activation:**
1. Say "Aiden"
2. Speak your command
3. Aiden executes

**Hotkey Activation:**
1. Press Ctrl+Shift+Space
2. Speak your command
3. Aiden executes

**Example Commands:**
```
"Open Chrome"
"Close Notepad and open Calculator"
"Turn on the fan" (ESP32)
"Kill Python"
"Lock my computer"
"What's 25 + 37?"
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
- First launch may be slow (app discovery)
- Check app name spelling
- Try full app name

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
