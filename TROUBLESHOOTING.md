# Aiden Troubleshooting Guide

This guide provides solutions for common issues you might encounter with Aiden AI Desktop Agent.

## Speech Recognition Issues

### Microphone Not Working

If Aiden is not recognizing your voice or giving "Error" messages:

1. **Check Microphone Hardware**
   - Ensure your microphone is properly connected
   - Try using a different microphone if available
   - Test your microphone in another application (like Voice Recorder)

2. **Check Microphone Permissions**
   - Make sure your application has permission to access the microphone
   - On Windows: Settings > Privacy > Microphone
   - On macOS: System Preferences > Security & Privacy > Microphone
   - On Linux: Check your distribution's settings

3. **Adjust Microphone Settings**
   - Open Sound settings on your computer and adjust microphone levels
   - Ensure the correct microphone is set as default
   - Increase microphone volume and sensitivity

4. **Try Adjusting Aiden's Speech Recognition Settings**
   - Open `config/config.json`
   - Try these adjustments:
     ```json
     "stt": {
       "energy_threshold": 4000,  // Try a higher value if in a noisy environment
       "pause_threshold": 0.8,    // Try a higher value if having cutoff issues
       "timeout": 15             // Try a longer timeout
     }
     ```

5. **Check Internet Connection**
   - Google speech recognition requires an internet connection
   - Verify you have a stable connection

6. **Install Required Packages**
   - Make sure all requirements are installed: `pip install -r requirements.txt`
   - For PyAudio issues on Windows, try: `pip install pipwin` then `pipwin install pyaudio`

## Fan Control Issues

If you're having trouble with the ESP32 fan control:

1. **Check ESP32 Connection**
   - Make sure your ESP32 is powered on and connected to your network
   - Verify the IP address in `config/config.json` is correct
   - Try accessing the ESP32 directly from a web browser (e.g., http://192.168.1.6/on)

2. **Test ESP32 Commands Directly**
   - Run `python test_esp32.py` to test direct communication with the ESP32

3. **Check Network Settings**
   - Make sure your computer and ESP32 are on the same network
   - Check for any firewall rules that might block communication

## Sound and Voice Issues

If you're having issues with Aiden's voice or sound effects:

1. **Verify Audio Output**
   - Check your speakers/headphones are properly connected and volume is up
   - Test audio playback with another application

2. **Check Required Packages**
   - For edge-tts: `pip install edge-tts`
   - For audio playback: `pip install pygame`

3. **Try a Different Voice**
   - Modify the `voice_id` in `config/config.json` to use a different voice
   - Available voices include "en-US-GuyNeural", "en-US-JennyNeural", etc.

4. **Disable Sound Effects**
   - If sound effects are causing issues, disable them in the config

## Logging and Debugging

For more detailed troubleshooting:

1. **Check Log File**
   - Look at `logs/aiden.log` for detailed error information

2. **Increase Logging Level**
   - In `config/config.json`, change `"log_level": "INFO"` to `"log_level": "DEBUG"`
   - Restart Aiden to get more detailed logs

3. **Run with Print Statements**
   - Add `print()` statements to the code where issues might be occurring
   - Restart and observe the console output

## Getting Help

If you continue to have issues:

1. Check the GitHub repository for updates or known issues
2. File an issue on GitHub with:
   - A description of the problem
   - Steps to reproduce
   - Your config file settings (remove any personal information)
   - Relevant log entries
