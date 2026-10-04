"""
Prompts Loader
Centralized loading and caching of prompts.yaml for AI clients
"""
import threading
from pathlib import Path
from typing import Dict, Any, Optional
import yaml

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Module-level cache for prompts to avoid repeated file I/O
_prompts_cache: Optional[Dict[str, Any]] = None
_cache_lock = threading.Lock()


def load_prompts() -> Dict[str, Any]:
    """
    Load and cache prompts.yaml content.
    
    Returns cached value on subsequent calls, avoiding repeated file I/O.
    Thread-safe with proper locking to avoid race conditions.
    
    Returns:
        Dictionary containing prompts configuration
    """
    global _prompts_cache
    
    # Fast path: return cached value without lock
    if _prompts_cache is not None:
        return _prompts_cache
    
    # Slow path: acquire lock and load
    with _cache_lock:
        # Double-check pattern: another thread may have loaded while we waited
        if _prompts_cache is not None:
            return _prompts_cache
        
        try:
            prompts_file = Path("config/prompts.yaml")
            if prompts_file.exists():
                with open(prompts_file, 'r', encoding='utf-8') as f:
                    _prompts_cache = yaml.safe_load(f) or {}
                    logger.debug("Loaded and cached prompts.yaml")
                    return _prompts_cache
        except Exception as e:
            logger.error(f"Error loading prompts.yaml: {e}")
        
        _prompts_cache = {}
        return _prompts_cache


def get_system_prompt() -> str:
    """
    Get the system prompt for AI assistants.
    
    Returns:
        System prompt string or default if not found
    """
    prompts = load_prompts()
    return prompts.get("system_prompt", "You are Aiden, an intelligent Windows assistant.")


def get_enhancement_prompt() -> str:
    """
    Get the enhancement prompt template for ESP32 responses.
    
    Returns:
        Enhancement prompt template or empty string if not found
    """
    prompts = load_prompts()
    return prompts.get("enhancement_prompt", "")


def clear_cache():
    """Clear the prompts cache. Useful for testing or hot-reloading."""
    global _prompts_cache
    with _cache_lock:
        _prompts_cache = None
