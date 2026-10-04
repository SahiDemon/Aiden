# Wake Word False Positive Debugger

These scripts help you identify and fix false positive wake word detections.

## The Problem

Your wake word detector is triggering when you're talking on Discord (or doing other activities) even though you're not saying "hey aiden". These tools will help you:

1. **See exactly what words are being detected** when false triggers occur
2. **Record audio clips** of each detection for analysis
3. **Track patterns** in false positives
4. **Test different threshold settings**

## Scripts

### 1. `debug_wake_word.py` - Basic Debugger

**What it does:**
- Continuously transcribes everything you say using Vosk
- Detects when the wake word matching logic would trigger
- Logs all transcriptions with timestamps and audio energy levels
- Saves audio clips of each detection
- Lets you mark detections as false positives

**How to use:**
```powershell
# Activate venv
.\venv\Scripts\Activate.ps1

# Run the debugger
python scripts/debug_wake_word.py
```

**What to do:**
1. Start the script
2. Talk normally (on Discord, to yourself, whatever)
3. When it detects the wake word, it will beep and ask if it was a FALSE POSITIVE
4. Type `f` and press Enter if it was wrong, or just press Enter if it was correct
5. Press Ctrl+C when done

**Output:**
- `logs/wake_word_debug_TIMESTAMP.txt` - Full log of everything detected
- `logs/wake_word_audio_TIMESTAMP/*.wav` - Audio clips of each detection

### 2. `debug_wake_word_advanced.py` - Advanced Debugger

**What it does:**
- Monitors **BOTH** Porcupine and Vosk simultaneously
- Shows which model detected what
- Helps identify if one model is better than the other
- Same logging and audio saving as basic version

**How to use:**
```powershell
# Activate venv
.\venv\Scripts\Activate.ps1

# Run the advanced debugger
python scripts/debug_wake_word_advanced.py
```

**What to do:**
Same as basic version, but you'll see which model (Porcupine or Vosk) triggered each detection.

## Analyzing Results

### 1. Check the Log File

Open `logs/wake_word_debug_TIMESTAMP.txt` and look for patterns:

```
[2026-01-14 15:23:45.123] TRANSCRIPTION
  Text: 'i'm going to play some games'
  Energy: 245.67

[2026-01-14 15:23:47.456] WAKE WORD DETECTION
  Text: 'aid in the team'  <-- FALSE POSITIVE!
  Energy: 312.45
  >>> MARKED AS FALSE POSITIVE by user <<<
```

**Common patterns to look for:**
- Words that sound like "aiden": "aid in", "aiding", "a den", "ate in"
- Similar sounding words: "eaten", "eden", "aden"
- Partial matches in longer phrases

### 2. Listen to Audio Clips

The audio clips are saved in `logs/wake_word_audio_TIMESTAMP/`:
- Each detection has its own WAV file
- Listen to false positives to hear what actually triggered
- Compare true positives vs false positives

### 3. Check Energy Levels

Look at the `Energy:` values in the log:
- Too low? Might be picking up background noise
- Inconsistent? Might need better thresholds

## Fixing False Positives

Based on what you find, you can adjust settings in `.env`:

### Option 1: Adjust Porcupine Sensitivity
```env
# Lower = fewer false positives, but might miss real wake words
# Higher = catches more wake words, but more false positives
SPEECH_PORCUPINE_SENSITIVITY=0.3  # Try values between 0.0-1.0
```

### Option 2: Increase Debounce Time
```env
# Seconds between detections (prevents rapid re-triggering)
SPEECH_PORCUPINE_DEBOUNCE_SECONDS=2.5  # Default is 1.5
```

### Option 3: Increase Minimum Energy
```env
# Minimum audio energy to process (filters out quiet sounds)
SPEECH_PORCUPINE_MIN_ENERGY=200  # Default is 150
```

### Option 4: Adjust Confirmation Window
```env
# Require detection to be confirmed within this window
SPEECH_PORCUPINE_CONFIRMATION_WINDOW=0.5  # Default is 0.3
```

### Option 5: Improve Wake Word Matching

Edit `src/speech/wake_word.py` line 161-196 to adjust the fuzzy matching logic:
- Make similarity threshold stricter (increase from 0.90 to 0.95)
- Remove variations that cause false positives
- Add more specific filtering

## Testing Your Changes

After adjusting settings:

1. **Stop Aiden** if it's running
2. **Run the debugger again** with new settings
3. **Compare results** - are there fewer false positives?
4. **Make sure true positives still work** - say "hey aiden" a few times

## Tips

1. **Test in your actual environment** - If false positives happen on Discord, run the debugger while on Discord
2. **Test for at least 5-10 minutes** - Get a good sample size
3. **Try different volumes** - Speak at different volumes to see what triggers
4. **Check the audio clips** - They're the best way to understand what's happening

## Example Session

```powershell
PS F:\GitHub\Aiden> python scripts/debug_wake_word_advanced.py

================================================================================
ADVANCED WAKE WORD DEBUGGER
================================================================================
Wake Word: 'aiden'
Porcupine: ENABLED
Vosk: ENABLED

Speak normally - everything will be transcribed
When wake word is detected, mark it as false positive if needed
Press Ctrl+C to stop
================================================================================

[2026-01-14 15:23:45.123] [VOSK] Transcription
  Text: 'hello everyone'
  Energy: 234.56

[2026-01-14 15:23:47.456] [PORCUPINE] *** WAKE WORD DETECTED ***
  Text: '[Porcupine Detection #0]'
  Energy: 312.45
  Audio: porcupine_20260114_152347.wav

================================================================================
>>> WAKE WORD DETECTED by PORCUPINE
>>> Audio saved: logs/wake_word_audio_20260114_152347/porcupine_20260114_152347.wav
>>> Was this a FALSE POSITIVE?
>>> Type 'f' and press Enter (or just Enter to skip): f

✗ FALSE POSITIVE (Total: 1)
================================================================================

Continuing to listen...
```

## Need Help?

If you're still getting false positives after trying these tools:

1. Share the log file and audio clips
2. Note the specific phrases that trigger false positives
3. Consider training a custom Porcupine model with your voice
4. Try switching between Porcupine and Vosk to see which works better

## Advanced: Custom Porcupine Model

If you're getting too many false positives, you can train a custom Porcupine model:

1. Go to [Picovoice Console](https://console.picovoice.ai/)
2. Create a custom "aiden" wake word with your voice
3. Download the `.ppn` file
4. Update `.env` with the path:
   ```env
   SPEECH_PORCUPINE_MODEL_PATH=path/to/your/custom_aiden.ppn
   ```

This will make the detector specifically tuned to YOUR pronunciation of "aiden".
