"""
Quick Wake Word Settings Tester
Tests different sensitivity/threshold settings to find optimal values
"""
import os
import sys
import time
from datetime import datetime

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


def print_current_settings():
    """Display current wake word settings"""
    settings = get_settings()
    
    print("\n" + "=" * 80)
    print("CURRENT WAKE WORD SETTINGS")
    print("=" * 80)
    print(f"Wake Word: '{settings.app.wake_word}'")
    print(f"\nPorcupine Settings:")
    print(f"  Enabled: {settings.speech.use_porcupine}")
    print(f"  Access Key: {'SET' if settings.speech.porcupine_access_key else 'NOT SET'}")
    print(f"  Model Path: {settings.speech.porcupine_model_path}")
    print(f"  Sensitivity: {settings.speech.porcupine_sensitivity} (0.0-1.0)")
    print(f"    └─ Lower = fewer false positives, might miss real wake words")
    print(f"    └─ Higher = catches more, but more false positives")
    print(f"  Min Energy: {settings.speech.porcupine_min_energy}")
    print(f"    └─ Filters out audio quieter than this threshold")
    print(f"  Debounce: {settings.speech.porcupine_debounce_seconds}s")
    print(f"    └─ Minimum time between detections")
    print(f"  Confirmation Window: {settings.speech.porcupine_confirmation_window}s")
    print(f"    └─ ≤0.3s = single detection, >0.5s = requires 2 detections")
    
    print(f"\nVosk Settings:")
    print(f"  Model Path: {settings.speech.vosk_model_path}")
    print(f"  Model Exists: {os.path.exists(settings.speech.vosk_model_path)}")
    
    print("=" * 80 + "\n")


def print_recommendations():
    """Print recommendations based on common issues"""
    print("\n" + "=" * 80)
    print("RECOMMENDED SETTINGS FOR COMMON ISSUES")
    print("=" * 80)
    
    print("\n1. TOO MANY FALSE POSITIVES (triggering when you're not saying wake word)")
    print("   Add to .env:")
    print("   SPEECH_PORCUPINE_SENSITIVITY=0.3")
    print("   SPEECH_PORCUPINE_MIN_ENERGY=250")
    print("   SPEECH_PORCUPINE_DEBOUNCE_SECONDS=2.0")
    
    print("\n2. MISSING REAL WAKE WORDS (not responding when you say it)")
    print("   Add to .env:")
    print("   SPEECH_PORCUPINE_SENSITIVITY=0.7")
    print("   SPEECH_PORCUPINE_MIN_ENERGY=150")
    print("   SPEECH_PORCUPINE_DEBOUNCE_SECONDS=1.0")
    
    print("\n3. BALANCED (good starting point)")
    print("   Add to .env:")
    print("   SPEECH_PORCUPINE_SENSITIVITY=0.5")
    print("   SPEECH_PORCUPINE_MIN_ENERGY=200")
    print("   SPEECH_PORCUPINE_DEBOUNCE_SECONDS=1.5")
    
    print("\n4. VERY STRICT (minimal false positives, might miss some real ones)")
    print("   Add to .env:")
    print("   SPEECH_PORCUPINE_SENSITIVITY=0.2")
    print("   SPEECH_PORCUPINE_MIN_ENERGY=300")
    print("   SPEECH_PORCUPINE_DEBOUNCE_SECONDS=2.5")
    print("   SPEECH_PORCUPINE_CONFIRMATION_WINDOW=0.5")
    
    print("\n5. VERY LENIENT (catches everything, many false positives)")
    print("   Add to .env:")
    print("   SPEECH_PORCUPINE_SENSITIVITY=0.8")
    print("   SPEECH_PORCUPINE_MIN_ENERGY=100")
    print("   SPEECH_PORCUPINE_DEBOUNCE_SECONDS=1.0")
    
    print("\n" + "=" * 80)
    print("After changing .env, restart Aiden or run the debugger to test")
    print("=" * 80 + "\n")


def print_troubleshooting():
    """Print troubleshooting tips"""
    print("\n" + "=" * 80)
    print("TROUBLESHOOTING TIPS")
    print("=" * 80)
    
    print("\nSymptom: False positives when talking on Discord")
    print("Likely Cause: Sensitivity too high or similar-sounding words")
    print("Solution:")
    print("  1. Run: .\\run_wake_word_debug.ps1 -Advanced")
    print("  2. Talk on Discord normally")
    print("  3. Mark false positives when they occur")
    print("  4. Check log to see what words triggered it")
    print("  5. Lower sensitivity or increase min_energy")
    
    print("\nSymptom: Not responding to wake word")
    print("Likely Cause: Sensitivity too low or audio too quiet")
    print("Solution:")
    print("  1. Check if Porcupine model exists (see above)")
    print("  2. Increase sensitivity to 0.7")
    print("  3. Lower min_energy to 150")
    print("  4. Speak louder and clearer")
    
    print("\nSymptom: Triggers multiple times for one wake word")
    print("Likely Cause: Debounce time too short")
    print("Solution:")
    print("  1. Increase SPEECH_PORCUPINE_DEBOUNCE_SECONDS to 2.5")
    
    print("\nSymptom: Triggers on random noise")
    print("Likely Cause: Min energy too low")
    print("Solution:")
    print("  1. Increase SPEECH_PORCUPINE_MIN_ENERGY to 300")
    print("  2. Enable confirmation window (0.5s)")
    
    print("\n" + "=" * 80 + "\n")


def print_testing_guide():
    """Print testing guide"""
    print("\n" + "=" * 80)
    print("TESTING GUIDE")
    print("=" * 80)
    
    print("\nStep 1: Identify the Problem")
    print("  Run: .\\run_wake_word_debug.ps1")
    print("  Talk normally for 5-10 minutes")
    print("  Mark false positives when they occur")
    
    print("\nStep 2: Analyze the Log")
    print("  Open: logs/wake_word_debug_TIMESTAMP.txt")
    print("  Look for patterns in false positives")
    print("  Check energy levels of false vs true positives")
    
    print("\nStep 3: Adjust Settings")
    print("  Based on log analysis, update .env file")
    print("  Change ONE setting at a time")
    print("  Document what you changed")
    
    print("\nStep 4: Test Again")
    print("  Run debugger with new settings")
    print("  Compare results to previous run")
    print("  Repeat until satisfied")
    
    print("\nStep 5: Test in Production")
    print("  Run Aiden normally: .\\run_aiden.ps1")
    print("  Use for a few hours")
    print("  If issues persist, go back to Step 1")
    
    print("\n" + "=" * 80 + "\n")


def main():
    """Main entry point"""
    print("\n" + "=" * 80)
    print("WAKE WORD SETTINGS TESTER")
    print("=" * 80)
    print("\nThis tool helps you understand and optimize your wake word settings")
    print("to reduce false positives while maintaining good detection accuracy.")
    print("=" * 80)
    
    # Show current settings
    print_current_settings()
    
    # Show recommendations
    print_recommendations()
    
    # Show troubleshooting
    print_troubleshooting()
    
    # Show testing guide
    print_testing_guide()
    
    print("\nNext Steps:")
    print("  1. Review your current settings above")
    print("  2. Choose a recommended preset or custom values")
    print("  3. Update your .env file")
    print("  4. Run: .\\run_wake_word_debug.ps1")
    print("  5. Test and iterate")
    print("\nFor detailed debugging, see: docs/guides/wake-word/debugging.md")
    print("For quick start, see: docs/guides/wake-word/solution-summary.md")
    print("")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        print(f"\nERROR: {e}")
        print("Make sure .env file exists and is properly configured")
        sys.exit(1)
