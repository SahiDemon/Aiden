import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from src.media.browser_media_controller import BrowserMediaController

async def test_direct_playback():
    controller = BrowserMediaController()
    
    print("Testing direct playback on YouTube Music (should use ytmusicapi)...")
    # This query should return a specific song
    success, response = await controller.control("play_track", target="youtube_music", query="Alan Walker faded")
    print(f"Success: {success}")
    print(f"Response: {response}")
    
    # Check if the response message indicates direct playback
    if "Playing" in response.get("message", "") and "YouTube Music" in response.get("message", ""):
        print("PASS: Direct playback triggered.")
    else:
        print("FAIL: Direct playback NOT triggered (might have fallen back to search).")

if __name__ == "__main__":
    asyncio.run(test_direct_playback())
