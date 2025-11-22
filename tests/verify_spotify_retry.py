import asyncio
import sys
import os
import logging

# Add project root to path
sys.path.append(os.getcwd())

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO)

from src.media.media_router import MediaRouter

async def test_spotify_retry():
    router = MediaRouter()
    
    print("Testing 'play_liked_songs' with retry logic...")
    # This assumes Spotify might be closed or not active.
    # If it's already active, it should just work immediately.
    # If closed, it should launch and wait.
    
    success, response = await router.handle_media_command(
        action="play_liked_songs",
        target="spotify"
    )
    
    print(f"Success: {success}")
    print(f"Response: {response}")
    
    if response.get("message") == "Playing your Liked Songs on Spotify.":
        print("PASS: Action handled correctly.")
    else:
        print(f"FAIL or UNKNOWN: {response}")

if __name__ == "__main__":
    asyncio.run(test_spotify_retry())
