"""
WebSocket broadcast utility
Allows broadcasting updates without circular dependencies
"""
import asyncio
from typing import Dict, Any, Optional, Callable
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Global broadcast callback
_broadcast_callback: Optional[Callable] = None


def set_broadcast_callback(callback: Callable):
    """Set the broadcast callback function"""
    global _broadcast_callback
    _broadcast_callback = callback
    logger.info("WebSocket broadcast callback configured")


async def broadcast_voice_status(status: str, speaking: bool = False):
    """Broadcast voice activity status to dashboard"""
    if _broadcast_callback:
        try:
            logger.debug(f"Broadcasting voice status: {status}, speaking={speaking}")
            await _broadcast_callback("voice_activity", {
                "status": status,
                "speaking": speaking
            })
        except Exception as e:
            logger.error(f"Failed to broadcast voice status: {e}")
    else:
        logger.warning("Broadcast callback not set - cannot send voice status")


async def broadcast_message(message_type: str, data: Dict[str, Any]):
    """Broadcast generic message to dashboard"""
    if _broadcast_callback:
        try:
            logger.info(f"Broadcasting message: type={message_type}, data={data}")
            await _broadcast_callback(message_type, data)
        except Exception as e:
            logger.error(f"Failed to broadcast message: {e}")
    else:
        logger.warning(f"Broadcast callback not set - cannot send {message_type}")

