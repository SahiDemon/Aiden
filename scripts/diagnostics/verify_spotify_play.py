import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from src.media.media_router import MediaRouter

async def test_spotify_play_generic():
    router = MediaRouter()
    
    print("Testing generic 'play' action on Spotify (should play Liked Songs)...")
    success, response = await router.handle_media_command(
        action="play",
        target="spotify"
    )
    
    print(f"Success: {success}")
    print(f"Response: {response}")
    
    if "Starting Spotify playback" in response.get("message", "") or "Resuming your music" in response.get("message", ""):
        print("PASS: Generic 'play' triggered playback.")
    else:
        print("FAIL: Generic 'play' did NOT trigger playback.")

    print("\nTesting 'resume' action on Spotify (should just resume)...")
    success, response = await router.handle_media_command(
        action="resume",
        target="spotify"
    )
    print(f"Success: {success}")
    print(f"Response: {response}")
    
    if "resumed" in response.get("message", "").lower():
        print("PASS: 'resume' triggered resume.")
    else:
        print("FAIL: 'resume' did NOT trigger resume.")

if __name__ == "__main__":
    asyncio.run(test_spotify_play_generic())
