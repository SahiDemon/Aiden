"""
Clear TTS Audio Cache
Run this after changing TTS providers to remove old cached audio
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.redis_client import get_redis_client
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def clear_tts_cache():
    """Clear all cached TTS audio from Redis"""
    print("\n" + "="*60)
    print("Clearing TTS Audio Cache")
    print("="*60 + "\n")
    
    try:
        redis = await get_redis_client()
        
        # Delete all keys matching tts_audio:*
        print("🔍 Searching for cached TTS audio...")
        
        # Get all TTS cache keys
        cursor = 0
        keys_deleted = 0
        
        while True:
            # Use SCAN to iterate through keys
            cursor, keys = await redis.client.scan(
                cursor=cursor,
                match="tts_audio:*",
                count=100
            )
            
            if keys:
                # Delete the keys
                deleted = await redis.client.delete(*keys)
                keys_deleted += deleted
                print(f"   Deleted {deleted} cached audio files...")
            
            if cursor == 0:
                break
        
        print(f"\n✅ Cache cleared successfully!")
        print(f"   Total items removed: {keys_deleted}")
        print("\n" + "="*60)
        print("All new responses will use the current TTS provider")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error clearing cache: {e}")
        print("\nMake sure:")
        print("1. Redis is running and accessible")
        print("2. REDIS_URL is correctly set in .env")


if __name__ == "__main__":
    asyncio.run(clear_tts_cache())
