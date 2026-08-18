# Google Chirp 3 HD TTS Setup Guide

## Overview
Aiden now supports Google Cloud Text-to-Speech with **Chirp 3 HD voices**, offering ultra-realistic and natural-sounding speech synthesis.

## Available Voices
- **en-US-Chirp-HD-F** - Chirp HD Female (default)
- **en-US-Chirp-HD-M** - Chirp HD Male
- **en-US-Chirp2-HD-F** - Chirp2 HD Female
- **en-US-Chirp2-HD-M** - Chirp2 HD Male
- **en-US-Studio-O** - Studio O (Neutral)
- **en-US-Studio-Q** - Studio Q (Neutral)

## Setup Instructions

### 1. Install Dependencies
```powershell
# Activate your virtual environment
.\.venv\Scripts\Activate.ps1

# Install the new Google Cloud TTS library
python -m pip install google-cloud-texttospeech>=2.16.0
```

### 2. Get Google Cloud Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **Cloud Text-to-Speech API**:
   - Navigate to "APIs & Services" > "Library"
   - Search for "Cloud Text-to-Speech API"
   - Click "Enable"
4. Create a service account:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "Service Account"
   - Fill in the details and click "Create"
   - Grant the "Cloud Text-to-Speech User" role
   - Click "Done"
5. Download the JSON key file:
   - Click on the service account you created
   - Go to "Keys" tab
   - Click "Add Key" > "Create new key"
   - Choose "JSON" format
   - Save the file (e.g., `google-tts-credentials.json`)

### 3. Configure Aiden

Add these settings to your `.env` file:

```env
# TTS Provider Configuration
SPEECH_TTS_PROVIDER=google

# Google TTS Settings
SPEECH_GOOGLE_TTS_CREDENTIALS_PATH=F:\path\to\google-tts-credentials.json
SPEECH_GOOGLE_TTS_VOICE=en-US-Chirp-HD-F
SPEECH_GOOGLE_TTS_PITCH=0.0
SPEECH_GOOGLE_TTS_SPEAKING_RATE=1.0
```

**Important**: Replace `F:\path\to\google-tts-credentials.json` with the actual path to your downloaded JSON credentials file.

### 4. Test the Setup

Restart Aiden and test:
```powershell
.\run_aiden.ps1
```

Try a voice command like "Hello Aiden" and listen to the response. The voice should now use Google Chirp 3 HD.

## Configuration Options

### TTS Provider
Switch between providers in `.env`:
- `SPEECH_TTS_PROVIDER=edge` - Microsoft Edge TTS (default, free)
- `SPEECH_TTS_PROVIDER=google` - Google Chirp 3 HD (requires credentials)
- `SPEECH_TTS_PROVIDER=offline` - Offline pyttsx3 (fallback)

### Google TTS Settings

#### Voice Selection
```env
SPEECH_GOOGLE_TTS_VOICE=en-US-Chirp2-HD-F
```

#### Speaking Rate (0.25 - 4.0)
Controls how fast the voice speaks:
```env
SPEECH_GOOGLE_TTS_SPEAKING_RATE=1.2  # 20% faster
SPEECH_GOOGLE_TTS_SPEAKING_RATE=0.8  # 20% slower
```

#### Pitch Adjustment (-20.0 to +20.0)
Adjusts voice pitch:
```env
SPEECH_GOOGLE_TTS_PITCH=2.0   # Slightly higher pitch
SPEECH_GOOGLE_TTS_PITCH=-2.0  # Slightly lower pitch
```

## Dashboard Configuration

You can also change TTS settings through the dashboard:

1. Open the dashboard at `http://localhost:5000`
2. Go to **Settings** > **Speech**
3. Select **TTS Provider**: Google Chirp 3 HD
4. Choose your preferred **Google Voice**
5. Adjust **Speaking Rate** and **Pitch** sliders
6. Click **Save Settings**

## Pricing

Google Cloud TTS has a free tier:
- **Free**: First 1 million characters per month (Standard voices)
- **Chirp HD voices**: $16.00 per 1 million characters

For typical usage, a few thousand characters per day:
- ~100 responses/day × 50 chars = 5,000 chars/day
- ~150,000 chars/month
- **Well within the free tier**

Check current pricing at [Google Cloud TTS Pricing](https://cloud.google.com/text-to-speech/pricing)

## Troubleshooting

### "Failed to initialize Google TTS client"
- **Check credentials path**: Ensure `SPEECH_GOOGLE_TTS_CREDENTIALS_PATH` points to the correct JSON file
- **Verify API is enabled**: Make sure Cloud Text-to-Speech API is enabled in your Google Cloud project
- **Check service account permissions**: Ensure the service account has "Cloud Text-to-Speech User" role

### "Google TTS authentication error"
- Verify the JSON credentials file is valid and not corrupted
- Ensure the service account has not been deleted or disabled

### "Google TTS quota exceeded"
- Check your usage in Google Cloud Console
- Consider using Edge TTS as a fallback: `SPEECH_TTS_PROVIDER=edge`

### Fallback Behavior
If Google TTS fails to initialize, Aiden automatically falls back to Microsoft Edge TTS.

## Comparison: Edge TTS vs Google Chirp 3 HD

| Feature | Edge TTS | Google Chirp 3 HD |
|---------|----------|-------------------|
| **Quality** | High | Ultra-realistic |
| **Cost** | Free | Free tier + paid |
| **Setup** | None | Requires credentials |
| **Voices** | 8 options | 6 HD options |
| **Natural Speech** | Good | Excellent |
| **Offline** | No | No |

## Next Steps

1. **Test different voices**: Try all Chirp 3 HD voices to find your favorite
2. **Adjust settings**: Fine-tune speaking rate and pitch for optimal experience
3. **Monitor usage**: Keep an eye on your Google Cloud usage dashboard
4. **Set spending limits**: Configure billing alerts in Google Cloud Console

Enjoy the ultra-realistic voice synthesis! 🎤✨
