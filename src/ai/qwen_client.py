"""
Qwen Cloud AI Client
Handles intelligent command processing with context awareness
Uses Alibaba Cloud's Qwen API for natural language understanding
"""
import json
import hashlib
import logging
from typing import Dict, Any, List, Optional
import httpx
import yaml
from pathlib import Path

from src.utils.config import get_settings
from src.utils.logger import get_logger
from src.database.redis_client import get_redis_client

logger = get_logger(__name__)


class GroqClient:
    """
    Qwen Cloud API client for context-aware command processing
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=self.settings.qwen.timeout)
        self.system_prompt = self._load_system_prompt()
        
    def _load_system_prompt(self) -> str:
        """Load system prompt from prompts.yaml"""
        try:
            prompts_file = Path("config/prompts.yaml")
            if prompts_file.exists():
                with open(prompts_file, 'r', encoding='utf-8') as f:
                    prompts = yaml.safe_load(f)
                    return prompts.get("system_prompt", "")
            else:
                logger.warning("prompts.yaml not found, using default prompt")
                return self._get_default_prompt()
        except Exception as e:
            logger.error(f"Error loading prompts.yaml: {e}")
            return self._get_default_prompt()
    
    def _get_default_prompt(self) -> str:
        """Default system prompt if file not found"""
        return """You are Aiden, an intelligent Windows assistant.
        Analyze user messages and return structured JSON responses with commands to execute.
        Always return valid JSON in format: {"is_followup": bool, "intent": str, "commands": [...], "response": str, "update_context": bool}"""
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send chat request to Qwen API with context awareness
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            context: Conversation context (history, entities, etc.)
            
        Returns:
            Parsed command structure
        """
        try:
            # Check cache first
            redis = await get_redis_client()
            user_message = messages[-1]["content"] if messages else ""
            context_hash = self._hash_context(context)
            
            cached_response = await redis.get_llm_response(user_message, context_hash)
            if cached_response:
                logger.info("Using cached LLM response")
                return cached_response
            
            # Build request payload
            payload = {
                "model": self.settings.qwen.model,
                "input": {
                    "messages": messages
                },
                "parameters": {
                    "max_tokens": self.settings.qwen.max_tokens,
                    "temperature": self.settings.qwen.temperature,
                    "result_format": "message"  # Get structured message format
                }
            }
            
            # Make API request
            headers = {
                "Authorization": f"Bearer {self.settings.qwen.api_key}",
                "Content-Type": "application/json"
            }
            
            logger.debug(f"Sending request to Qwen API: {user_message[:100]}...")
            
            response = await self.client.post(
                self.settings.qwen.api_url,
                json=payload,
                headers=headers
            )
            
            response.raise_for_status()
            result = response.json()
            
            # Extract message from response
            output = result.get("output", {})
            message_content = output.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Parse JSON response
            parsed_response = self._parse_response(message_content, user_message)
            
            # Cache response
            await redis.cache_llm_response(user_message, context_hash, parsed_response)
            
            return parsed_response
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Qwen API HTTP error: {e.response.status_code} - {e.response.text}")
            return self._fallback_response(user_message, "API error")
        except httpx.RequestError as e:
            logger.error(f"Qwen API request error: {e}")
            return self._fallback_response(user_message, "Connection error")
        except Exception as e:
            logger.error(f"Error in Qwen chat: {e}", exc_info=True)
            return self._fallback_response(user_message, str(e))
    
    def _parse_response(self, content: str, original_query: str) -> Dict[str, Any]:
        """Parse JSON response from Qwen"""
        try:
            # Clean content - remove markdown code blocks if present
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            # Parse JSON
            parsed = json.loads(content)
            
            # Validate required fields
            if "intent" not in parsed:
                parsed["intent"] = "command"
            if "commands" not in parsed:
                parsed["commands"] = []
            if "response" not in parsed:
                parsed["response"] = "Processing your request"
            if "is_followup" not in parsed:
                parsed["is_followup"] = False
            if "update_context" not in parsed:
                parsed["update_context"] = True
            
            return parsed
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Qwen: {e}")
            logger.error(f"Content was: {content[:500]}")
            
            # Try to extract information from text response
            return self._extract_from_text(content, original_query)
    
    def _extract_from_text(self, text: str, original_query: str) -> Dict[str, Any]:
        """Extract intent from plain text response as fallback"""
        text_lower = text.lower()
        query_lower = original_query.lower()
        
        # Detect greetings
        if any(word in query_lower for word in ["hi", "hello", "hey", "good morning", "good afternoon"]):
            return {
                "is_followup": False,
                "intent": "greeting",
                "commands": [],
                "response": f"Hey! How can I help you, {self.settings.app.user_name}?",
                "update_context": True,
                "expecting_followup": True
            }
        
        # Detect app launch
        if any(word in query_lower for word in ["open", "launch", "start", "run"]):
            app_name = self._extract_app_name(query_lower)
            return {
                "is_followup": False,
                "intent": "command",
                "commands": [{"type": "launch_app", "params": {"name": app_name}}],
                "response": f"Opening {app_name}",
                "update_context": True,
                "expecting_followup": False
            }
        
        # Default fallback
        return {
            "is_followup": False,
            "intent": "question",
            "commands": [],
            "response": text if text else "I'm not sure how to help with that",
            "update_context": False,
            "expecting_followup": False
        }
    
    def _extract_app_name(self, query: str) -> str:
        """Extract app name from query"""
        words = query.split()
        keywords = ["open", "launch", "start", "run"]
        
        for i, word in enumerate(words):
            if word in keywords and i + 1 < len(words):
                return words[i + 1]
        
        return "application"
    
    def _fallback_response(self, query: str, error: str) -> Dict[str, Any]:
        """Generate fallback response when API fails"""
        logger.warning(f"Using fallback response due to: {error}")
        
        return {
            "is_followup": False,
            "intent": "error",
            "commands": [],
            "response": f"I'm having trouble processing that right now. Could you try again?",
            "update_context": False,
            "expecting_followup": False,
            "error": error
        }
    
    def _hash_context(self, context: Optional[Dict[str, Any]]) -> str:
        """Create hash of context for caching"""
        if not context:
            return "no_context"
        
        # Use relevant context fields for hash
        context_str = json.dumps({
            "last_intent": context.get("last_intent"),
            "last_entities": context.get("last_entities"),
            "expecting_followup": context.get("expecting_followup")
        }, sort_keys=True)
        
        return hashlib.md5(context_str.encode()).hexdigest()
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Global client instance
_qwen_client: Optional[QwenClient] = None


async def get_qwen_client() -> QwenClient:
    """Get or create global Qwen client"""
    global _qwen_client
    if _qwen_client is None:
        _qwen_client = QwenClient()
    return _qwen_client


async def close_qwen_client():
    """Close global Qwen client"""
    global _qwen_client
    if _qwen_client:
        await _qwen_client.close()
        _qwen_client = None

