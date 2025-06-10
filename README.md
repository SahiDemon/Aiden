*# Aiden - AI Desktop Agent

Aiden is a voice-activated AI desktop agent that uses natural voice interaction to assist with computer tasks. It is designed to be respectful, efficient, and personalized to your preferences.

## Features

- **Voice Activation**: Trigger with a hotkey (asterisk '*' key) and issue commands by voice
- **Natural Voice Responses**: Speaks back in a natural female voice using edge-tts
- **Personalized Interaction**: Addresses you as "Boss" and remembers your preferences
- **Command Processing**: Uses LLM capabilities to understand natural language commands
- **System Integration**: Controls applications, performs file operations, web searches, and more
- **Memory**: Tracks interaction history to become more helpful over time

## Requirements

- Python 3.9 or higher
- Operating System: Windows, macOS, or Linux
- Microphone for voice input
- Speakers for voice output
- Internet connection (for STT and LLM capabilities)

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/aiden.git
   cd aiden
   ```

2. Create a virtual environment:
   ```
   python -m venv .venv
   ```

3. Activate the virtual environment:
   - Windows: `.\.venv\Scripts\activate`
   - macOS/Linux: `source .venv/bin/activate`

4. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

5. Install tgpt CLI tool for LLM capabilities:
   - Visit https://github.com/aandrew-me/tgpt and follow installation instructions
   - Ensure `tgpt` is available in your PATH

6. Alternatively, use the included installation script:
   ```
   python install.py
   ```

## Configuration

The configuration files are located in the `config` directory:

- `config.json`: General application settings
- `user_profile.json`: User-specific preferences and history

You can modify these files directly to customize Aiden's behavior.

## Usage

1. Activate the virtual environment:
   - Windows: `.\.venv\Scripts\activate`
   - macOS/Linux: `source .venv/bin/activate`

2. Run the application:
   ```
   # Make sure you run this from the project root directory
   python -m src.main
   ```

3. Once running, press the `*` (asterisk) key to activate Aiden, then speak your command.

4. Aiden will respond verbally and perform the requested action.

### Example Commands

- "Open Chrome"
- "What's the weather like today?"
- "Create a new text file on my desktop"
- "Search the web for AI news"
- "What time is it?"
- "Open my documents folder"

## Development

### Project Structure

```
aiden/
├── config/             # Configuration files
│   ├── config.json     # Application settings
│   └── user_profile.json # User preferences and history
├── logs/               # Log files
├── src/                # Source code
│   ├── utils/          # Utility modules
│   │   ├── config_manager.py      # Configuration handling
│   │   ├── voice_system.py        # TTS functionality
│   │   ├── speech_recognition_system.py # STT functionality
│   │   ├── hotkey_listener.py     # Keyboard activation
│   │   ├── llm_connector.py       # AI processing
│   │   └── command_dispatcher.py  # Command routing
│   └── main.py         # Main application entry point
├── temp/               # Temporary files
├── install.py          # Installation helper
├── requirements.txt    # Dependencies
└── setup.py            # Installation script
```

### Main Components

- **ConfigManager**: Handles configuration and user profiles
- **VoiceSystem**: Manages text-to-speech capabilities
- **SpeechRecognitionSystem**: Handles speech-to-text functionality
- **HotkeyListener**: Detects hotkey presses to activate the agent
- **LLMConnector**: Connects to language models for command processing
- **CommandDispatcher**: Routes commands to appropriate handlers

## Troubleshooting

### Common Issues

1. **Module Not Found Errors**:
   - Make sure you're running the application from the project root directory
   - Ensure the virtual environment is activated

2. **Audio Playback Issues**:
   - The application uses pygame for audio in Python 3.11+ and falls back to other methods
   - Make sure your system has working audio output

3. **Speech Recognition Problems**:
   - Ensure your microphone is working and properly configured
   - Check internet connectivity for the Google Web Speech API

4. **tgpt Not Found**:
   - Make sure tgpt is installed and available in your system PATH
   - Test by running `tgpt "hello"` in your terminal

## Security Considerations

Aiden follows these security principles:

- Restricted file system access to prevent operations in sensitive directories
- Confirmation required for potentially destructive operations
- No arbitrary system command execution
- User data stored locally, not sent to external services (except for STT and LLM processing)

## License

[MIT License](LICENSE)

## Acknowledgements

- [edge-tts](https://github.com/rany2/edge-tts) for natural voice capabilities
- [tgpt](https://github.com/aandrew-me/tgpt) for LLM interaction
- [SpeechRecognition](https://github.com/Uberi/speech_recognition) for speech-to-text capabilities
- [pynput](https://github.com/moses-palmer/pynput) for hotkey detection
