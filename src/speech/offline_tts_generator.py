import sys
import pyttsx3
import traceback

def generate_audio(text, output_file):
    try:
        engine = pyttsx3.init()
        
        # Optional: Adjust voice/rate settings here
        voices = engine.getProperty('voices')
        if voices:
            # Use first available voice
            engine.setProperty('voice', voices[0].id)
        
        engine.setProperty('rate', 175)  # Speed (words per minute)
        engine.setProperty('volume', 1.0)  # Volume (0.0 to 1.0)
        
        engine.save_to_file(text, output_file)
        engine.runAndWait()
        
        # Verify file was created
        import os
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            print(f"SUCCESS: Generated {output_file}", file=sys.stderr)
            return True
        else:
            print(f"ERROR: File not created or empty: {output_file}", file=sys.stderr)
            return False
            
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python offline_tts_generator.py <text> <output_file>", file=sys.stderr)
        sys.exit(1)
        
    text = sys.argv[1]
    output_file = sys.argv[2]
    
    success = generate_audio(text, output_file)
    sys.exit(0 if success else 1)
