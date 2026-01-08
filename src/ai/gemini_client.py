"""
Google Gemini AI Client
High-performance, free-tier friendly AI client with 15 RPM, 1M tokens/day
Supports automatic API key rotation on rate limit errors
"""
import asyncio
import json
import logging
from typing import Dict, List, Optional, Any
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GeminiClient:
    """
    Google Gemini API client for context-aware command processing
    Optimized for structured JSON responses with function calling
    Supports automatic API key rotation on rate limit errors
    """
    
    def __init__(self):
        self.settings = get_settings()
        
        # Collect all available API keys (primary + numbered)
        self.api_keys: List[str] = []
        
        # Add primary API key first (if set)
        if self.settings.gemini.api_key:
            self.api_keys.append(self.settings.gemini.api_key)
        
        # Add numbered API keys (for rotation)
        if self.settings.gemini.api_key_1:
            self.api_keys.append(self.settings.gemini.api_key_1)
        if self.settings.gemini.api_key_2:
            self.api_keys.append(self.settings.gemini.api_key_2)
        if self.settings.gemini.api_key_3:
            self.api_keys.append(self.settings.gemini.api_key_3)
        
        if not self.api_keys:
            raise ValueError("No Gemini API keys configured (GEMINI_API_KEY or GEMINI_API_KEY_1/2/3)")
        
        # Track current API key index (will be loaded from Redis if available)
        self.current_key_index = 0
        self.key_rotated = False  # Track if we've rotated keys in this session
        self.initial_key_index = 0  # Track the key we started with
        
        # Initialize with first key (will be updated if Redis has a saved working key)
        self._configure_client()
        
        logger.info(f"Gemini client initialized with model: {self.settings.gemini.model}, {len(self.api_keys)} API key(s) available")
    
    async def initialize(self):
        """Async initialization to load working key from Redis"""
        working_index = await self._load_working_key_index()
        if working_index is not None:
            self.current_key_index = working_index
            self.initial_key_index = working_index
            self._configure_client()
            logger.info(f"Using saved working API key: {self.current_key_index + 1}")
    
    def _configure_client(self):
        """Configure genai with current API key and recreate models"""
        current_key = self.api_keys[self.current_key_index]
        genai.configure(api_key=current_key)
        
        # Reinitialize models with current API key
        self.model_json = genai.GenerativeModel(
            model_name=self.settings.gemini.model,
            generation_config={
                "temperature": self.settings.gemini.temperature,
                "max_output_tokens": self.settings.gemini.max_tokens,
                "response_mime_type": "application/json",
                "top_p": 0.95,  # Faster, more focused responses
                "top_k": 40,
            }
        )
        self.model_text = genai.GenerativeModel(
            model_name=self.settings.gemini.model,
            generation_config={
                "temperature": self.settings.gemini.temperature,
                "max_output_tokens": self.settings.gemini.max_tokens,
                "top_p": 0.95,
                "top_k": 40,
            }
        )
    
    def _is_rate_limit_error(self, error: Exception) -> bool:
        """Check if error is a rate limit/quota error"""
        error_str = str(error).lower()
        error_type = type(error).__name__
        
        # Check for ResourceExhausted (rate limit) or InvalidArgument (bad key)
        if isinstance(error, (google_exceptions.ResourceExhausted, google_exceptions.InvalidArgument)):
            return True
            
        # Check error message for rate limit indicators OR invalid key indicators
        rate_limit_indicators = [
            "resource exhausted",
            "rate limit",
            "quota exceeded",
            "quota limit",
            "429",
            "too many requests",
            "api key not valid",
            "api key expired",
            "400"
        ]
        
        return any(indicator in error_str for indicator in rate_limit_indicators)
    
    def _rotate_api_key(self) -> bool:
        """Rotate to next available API key"""
        if len(self.api_keys) <= 1:
            logger.warning("Only one API key available, cannot rotate")
            return False
        
        # Move to next key
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        self._configure_client()
        self.key_rotated = True
        
        logger.info(f"Rotated to API key {self.current_key_index + 1} of {len(self.api_keys)}")
        return True
    
    async def _load_working_key_index(self) -> Optional[int]:
        """Load the last working API key index from Redis"""
        try:
            from src.database.redis_client import get_redis_client
            redis = await get_redis_client()
            saved_index = await redis.get("gemini:working_key_index")
            if saved_index:
                index = int(saved_index)
                if 0 <= index < len(self.api_keys):
                    logger.info(f"Loaded working API key index from Redis: {index + 1}")
                    return index
        except Exception as e:
            logger.debug(f"Could not load working key index from Redis: {e}")
        return None
    
    async def _save_working_key_index(self, index: int):
        """Save the working API key index to Redis"""
        try:
            from src.database.redis_client import get_redis_client
            redis = await get_redis_client()
            # Save with no expiration (persist until changed)
            await redis.set("gemini:working_key_index", str(index))
            logger.debug(f"Saved working API key index to Redis: {index + 1}")
        except Exception as e:
            logger.debug(f"Could not save working key index to Redis: {e}")
    
    async def _announce_key_rotation(self):
        """Announce API key rotation via TTS"""
        try:
            from src.speech.tts import get_tts_engine
            tts = get_tts_engine()
            message = "Boss! I detected an issue with my backend server API, so I've automatically switched to a new one to keep things running smoothly."
            await tts.speak(message)
            logger.info("Announced API key rotation via TTS")
        except Exception as e:
            logger.error(f"Failed to announce key rotation via TTS: {e}")
    
    async def chat(self, messages: List[Dict[str, str]], use_json_format: bool = True) -> Optional[Dict[str, Any]]:
        """
        Send chat request to Gemini API with context awareness
        Automatically rotates API keys on rate limit errors
        
        Args:
            messages: List of message dicts with 'role' and 'content'
                     Format: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        
        Returns:
            Parsed JSON response with intent, commands, and response text
        """
        # Track if we've rotated for this request
        rotated_this_request = False
        max_retries = len(self.api_keys)  # Try all available keys
        
        for attempt in range(max_retries):
            try:
                # Extract system prompt and user messages
                system_prompts = []
                conversation = []
                
                for msg in messages:
                    if msg["role"] == "system":
                        system_prompts.append(msg["content"])
                    elif msg["role"] == "user":
                        conversation.append({"role": "user", "parts": [msg["content"]]})
                    elif msg["role"] == "assistant":
                        conversation.append({"role": "model", "parts": [msg["content"]]})
                
                # Get the last user message
                if not conversation:
                    logger.error("No user messages found in conversation")
                    return None
                
                user_message = conversation[-1]["parts"][0]
                
                logger.debug(f"Sending request to Gemini API (key {self.current_key_index + 1}/{len(self.api_keys)}): {user_message[:100]}...")
                
                # Generate response - use appropriate model based on format
                model = self.model_json if use_json_format else self.model_text
                
                # Combine all system prompts
                full_system_prompt = "\n\n".join(system_prompts)
                
                if use_json_format:
                    full_prompt = f"{full_system_prompt}\n\nUser: {user_message}\n\nRespond with valid JSON only."
                else:
                    full_prompt = f"{full_system_prompt}\n\nUser: {user_message}"
                
                response = model.generate_content(full_prompt)
                
                # If not using JSON format, return plain text wrapped in expected dict format
                if not use_json_format:
                    result = {
                        "response": response.text.strip(),
                        "intent": "summary",
                        "commands": [],
                        "is_followup": False,
                        "update_context": False
                    }
                else:
                    # Parse JSON response
                    result = self._parse_json_response(response.text)
                
                # If we successfully got a response after rotating, save the working key and announce
                if result and rotated_this_request:
                    # Save the working key index to Redis as the new default
                    await self._save_working_key_index(self.current_key_index)
                    # Announce rotation in background (don't wait)
                    asyncio.create_task(self._announce_key_rotation())
                elif result and self.current_key_index != self.initial_key_index:
                    # If we're using a different key than we started with, save it
                    await self._save_working_key_index(self.current_key_index)
                
                if result:
                    logger.info(f"Gemini response: intent={result.get('intent')}, commands={len(result.get('commands', []))}")
                    return result
                else:
                    logger.error("Failed to parse Gemini response")
                    return None
                    
            except Exception as e:
                # Check if this is a rate limit error
                if self._is_rate_limit_error(e):
                    logger.warning(f"Rate limit error detected (attempt {attempt + 1}/{max_retries}): {e}")
                    
                    # Try to rotate to next key
                    if self._rotate_api_key():
                        rotated_this_request = True
                        logger.info(f"Retrying with new API key (key {self.current_key_index + 1})")
                        continue  # Retry with new key
                    else:
                        logger.error("Cannot rotate API key, all keys may be exhausted")
                        return None
                else:
                    # Not a rate limit error, log and return
                    logger.error(f"Error in Gemini chat (non-rate-limit): {e}", exc_info=True)
                    return None
        
        # If we exhausted all retries
        logger.error(f"Failed after {max_retries} attempts with all available API keys")
        return None
    
    def _parse_json_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Parse JSON response from Gemini"""
        try:
            # Clean the response text
            text = response_text.strip()
            
            # Remove markdown code blocks if present
            if text.startswith("```json"):
                text = text[7:]  # Remove ```json
            if text.startswith("```"):
                text = text[3:]  # Remove ```
            if text.endswith("```"):
                text = text[:-3]  # Remove ```
            
            text = text.strip()
            
            # Parse JSON
            parsed = json.loads(text)
            
            # Validate required fields
            if not isinstance(parsed, dict):
                logger.error("Response is not a JSON object")
                return None
            
            # Ensure all required fields exist
            response = {
                "intent": parsed.get("intent", "unknown"),
                "commands": parsed.get("commands", []),
                "response": parsed.get("response", "Done"),
                "update_context": parsed.get("update_context", True),
                "expecting_followup": parsed.get("expecting_followup", False)
            }
            
            return response
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Gemini: {e}")
            logger.error(f"Response text: {response_text[:500]}")
            return None
        except Exception as e:
            logger.error(f"Error parsing Gemini response: {e}")
            return None


# Global instance
_gemini_client: Optional[GeminiClient] = None


async def get_gemini_client() -> GeminiClient:
    """Get or create global Gemini client"""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = GeminiClient()
        # Load working key from Redis if available
        await _gemini_client.initialize()
    return _gemini_client


async def close_gemini_client():
    """Close global Gemini client"""
    global _gemini_client
    if _gemini_client:
        _gemini_client = None

