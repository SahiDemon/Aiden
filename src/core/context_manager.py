"""
Context Manager
Manages conversation context using Redis for intelligent follow-up detection
"""
import asyncio
import uuid
import logging
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.database.redis_client import get_redis_client
from src.database.neon_client import get_db_client
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ContextManager:
    """
    Manages conversation context for intelligent follow-up detection
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.current_conversation_id: Optional[str] = None
        
    async def start_conversation(self, user_id: str = "default", mode: str = "voice") -> str:
        """
        Start new conversation and return conversation ID
        OPTIMIZED: Creates ID immediately, saves to DB in background
        
        Args:
            user_id: User identifier
            mode: Conversation mode (voice, text, hotkey)
            
        Returns:
            Conversation ID
        """
        try:
            # Generate ID immediately (no database delay)
            conversation_id = str(uuid.uuid4())
            self.current_conversation_id = conversation_id
            
            # Initialize context in Redis (fast, in-memory)
            redis = await get_redis_client()
            initial_context = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "mode": mode,
                "created_at": datetime.utcnow().isoformat(),
                "last_intent": None,
                "last_entities": [],
                "last_action": None,
                "expecting_followup": False,
                "history": []
            }
            
            await redis.save_context(conversation_id, initial_context)
            
            # Save to database in background (non-blocking)
            asyncio.create_task(self._save_conversation_to_db(conversation_id, user_id, mode))
            
            return conversation_id
            
        except Exception as e:
            logger.error(f"Error starting conversation: {e}")
            # Return fallback ID
            fallback_id = str(uuid.uuid4())
            self.current_conversation_id = fallback_id
            return fallback_id
    
    async def _save_conversation_to_db(self, conversation_id: str, user_id: str, mode: str):
        """Save conversation to database in background (non-blocking)"""
        try:
            db = await get_db_client()
            await db.create_conversation(user_id=user_id, mode=mode)
        except Exception as e:
            logger.debug(f"Background DB save failed (non-critical): {e}")
    
    async def _save_messages_to_db(self, conversation_id: str, user_message: str, ai_response: Dict[str, Any]):
        """Save messages to database in background (non-blocking)"""
        try:
            db = await get_db_client()
            await db.add_message(
                conversation_id=conversation_id,
                role="user",
                content=user_message,
                metadata={"intent": ai_response.get("intent")}
            )
            await db.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=ai_response.get("response", ""),
                metadata={"commands": ai_response.get("commands", [])}
            )
        except Exception as e:
            logger.debug(f"Background message save failed (non-critical): {e}")
    
    async def _end_conversation_in_db(self, conversation_id: str):
        """End conversation in database (background, non-blocking)"""
        try:
            db = await get_db_client()
            await db.end_conversation(conversation_id)
        except Exception as e:
            logger.debug(f"Background conversation end failed (non-critical): {e}")
    
    async def get_context(self, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get conversation context from Redis
        
        Args:
            conversation_id: Conversation ID (uses current if not specified)
            
        Returns:
            Context dictionary
        """
        conversation_id = conversation_id or self.current_conversation_id
        
        if not conversation_id:
            return self._empty_context()
        
        try:
            redis = await get_redis_client()
            context = await redis.get_context(conversation_id)
            
            if context:
                return context
            else:
                logger.warning(f"No context found for conversation {conversation_id}")
                return self._empty_context()
                
        except Exception as e:
            logger.error(f"Error getting context: {e}")
            return self._empty_context()
    
    async def update_context(
        self,
        user_message: str,
        ai_response: Dict[str, Any],
        conversation_id: Optional[str] = None
    ):
        """
        Update conversation context after interaction
        
        Args:
            user_message: User's message
            ai_response: AI's parsed response
            conversation_id: Conversation ID (uses current if not specified)
        """
        conversation_id = conversation_id or self.current_conversation_id
        
        if not conversation_id:
            logger.warning("No active conversation to update")
            return
        
        try:
            # Get current context
            context = await self.get_context(conversation_id)
            
            # Update history (keep last 10 messages)
            context["history"].append({"role": "user", "content": user_message})
            context["history"].append({"role": "assistant", "content": ai_response.get("response", "")})
            context["history"] = context["history"][-10:]  # Keep last 10 messages
            
            logger.info(f"[CONTEXT] Updated history: now has {len(context['history'])} messages")
            
            # Update context fields from AI response
            context["last_intent"] = ai_response.get("intent")
            context["expecting_followup"] = ai_response.get("expecting_followup", False)
            
            # Extract entities from commands
            entities = []
            for cmd in ai_response.get("commands", []):
                params = cmd.get("params", {})
                if "name" in params:
                    entities.append(params["name"])
                if "target" in params:
                    entities.append(params["target"])
            
            if entities:
                context["last_entities"] = entities
            
            # Update last action
            if ai_response.get("commands"):
                context["last_action"] = ai_response["commands"][0].get("type")
            
            # Save updated context to Redis (fast, blocking)
            redis = await get_redis_client()
            await redis.save_context(conversation_id, context)
            
            # Save to database in background (non-blocking)
            asyncio.create_task(self._save_messages_to_db(
                conversation_id, 
                user_message, 
                ai_response
            ))
            
            logger.debug(f"Updated context for conversation {conversation_id}")
            
        except Exception as e:
            logger.error(f"Error updating context: {e}")
    
    async def end_conversation(self, conversation_id: Optional[str] = None):
        """
        End conversation and cleanup
        
        Args:
            conversation_id: Conversation ID (uses current if not specified)
        """
        conversation_id = conversation_id or self.current_conversation_id
        
        if not conversation_id:
            return
        
        try:
            # Mark as ended in database (background, non-blocking)
            asyncio.create_task(self._end_conversation_in_db(conversation_id))
            
            # Keep context in Redis (will expire based on TTL)
            # This allows us to resume if needed
            
            if conversation_id == self.current_conversation_id:
                self.current_conversation_id = None
            
            logger.info(f"Ended conversation: {conversation_id}")
            
        except Exception as e:
            logger.error(f"Error ending conversation: {e}")
    
    async def clear_context(self, conversation_id: Optional[str] = None):
        """
        Clear conversation context from Redis
        
        Args:
            conversation_id: Conversation ID (uses current if not specified)
        """
        conversation_id = conversation_id or self.current_conversation_id
        
        if not conversation_id:
            return
        
        try:
            redis = await get_redis_client()
            await redis.delete_context(conversation_id)
            logger.info(f"Cleared context for conversation {conversation_id}")
            
        except Exception as e:
            logger.error(f"Error clearing context: {e}")
    
    async def get_conversation_history(
        self,
        conversation_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get conversation history from database
        
        Args:
            conversation_id: Conversation ID (uses current if not specified)
            limit: Maximum number of messages to retrieve
            
        Returns:
            List of message dictionaries
        """
        conversation_id = conversation_id or self.current_conversation_id
        
        if not conversation_id:
            return []
        
        try:
            db = await get_db_client()
            messages = await db.get_conversation_messages(conversation_id, limit=limit)
            return [msg.to_dict() for msg in messages]
            
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []
    
    def _empty_context(self) -> Dict[str, Any]:
        """Return empty context structure"""
        return {
            "conversation_id": None,
            "user_id": "default",
            "mode": "voice",
            "created_at": datetime.utcnow().isoformat(),
            "last_intent": None,
            "last_entities": [],
            "last_action": None,
            "expecting_followup": False,
            "history": []
        }
    
    async def is_followup(self, message: str, context: Dict[str, Any]) -> bool:
        """
        Determine if message is a follow-up based on context
        
        Args:
            message: User message
            context: Current conversation context
            
        Returns:
            True if this appears to be a follow-up message
        """
        message_lower = message.lower().strip()
        
        # Check if context expects follow-up
        if context.get("expecting_followup"):
            return True
        
        # Check for follow-up indicators
        followup_indicators = [
            "and ", "also ", "too ", "then ", "after that",
            "what about", "how about", "can you also"
        ]
        
        if any(indicator in message_lower for indicator in followup_indicators):
            return True
        
        # Check if message references previous entities
        last_entities = context.get("last_entities", [])
        if last_entities:
            for entity in last_entities:
                if entity.lower() in message_lower:
                    return True
        
        return False
    
    async def build_messages(self, user_text: str, context: Dict[str, Any], needs_context: List[str] = None) -> List[Dict[str, str]]:
        """
        Build messages list for AI including context
        
        Args:
            user_text: User's message
            context: Conversation context
            needs_context: List of context types needed (e.g., ["installed_apps", "running_processes"])
            
        Returns:
            List of message dictionaries for AI
        """
        messages = []
        
        # Load system prompt from prompts.yaml
        from pathlib import Path
        import yaml
        
        try:
            prompts_file = Path("config/prompts.yaml")
            if prompts_file.exists():
                with open(prompts_file, 'r', encoding='utf-8') as f:
                    prompts = yaml.safe_load(f)
                    system_prompt = prompts.get("system_prompt", "")
            else:
                system_prompt = "You are Aiden, an intelligent Windows assistant."
        except Exception as e:
            logger.error(f"Error loading prompts.yaml: {e}")
            system_prompt = "You are Aiden, an intelligent Windows assistant."
        
        # Get system context ONLY if AI requested it via needs_context
        system_context_str = ""
        
        if needs_context:
            logger.info(f"[CONTEXT] AI requested context: {needs_context}")
            try:
                from src.utils.system_context import get_system_context
                sys_ctx = get_system_context()
                ai_context = await sys_ctx.get_ai_context()
                
                system_context_str = "\n\n## AVAILABLE SYSTEM RESOURCES\n"
                
                if "installed_apps" in needs_context and ai_context.get("installed_apps"):
                    apps_list = ai_context["installed_apps"]
                    system_context_str += f"Installed Apps ({ai_context['total_apps']} total): "
                    system_context_str += ", ".join([app.split(" (")[0] for app in apps_list[:20]])
                    system_context_str += "\n"
                
                if "running_processes" in needs_context and ai_context.get("running_processes"):
                    procs_list = ai_context["running_processes"]
                    system_context_str += f"Running Processes ({ai_context['total_processes']} total): "
                    system_context_str += ", ".join(procs_list[:40])
                
                logger.debug(f"System context provided: {needs_context}")
            
            except Exception as e:
                logger.debug(f"Could not fetch system context: {e}")
        else:
            logger.debug(f"No system context requested for: {user_text[:50]}...")
        
        # Add system message from prompts.yaml + optional system context
        system_message = {
            "role": "system",
            "content": system_prompt + system_context_str
        }
        messages.append(system_message)
        
        # Add conversation history if available
        history = context.get("history", [])
        logger.info(f"[CONTEXT] History has {len(history)} messages")
        if history:
            # Add last 10 messages for context (5 exchanges)
            messages.extend(history[-10:])
            logger.info(f"[CONTEXT] Added {len(history[-10:])} history messages to AI context")
        else:
            logger.warning(f"[CONTEXT] No conversation history found for conversation {context.get('conversation_id')}")
        
        # Add current user message
        messages.append({"role": "user", "content": user_text})
        
        logger.info(f"[CONTEXT] Total messages being sent to AI: {len(messages)}")
        return messages


# Global context manager instance
_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """Get or create global context manager"""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager

