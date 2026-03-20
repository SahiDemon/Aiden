"""
Test Google Cloud Text-to-Speech Integration
Run this script to verify your Google TTS setup
"""
import os
import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def test_google_tts():
    """Test Google TTS setup and generate sample audio"""
    print("\n" + "="*60)
    print("Google Chirp 3 HD TTS Test")
    print("="*60 + "\n")
    
    try:
        # Load settings
        settings = get_settings()
        
        print("📋 Configuration:")
        print(f"   Provider: {settings.speech.tts_provider}")
        print(f"   Google Voice: {settings.speech.google_tts_voice}")
        print(f"   Speaking Rate: {settings.speech.google_tts_speaking_rate}")
        print(f"   Pitch: {settings.speech.google_tts_pitch}")
        print(f"   Credentials: {settings.speech.google_tts_credentials_path}")
        print()
        
        if settings.speech.tts_provider != "google":
            print("⚠️  TTS provider is not set to 'google'")
            print("   Update SPEECH_TTS_PROVIDER=google in your .env file")
            return
        
        # Check credentials file
        creds_path = settings.speech.google_tts_credentials_path
        if not creds_path:
            print("❌ Google credentials path not set!")
            print("   Set SPEECH_GOOGLE_TTS_CREDENTIALS_PATH in .env file")
            return
        
        if not os.path.exists(creds_path):
            print(f"❌ Credentials file not found: {creds_path}")
            print("   Check the path in SPEECH_GOOGLE_TTS_CREDENTIALS_PATH")
            return
        
        print(f"✅ Credentials file found: {creds_path}\n")
        
        # Initialize Google TTS client
        print("🔧 Initializing Google TTS client...")
        from google.cloud import texttospeech
        
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
        client = texttospeech.TextToSpeechClient()
        print("✅ Google TTS client initialized successfully!\n")
        
        # Test synthesis
        print("🎤 Testing speech synthesis...")
        test_text = "Hello! This is a test of Google Chirp 3 HD voice synthesis."
        
        synthesis_input = texttospeech.SynthesisInput(text=test_text)
        voice = texttospeech.VoiceSelectionParams(
            name=settings.speech.google_tts_voice,
            language_code=settings.speech.google_tts_voice[:5]
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=settings.speech.google_tts_speaking_rate,
            pitch=settings.speech.google_tts_pitch
        )
        
        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        
        # Save test audio
        output_file = "test_google_tts.mp3"
        with open(output_file, "wb") as f:
            f.write(response.audio_content)
        
        print(f"✅ Audio generated successfully!")
        print(f"   Output: {output_file}")
        print(f"   Size: {len(response.audio_content)} bytes")
        print(f"   Text: '{test_text}'")
        print()
        
        # Play the audio
        print("🔊 Playing audio...")
        import pygame
        pygame.mixer.init()
        pygame.mixer.music.load(output_file)
        pygame.mixer.music.play()
        
        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.1)
        
        print("✅ Playback complete!\n")
        
        # Cleanup
        try:
            os.remove(output_file)
            print(f"🧹 Cleaned up test file: {output_file}")
        except:
            pass
        
        print("\n" + "="*60)
        print("✅ Google TTS Test Complete - Everything Works!")
        print("="*60 + "\n")
        
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("\nInstall Google Cloud TTS:")
        print("   pip install google-cloud-texttospeech>=2.16.0")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("1. Verify credentials file exists and is valid")
        print("2. Check that Cloud Text-to-Speech API is enabled")
        print("3. Ensure service account has 'Cloud Text-to-Speech User' role")
        print("4. Review README_GOOGLE_CHIRP_TTS.md for setup instructions")


if __name__ == "__main__":
    asyncio.run(test_google_tts())
