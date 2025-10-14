"""
Redis Client for Context Management and Caching
Handles conversation context, app paths cache, LLM response cache, and TTS audio cache
"""
import json
import hashlib
import logging
from typing import Optional, Dict, Any, List
from redis import asyncio as aioredis

from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class RedisClient:
    """Async Redis client for caching and context management"""
    
    def __init__(self):
        self.settings = get_settings()
        self.client: Optional[aioredis.Redis] = None
        self.binary_client: Optional[aioredis.Redis] = None  # For binary data like audio
        
    async def connect(self):
        """Initialize Redis connection"""
        try:
            # Main client for text data
            self.client = await aioredis.from_url(
                self.settings.redis.url,
                decode_responses=True,  # Decode text responses
                socket_timeout=self.settings.redis.socket_timeout,
                socket_connect_timeout=self.settings.redis.socket_connect_timeout
            )
            
            # Binary client for audio data
            self.binary_client = await aioredis.from_url(
                self.settings.redis.url,
                decode_responses=False,  # Keep binary data as bytes
                socket_timeout=self.settings.redis.socket_timeout,
                socket_connect_timeout=self.settings.redis.socket_connect_timeout
            )
            
            # Test connection
            await self.client.ping()
            logger.info("Connected to Redis successfully")
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def disconnect(self):
        """Close Redis connection"""
        if self.client:
            await self.client.close()
        if self.binary_client:
            await self.binary_client.close()
        logger.info("Disconnected from Redis")
    
    # ===== Context Management =====
    
    async def save_context(
        self,
        conversation_id: str,
        context: Dict[str, Any],
        ttl: Optional[int] = None
    ):
        """
        Save conversation context to Redis
        
        Args:
            conversation_id: Unique conversation ID
            context: Context dictionary containing history, entities, etc.
            ttl: Time to live in seconds (default from config)
        """
        if not self.settings.cache.enable_caching:
            return
        
        try:
            key = f"conversation_context:{conversation_id}"
            ttl = ttl or self.settings.cache.ttl_context
            
            await self.client.setex(
                key,
                ttl,
                json.dumps(context, default=str)
            )
            logger.debug(f"Saved context for conversation {conversation_id}")
            
        except Exception as e:
            logger.error(f"Error saving context: {e}")
    
    async def get_context(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Get conversation context from Redis
        
        Args:
            conversation_id: Unique conversation ID
            
        Returns:
            Context dictionary or None if not found
        """
        if not self.settings.cache.enable_caching:
            return None
        
        try:
            key = f"conversation_context:{conversation_id}"
            data = await self.client.get(key)
            
            if data:
                return json.loads(data)
            return None
            
        except Exception as e:
            logger.error(f"Error getting context: {e}")
            return None
    
    async def delete_context(self, conversation_id: str):
        """Delete conversation context"""
        try:
            key = f"conversation_context:{conversation_id}"
            await self.client.delete(key)
            logger.debug(f"Deleted context for conversation {conversation_id}")
        except Exception as e:
            logger.error(f"Error deleting context: {e}")
    
    async def extend_context_ttl(self, conversation_id: str, ttl: Optional[int] = None):
        """Extend TTL for conversation context"""
        try:
            key = f"conversation_context:{conversation_id}"
            ttl = ttl or self.settings.cache.ttl_context
            await self.client.expire(key, ttl)
        except Exception as e:
            logger.error(f"Error extending context TTL: {e}")
    
    # ===== App Paths Cache =====
    
    async def cache_app_path(self, app_name: str, app_path: str):
        """Cache application executable path"""
        if not self.settings.cache.enable_caching:
            return
        
        try:
            key = f"app_path:{app_name.lower()}"
            ttl = self.settings.cache.ttl_app_paths
            
            await self.client.setex(key, ttl, app_path)
            logger.debug(f"Cached path for {app_name}: {app_path}")
            
        except Exception as e:
            logger.error(f"Error caching app path: {e}")
    
    async def get_app_path(self, app_name: str) -> Optional[str]:
        """Get cached application path"""
        if not self.settings.cache.enable_caching:
            return None
        
        try:
            key = f"app_path:{app_name.lower()}"
            path = await self.client.get(key)
            
            if path:
                logger.debug(f"Cache hit for app {app_name}: {path}")
            return path
            
        except Exception as e:
            logger.error(f"Error getting app path: {e}")
            return None
    
    async def clear_app_cache(self):
        """Clear all cached app paths"""
        try:
            pattern = "app_path:*"
            keys = []
            async for key in self.client.scan_iter(match=pattern):
                keys.append(key)
            
            if keys:
                await self.client.delete(*keys)
                logger.info(f"Cleared {len(keys)} app paths from cache")
                
        except Exception as e:
            logger.error(f"Error clearing app cache: {e}")
    
    # ===== LLM Response Cache =====
    
    async def cache_llm_response(
        self,
        query: str,
        context_hash: str,
        response: Dict[str, Any]
    ):
        """
        Cache LLM response for identical queries with same context
        
        Args:
            query: User query
            context_hash: Hash of context to ensure same context
            response: LLM response dictionary
        """
        if not self.settings.cache.enable_caching:
            return
        
        try:
            # Create cache key from query + context hash
            cache_input = f"{query}:{context_hash}"
            cache_key = hashlib.md5(cache_input.encode()).hexdigest()
            key = f"llm_response:{cache_key}"
            ttl = self.settings.cache.ttl_llm_response
            
            await self.client.setex(
                key,
                ttl,
                json.dumps(response, default=str)
            )
            logger.debug(f"Cached LLM response for query: {query[:50]}...")
            
        except Exception as e:
            logger.error(f"Error caching LLM response: {e}")
    
    async def get_llm_response(
        self,
        query: str,
        context_hash: str
    ) -> Optional[Dict[str, Any]]:
        """Get cached LLM response"""
        if not self.settings.cache.enable_caching:
            return None
        
        try:
            cache_input = f"{query}:{context_hash}"
            cache_key = hashlib.md5(cache_input.encode()).hexdigest()
            key = f"llm_response:{cache_key}"
            
            data = await self.client.get(key)
            if data:
                logger.debug(f"Cache hit for LLM query: {query[:50]}...")
                return json.loads(data)
            return None
            
        except Exception as e:
            logger.error(f"Error getting LLM response: {e}")
            return None
    
    # ===== TTS Audio Cache =====
    
    async def cache_tts_audio(self, text: str, audio_data: bytes):
        """Cache TTS generated audio"""
        if not self.settings.cache.enable_caching:
            return
        
        try:
            # Use MD5 hash of text as key
            text_hash = hashlib.md5(text.encode()).hexdigest()
            key = f"tts_audio:{text_hash}"
            ttl = self.settings.cache.ttl_tts_audio
            
            # Use binary client for audio data
            await self.binary_client.setex(key, ttl, audio_data)
            logger.debug(f"Cached TTS audio for text: {text[:50]}...")
            
        except Exception as e:
            logger.error(f"Error caching TTS audio: {e}")
    
    async def get_tts_audio(self, text: str) -> Optional[bytes]:
        """Get cached TTS audio"""
        if not self.settings.cache.enable_caching:
            return None
        
        try:
            text_hash = hashlib.md5(text.encode()).hexdigest()
            key = f"tts_audio:{text_hash}"
            
            # Use binary client to get audio data
            audio_data = await self.binary_client.get(key)
            if audio_data:
                logger.debug(f"Cache hit for TTS text: {text[:50]}...")
                return audio_data
            return None
            
        except Exception as e:
            logger.error(f"Error getting TTS audio: {e}")
            return None
    
    # ===== General Cache Operations =====
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set generic cache value"""
        try:
            if ttl:
                await self.client.setex(key, ttl, value)
            else:
                await self.client.set(key, value)
        except Exception as e:
            logger.error(f"Error setting cache key {key}: {e}")
    
    async def get(self, key: str) -> Optional[Any]:
        """Get generic cache value"""
        try:
            return await self.client.get(key)
        except Exception as e:
            logger.error(f"Error getting cache key {key}: {e}")
            return None
    
    async def delete(self, key: str):
        """Delete cache key"""
        try:
            await self.client.delete(key)
        except Exception as e:
            logger.error(f"Error deleting cache key {key}: {e}")
    
    async def clear_all(self):
        """Clear all cache (use with caution!)"""
        try:
            await self.client.flushdb()
            logger.warning("Cleared all Redis cache")
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            info = await self.client.info()
            return {
                "used_memory": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients"),
                "total_keys": await self.client.dbsize(),
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "hit_rate": (
                    info.get("keyspace_hits", 0) / 
                    max(info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0), 1)
                ) * 100
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {}


# Global client instance
_redis_client: Optional[RedisClient] = None


async def get_redis_client() -> RedisClient:
    """Get or create global Redis client"""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
        await _redis_client.connect()
    return _redis_client


async def close_redis_client():
    """Close global Redis client"""
    global _redis_client
    if _redis_client:
        await _redis_client.disconnect()
        _redis_client = None

