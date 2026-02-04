# Wake Word False Positive Solution - Complete Summary

## What I Created For You

I've built a complete debugging and analysis toolkit to help you identify and fix the false positive wake word detections you're experiencing on Discord.

## The Tools

### 1. Basic Debugger (`scripts/debug_wake_word.py`)
**What it does:**
- Continuously records and transcribes everything you say
- Shows exactly what text the wake word detector is matching
- Logs timestamps, energy levels, and detected text
- Saves audio clips of each detection
- Lets you mark false positives in real-time

**When to use:** First debugging session to understand the problem

### 2. Advanced Debugger (`scripts/debug_wake_word_advanced.py`)
**What it does:**
- Everything the basic debugger does
- PLUS monitors both Porcupine AND Vosk simultaneously
- Shows which model detected what
- Helps compare model performance

**When to use:** When you want to see if one model is better than the other

### 3. Settings Tester (`scripts/test_wake_word_settings.py`)
**What it does:**
- Shows your current wake word configuration
- Provides recommended presets for common issues
- Explains what each setting does
- Gives troubleshooting tips

**When to use:** Before debugging to understand your settings, or when choosing new values

### 4. Easy Launchers
- `run_wake_word_debug.ps1` - PowerShell script with options
- `debug_wake_word.bat` - Double-click Windows batch file

## How To Use (Step-by-Step)

### Step 1: Understand Your Current Settings
```powershell
python scripts/test_wake_word_settings.py
```
This shows what settings you're currently using and what they mean.

### Step 2: Run the Debugger
```powershell
# Option A: Basic (recommended first)
.\run_wake_word_debug.ps1

# Option B: Advanced (both models)
.\run_wake_word_debug.ps1 -Advanced

# Option C: Double-click
debug_wake_word.bat
```

### Step 3: Reproduce the Problem
- Talk on Discord normally
- Do whatever triggers the false positives
- Let it run for 5-10 minutes to get good data

### Step 4: Mark False Positives
When the debugger detects the wake word:
- If it was WRONG (false positive): Type `f` and press Enter
- If it was CORRECT (true positive): Just press Enter

### Step 5: Analyze the Results
Open the log file: `logs/wake_word_debug_TIMESTAMP.txt`

Look for patterns:
```
[2026-01-14 15:23:47] WAKE WORD DETECTION
  Text: 'aid in the team'  <-- This triggered it!
  Energy: 312.45
  >>> MARKED AS FALSE POSITIVE <<<
```

Common false positive phrases:
- "aid in" / "aiding"
- "eaten" / "eating"
- "a den"
- "hey dan"

### Step 6: Listen to Audio Clips
Open: `logs/wake_word_audio_TIMESTAMP/`

Listen to the WAV files to hear exactly what was said when false positives occurred.

### Step 7: Adjust Settings
Based on what you found, update your `.env` file:

**For TOO MANY false positives:**
```env
SPEECH_PORCUPINE_SENSITIVITY=0.3
SPEECH_PORCUPINE_MIN_ENERGY=250
SPEECH_PORCUPINE_DEBOUNCE_SECONDS=2.0
```

**For MISSING real wake words:**
```env
SPEECH_PORCUPINE_SENSITIVITY=0.7
SPEECH_PORCUPINE_MIN_ENERGY=150
```

**For BALANCED (good starting point):**
```env
SPEECH_PORCUPINE_SENSITIVITY=0.5
SPEECH_PORCUPINE_MIN_ENERGY=200
SPEECH_PORCUPINE_DEBOUNCE_SECONDS=1.5
```

### Step 8: Test Again
Run the debugger again with new settings and compare results.

### Step 9: Test in Production
Once satisfied, run Aiden normally:
```powershell
.\run_aiden.ps1
```

## Understanding the Settings

### Sensitivity (0.0 - 1.0)
- **0.2-0.3**: Very strict, minimal false positives, might miss some real ones
- **0.4-0.6**: Balanced, good for most use cases
- **0.7-0.9**: Very sensitive, catches everything, many false positives

### Min Energy (50 - 500)
- **100-150**: Picks up quiet sounds (more false positives)
- **200-250**: Balanced, filters silence
- **300+**: Very strict, only loud/clear audio

