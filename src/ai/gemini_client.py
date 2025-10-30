"""
Google Gemini AI Client
High-performance, free-tier friendly AI client with 15 RPM, 1M tokens/day
"""
import json
import logging
from typing import Dict, List, Optional, Any
import google.generativeai as genai

from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GeminiClient:
    """
    Google Gemini API client for context-aware command processing
    Optimized for structured JSON responses with function calling
    """
    
    def __init__(self):
        self.settings = get_settings()
        
        # Configure Gemini
        genai.configure(api_key=self.settings.gemini.api_key)
        
        # Initialize model
        self.model = genai.GenerativeModel(
            model_name=self.settings.gemini.model,
            generation_config={
                "temperature": self.settings.gemini.temperature,
                "max_output_tokens": self.settings.gemini.max_tokens,
                "response_mime_type": "application/json",
                "top_p": 0.95,  # Faster, more focused responses
                "top_k": 40,
            }
        )
        
        logger.info(f"Gemini client initialized with model: {self.settings.gemini.model}")
    
    async def chat(self, messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        """
        Send chat request to Gemini API with context awareness
        
        Args:
            messages: List of message dicts with 'role' and 'content'
                     Format: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        
        Returns:
            Parsed JSON response with intent, commands, and response text
        """
        try:
            # Extract system prompt and user messages
            system_prompt = ""
            conversation = []
            
            for msg in messages:
                if msg["role"] == "system":
                    system_prompt = msg["content"]
                elif msg["role"] == "user":
                    conversation.append({"role": "user", "parts": [msg["content"]]})
                elif msg["role"] == "assistant":
                    conversation.append({"role": "model", "parts": [msg["content"]]})
            
            # Get the last user message
            if not conversation:
                logger.error("No user messages found in conversation")
                return None
            
            user_message = conversation[-1]["parts"][0]
            
            # Build the full prompt with system instructions
            full_prompt = f"{system_prompt}\n\nUser: {user_message}\n\nRespond with valid JSON only."
            
            logger.debug(f"Sending request to Gemini API: {user_message[:100]}...")
            
            # Generate response
            response = self.model.generate_content(full_prompt)
            
            # Parse JSON response
            parsed_response = self._parse_json_response(response.text)
            
            if parsed_response:
                logger.info(f"Gemini response: intent={parsed_response.get('intent')}, commands={len(parsed_response.get('commands', []))}")
                return parsed_response
            else:
                logger.error("Failed to parse Gemini response")
                return None
                
        except Exception as e:
            logger.error(f"Error in Gemini chat: {e}", exc_info=True)
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
    return _gemini_client


async def close_gemini_client():
    """Close global Gemini client"""
    global _gemini_client
    if _gemini_client:
        _gemini_client = None