### Debounce Seconds (0.5 - 5.0)
- **1.0s**: Quick re-triggering possible
- **1.5s**: Balanced (default)
- **2.5s+**: Prevents rapid re-triggers

### Confirmation Window (0.1 - 2.0)
- **≤0.3s**: Single detection mode (immediate response)
- **0.5s+**: Requires 2 detections close together (filters noise)

## What Each File Does

```
Aiden/
├── run_wake_word_debug.ps1          # Main launcher script
├── debug_wake_word.bat              # Windows double-click launcher
├── WAKE_WORD_DEBUG_QUICKSTART.md    # Quick start guide
├── scripts/
│   ├── debug_wake_word.py           # Basic debugger (Vosk)
│   ├── debug_wake_word_advanced.py  # Advanced debugger (Both models)
│   ├── test_wake_word_settings.py   # Settings viewer/tester
│   ├── README_WAKE_WORD_DEBUG.md    # Detailed documentation
│   └── WAKE_WORD_SOLUTION_SUMMARY.md # This file
└── logs/
    ├── wake_word_debug_*.txt        # Generated: Debug logs
    └── wake_word_audio_*/           # Generated: Audio clips
```

## Common Issues and Solutions

### Issue: "aid in" triggering false positives
**Why:** Very similar pronunciation to "aiden"
**Solution:** 
- Lower sensitivity to 0.3-0.4
- Consider training custom Porcupine model with your voice

### Issue: Triggers on background Discord audio
**Why:** Min energy too low, picking up other people's voices
**Solution:**
- Increase min_energy to 250-300
- Enable confirmation window (0.5s)

### Issue: Multiple triggers for one wake word
**Why:** Debounce time too short
**Solution:**
- Increase debounce to 2.0-2.5 seconds

### Issue: Not responding when you say wake word
**Why:** Sensitivity too low or speaking too quietly
**Solution:**
- Increase sensitivity to 0.6-0.7
- Lower min_energy to 150
- Speak louder/clearer

## Advanced: Custom Porcupine Model

If you're still getting too many false positives, train a custom model:

1. Go to [Picovoice Console](https://console.picovoice.ai/)
2. Create account (free tier available)
3. Train custom "aiden" wake word with YOUR voice
4. Download the `.ppn` file
5. Update `.env`:
   ```env
   SPEECH_PORCUPINE_MODEL_PATH=path/to/your/custom_aiden.ppn
   ```

This makes the detector specifically tuned to YOUR pronunciation.

## Tips for Best Results

1. **Test in real conditions** - If it happens on Discord, test while on Discord
2. **Get enough data** - Run debugger for 5-10 minutes minimum
3. **One change at a time** - Only adjust one setting per test
4. **Document changes** - Keep notes on what you tried
5. **Listen to clips** - Audio files show exactly what happened
6. **Compare runs** - Keep logs from different settings to compare
7. **Be patient** - Finding optimal settings takes iteration

## Quick Reference Commands

```powershell
# View current settings
python scripts/test_wake_word_settings.py

# Run basic debugger
.\run_wake_word_debug.ps1

# Run advanced debugger
.\run_wake_word_debug.ps1 -Advanced

# Get help
.\run_wake_word_debug.ps1 -Help

# After changes, test in production
.\run_aiden.ps1
```

## Expected Results

After using these tools, you should:
1. Know exactly what phrases trigger false positives
2. Have audio evidence of each detection
3. Understand which settings to adjust
4. Have optimal configuration for your environment
5. Significantly reduced false positive rate

## Support

If you're still having issues after trying these tools:
1. Share the debug log file
2. Share a few audio clips (especially false positives)
3. List the specific phrases that trigger false positives
4. Note your environment (Discord, background noise, etc.)

## Summary

You now have:
- ✅ Real-time transcription debugger
- ✅ Audio recording of detections
- ✅ False positive marking system
- ✅ Detailed logging with timestamps
- ✅ Settings analyzer and recommendations
- ✅ Easy-to-use launchers
- ✅ Comprehensive documentation

**Next step:** Run `.\run_wake_word_debug.ps1` and start collecting data!
