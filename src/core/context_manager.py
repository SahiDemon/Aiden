"""
Context Manager
Manages conversation context using Redis for intelligent follow-up detection
"""
import asyncio
import uuid
import logging
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

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
        # Summarization configuration
        self._summary_after_messages: int = 8  # when to start summarizing (earlier = less tokens)
        self._history_keep_after_summary: int = 6  # keep recent 3 exchanges (6 messages) after summarizing
        self._summary_max_chars: int = 600  # reduced cap for summary length
        self._pending_clarification_grace_seconds: int = max(
            5,
            int(self.settings.speech.pending_clarification_grace_seconds),
        )
        
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
                "pending_clarification": False,
                "pending_intent": None,
                "pending_slots": [],
                "pending_question": "",
                "pending_expires_at": None,
                "history": [],
                "summary": ""
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
            await db.create_conversation(
                conversation_id=conversation_id,
                user_id=user_id,
                mode=mode
            )
        except Exception as e:
            logger.debug(f"Background DB save failed (non-critical): {e}")
    
    async def _save_messages_to_db(self, conversation_id: str, user_message: str, ai_response: Dict[str, Any]):
        """Save messages to database in background (non-blocking)"""
        try:
            db = await get_db_client()
            await db.ensure_conversation_exists(conversation_id=conversation_id)
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
                # Auto-clear stale pending clarification state after grace window expires.
                if context.get("pending_clarification") and not self._is_pending_clarification_active(context):
                    self._clear_pending_clarification(context)
                    await redis.save_context(conversation_id, context)
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
            
            # Update history and apply summarization when long
            context["history"].append({"role": "user", "content": user_message})
            context["history"].append({"role": "assistant", "content": ai_response.get("response", "")})

            # If history exceeds threshold, summarize older part and keep recent tail
            if len(context["history"]) >= self._summary_after_messages:
                logger.info(f"[CONTEXT] History exceeded threshold ({self._summary_after_messages}), triggering summarization...")
                # Split into older block and recent tail we want to keep verbatim
                tail = context["history"][-self._history_keep_after_summary:]
                head = context["history"][:-self._history_keep_after_summary]
                logger.debug(f"[CONTEXT] Summarizing {len(head)} messages, keeping {len(tail)} recent")
                # Build/update summary from head and any existing summary
                existing_summary = context.get("summary", "") or ""
                try:
                    new_summary = await self._ai_summarize(head, existing_summary)
                    if not new_summary:
                        logger.debug("[CONTEXT] AI summarization returned empty, using heuristic fallback")
                        new_summary = self._summarize_messages(head, existing_summary)
                except Exception as e:
                    logger.debug(f"[CONTEXT] AI summarization failed: {e}, using heuristic fallback")
                    new_summary = self._summarize_messages(head, existing_summary)
                # Store summary and shrink history to tail only
                context["summary"] = new_summary[: self._summary_max_chars]
                context["history"] = tail
                logger.info(f"[CONTEXT] Summarization complete: summary length={len(context['summary'])}, history now={len(context['history'])} messages")

            # Ensure hard cap to avoid runaway growth (defensive: max 6 messages = 3 exchanges)
            context["history"] = context["history"][-self._history_keep_after_summary:]
            
            logger.info(f"[CONTEXT] Updated history: now has {len(context['history'])} messages")
            
            # Update context fields from AI response
            context["last_intent"] = ai_response.get("intent")
            context["expecting_followup"] = ai_response.get("expecting_followup", False)

            # Track pending clarification separately from compressed summary/history.
            # This state is used to keep execution decisions safe across turns.
            if context["expecting_followup"]:
                context["pending_clarification"] = True
                context["pending_intent"] = ai_response.get("intent")
                context["pending_slots"] = self._infer_pending_slots(ai_response.get("response", ""))
                context["pending_question"] = ai_response.get("response", "")
                context["pending_expires_at"] = self._next_pending_expiry_iso()
            else:
                self._clear_pending_clarification(context)
            
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
            
    async def inject_assistant_message(
        self,
        message: str,
        expecting_followup: bool = False,
        conversation_id: Optional[str] = None
    ):
        """
        Inject an assistant message directly into the context
        Useful for proactive alerts (like UPS) to ensure the AI has context
        for the user's response.
        """
        conversation_id = conversation_id or self.current_conversation_id
        
        if not conversation_id:
            conversation_id = await self.start_conversation(mode="voice")
            
        try:
            # Get current context
            context = await self.get_context(conversation_id)
            
            # Append message to history
            context["history"].append({"role": "assistant", "content": message})
            
            # Apply summarization if needed
            if len(context["history"]) >= self._summary_after_messages:
                logger.info(f"[CONTEXT] History exceeded threshold, triggering summarization...")
                tail = context["history"][-self._history_keep_after_summary:]
                head = context["history"][:-self._history_keep_after_summary]
                existing_summary = context.get("summary", "") or ""
                try:
                    new_summary = await self._ai_summarize(head, existing_summary)
                    if not new_summary:
                        new_summary = self._summarize_messages(head, existing_summary)
                except Exception as e:
                    new_summary = self._summarize_messages(head, existing_summary)
                context["summary"] = new_summary[: self._summary_max_chars]
                context["history"] = tail

            context["history"] = context["history"][-self._history_keep_after_summary:]
            context["expecting_followup"] = expecting_followup

            if expecting_followup:
                context["pending_clarification"] = True
                context["pending_question"] = message
                context["pending_slots"] = self._infer_pending_slots(message)
                context["pending_expires_at"] = self._next_pending_expiry_iso()
            else:
                self._clear_pending_clarification(context)
            
            # Save to redis
            redis = await get_redis_client()
            await redis.save_context(conversation_id, context)
            
            # Save to db in background
            try:
                db = await get_db_client()
                async def _save_injected_message():
                    await db.ensure_conversation_exists(conversation_id=conversation_id)
                    await db.add_message(
                        conversation_id=conversation_id,
                        role="assistant",
                        content=message,
                        metadata={"injected": True}
                    )

                asyncio.create_task(_save_injected_message())
            except Exception as e:
                logger.debug(f"Background save failed: {e}")
                
            logger.debug(f"Injected assistant message to conversation {conversation_id}")
            
        except Exception as e:
            logger.error(f"Error injecting assistant message: {e}")
            
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
            "pending_clarification": False,
            "pending_intent": None,
            "pending_slots": [],
            "pending_question": "",
            "pending_expires_at": None,
            "history": []
        }

    async def refresh_pending_clarification_grace(self, conversation_id: Optional[str] = None) -> bool:
        """Extend pending clarification grace so next hotkey can complete the slot-only reply."""
        conversation_id = conversation_id or self.current_conversation_id
        if not conversation_id:
            return False

        try:
            context = await self.get_context(conversation_id)
            if not context.get("pending_clarification"):
                return False

            context["pending_expires_at"] = self._next_pending_expiry_iso()
            redis = await get_redis_client()
            await redis.save_context(conversation_id, context)
            return True
        except Exception as e:
            logger.debug(f"Could not refresh pending clarification grace: {e}")
            return False
    
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
        
        from src.utils.prompt_loader import get_prompt
        system_prompt = get_prompt("system_prompt", "You are Aiden, an intelligent Windows assistant.")
        
        # Get system context ONLY if AI requested it via needs_context
        system_context_str = ""
        
        if needs_context:
            logger.info(f"[CONTEXT] AI requested context: {needs_context}")
            try:
                from src.utils.system_context import get_system_context
                sys_ctx = get_system_context()
                system_context_str = "\n\n## RELEVANT SYSTEM CONTEXT\n"
                
                query_hint = self._extract_query_from_text(user_text, context)
                if not query_hint and context.get("expecting_followup"):
                    t = (user_text or "").strip()
                    if 2 < len(t) < 160:
                        query_hint = t.lower()
                apps_section = ""
                proc_section = ""
                proc_list: List[str] = []
                
                if "installed_apps" in needs_context:
                    if query_hint:
                        app_info = await sys_ctx.find_app(query_hint)
                        if app_info:
                            apps_section += "Installed app match: "
                            display_name = app_info.get("display_name") or app_info.get("name") or query_hint
                            exe_path = app_info.get("exe_path", "")
                            install_path = app_info.get("install_path", "")
                            steam_appid = None
                            try:
                                from src.execution.app_launcher import get_app_launcher
                                launcher = get_app_launcher()
                                steam_appid = await launcher._resolve_steam_appid(query_hint.lower(), install_path)
                            except Exception:
                                steam_appid = None
                            appid_str = f" | steam_appid: {steam_appid}" if steam_appid else ""
                            apps_section += f"{display_name} | exe: {exe_path} | path: {install_path}{appid_str}\n"
                        else:
                            apps_section += f"No installed app match found for '{query_hint}'.\n"
                    else:
                        apps_section += "No app query inferred from user text.\n"
                
                if "running_processes" in needs_context:
                    all_procs = await sys_ctx.get_ai_context()
                    proc_list = all_procs.get("running_processes", [])
                    hint_block = ""
                    if query_hint and not self._is_vague_query(user_text):
                        matches = await sys_ctx.find_process(query_hint)
                        if matches:
                            descs = [
                                f"{m.get('name', 'Unknown')} (PID: {m.get('pid')})"
                                for m in matches[:8]
                            ]
                            hint_block = (
                                "Heuristic name/path matches for inferred query "
                                f"'{query_hint}' (speech may be wrong — verify in table): "
                                + "; ".join(descs) + "\n\n"
                            )
                    proc_section = (
                        hint_block
                        + "Running processes — choose kill_process targets ONLY from rows below. "
                        "Use the exact `Name.exe (PID: N)` from a row. "
                        "Match user phrases (game title, 'music player', etc.) using exe name AND "
                        "the path tail after |.\n"
                        + "\n".join(proc_list)
                        + "\n"
                    )
                
                _MAX_APPS_CTX = 2500
                _MAX_PROC_CTX = 28000
                if len(apps_section) > _MAX_APPS_CTX:
                    apps_section = apps_section[: _MAX_APPS_CTX - 3] + "..."
                if len(proc_section) > _MAX_PROC_CTX:
                    proc_section = proc_section[: _MAX_PROC_CTX - 3] + "..."
                
                system_context_str += apps_section + proc_section
                
                # #region agent log — only active when APP_DEBUG=true
                if getattr(self.settings.app, "debug", False):
                    try:
                        import json as _json
                        import time as _time
                        _log_payload = {
                            "sessionId": "a7b452",
                            "timestamp": int(_time.time() * 1000),
                            "location": "context_manager.py:build_messages",
                            "message": "system_context_sizes",
                            "hypothesisId": "H1_H2",
                            "data": {
                                "needs_context": needs_context,
                                "proc_lines": len(proc_list) if "running_processes" in needs_context else 0,
                                "apps_chars": len(apps_section),
                                "proc_chars": len(proc_section),
                                "total_chars": len(system_context_str),
                                "query_hint": (query_hint or "")[:80],
                            },
                        }
                        with open("debug-a7b452.log", "a", encoding="utf-8") as _df:
                            _df.write(_json.dumps(_log_payload) + "\n")
                    except Exception:
                        pass
                # #endregion
                
                logger.debug(f"System context provided: {needs_context}")
            
            except Exception as e:
                logger.debug(f"Could not fetch system context: {e}")
        else:
            logger.debug(f"No system context requested for: {user_text[:50]}...")
        
        # Always include the main system prompt (AI needs it for proper command generation)
        history = context.get("history", [])
        system_message = {
            "role": "system",
            "content": system_prompt
        }
        messages.append(system_message)

        # Add relevant system context as a separate system message for visibility
        if system_context_str:
            messages.append({
                "role": "system",
                "content": system_context_str
            })

        # Add conversation summary first if available
        summary_text = context.get("summary") or ""
        if summary_text:
            logger.info(f"[CONTEXT] Including conversation summary (length: {len(summary_text)} chars)")
            messages.append({
                "role": "system",
                "content": f"Conversation summary (for context): {summary_text}"
            })

        # Add structured pending clarification state as a hard constraint for decision safety.
        if self._is_pending_clarification_active(context):
            pending_intent = context.get("pending_intent") or "unknown"
            pending_slots = context.get("pending_slots") or []
            pending_question = context.get("pending_question") or ""
            messages.append({
                "role": "system",
                "content": (
                    "Pending clarification is active. "
                    f"Intent: {pending_intent}. "
                    f"Missing slots: {', '.join(pending_slots) if pending_slots else 'unspecified'}. "
                    f"Assistant asked: {pending_question}. "
                    "If user reply is short (for example, only an app name), treat it as the missing slot value and COMPLETE the original action. "
                    "For example, if the original intent was to CLOSE an app and the user gives a name, you MUST close it — NOT open or launch it."
                )
            })

        # Add conversation history if available
        logger.info(f"[CONTEXT] History has {len(history)} messages")
        if history:
            # Add recent messages (already trimmed by update_context when long)
            messages.extend(history)
            logger.info(f"[CONTEXT] Added {len(history)} history messages to AI context")
        else:
            logger.warning(f"[CONTEXT] No conversation history found for conversation {context.get('conversation_id')}")
        
        # Add current user message
        messages.append({"role": "user", "content": user_text})
        
        logger.info(f"[CONTEXT] Total messages being sent to AI: {len(messages)}")
        return messages

    def _summarize_messages(self, messages: List[Dict[str, str]], existing_summary: str) -> str:
        """
        Lightweight heuristic summarization of older messages.
        - Combines prior summary with key points from provided messages
        - Extracts recent intents/entities-like keywords heuristically
        - Truncates to a safe maximum length upstream
        """
        if not messages:
            return existing_summary

        # Start with existing summary context
        parts: List[str] = []
        if existing_summary:
            parts.append(existing_summary.strip())

        # Build a compact bullet-like summary of pairs
        highlights: List[str] = []
        last_user = None
        for msg in messages:
            role = msg.get("role", "")
            content = (msg.get("content", "") or "").strip()
            if not content:
                continue
            # Keep it short; prefer user asks and assistant confirmations/actions
            if role == "user":
                last_user = content
                if len(content) > 180:
                    content = content[:177] + "..."
                highlights.append(f"User: {content}")
            elif role == "assistant":
                # If assistant follows a user, capture action intent
                summary_line = content
                if len(summary_line) > 180:
                    summary_line = summary_line[:177] + "..."
                highlights.append(f"Assistant: {summary_line}")

        if highlights:
            parts.append("; ".join(highlights))

        # Merge and lightly normalize whitespace
        combined = " \n".join(p for p in parts if p)
        combined = " ".join(combined.split())
        return combined

    async def _get_llm_client(self):
        """Lazily get the configured LLM client (Groq or Gemini)."""
        try:
            provider = self.settings.app.llm_provider
            if provider == "gemini":
                from src.ai.gemini_client import get_gemini_client
                return await get_gemini_client()
            else:
                from src.ai.groq_client import get_groq_client
                return await get_groq_client()
        except Exception as e:
            logger.debug(f"LLM client init failed: {e}")
            return None

    async def _ai_summarize(self, messages: List[Dict[str, str]], existing_summary: str) -> str:
        """
        Use the configured AI to generate a compact rolling summary of older history.
        Returns empty string on failure so caller can fallback.
        """
        if not messages:
            return existing_summary or ""

        llm = await self._get_llm_client()
        if not llm:
            return ""

        # Build a compact transcript string from provided messages
        def clip(text: str, limit: int = 400) -> str:
            text = (text or "").strip()
            return text if len(text) <= limit else text[: limit - 3] + "..."

        transcript_parts: List[str] = []
        # Limit how many we send to avoid token bloat
        slice_messages = messages[-12:]  # last up to 12 items of head
        for msg in slice_messages:
            role = msg.get("role", "user")
            content = clip(msg.get("content", ""), 300)
            if not content:
                continue
            prefix = "User" if role == "user" else "Assistant"
            transcript_parts.append(f"{prefix}: {content}")
        transcript = "\n".join(transcript_parts)

        system_inst = (
            "You maintain a brief running summary of the conversation. "
            "Merge the following excerpt into the existing summary, preserving key intents, entities, and decisions. "
            "Keep it under 6 short sentences, neutral tone, no speculation, no code blocks."
        )

        prompt_messages = [
            {"role": "system", "content": system_inst},
            {"role": "user", "content": (
                f"Existing summary (may be empty): {existing_summary or 'None'}\n\n"
                f"New conversation excerpt to merge:\n{transcript}\n\n"
                "Return only the updated summary."
            )},
        ]

        try:
            # For summarization, we don't need JSON format - just plain text
            # Check if the LLM client supports use_json_format parameter
            import inspect
            sig = inspect.signature(llm.chat)
            if "use_json_format" in sig.parameters:
                ai_resp = await llm.chat(prompt_messages, use_json_format=False)
            else:
                ai_resp = await llm.chat(prompt_messages)
            
            # Both clients return a dict with a 'response' string in our codebase pattern
            summary_text = (ai_resp or {}).get("response", "").strip()
            return summary_text
        except Exception as e:
            logger.debug(f"AI summarization failed: {e}")
            return ""

    def _is_vague_query(self, user_text: str) -> bool:
        """Return True if the user's request is semantically vague (e.g. 'the app playing music')."""
        text = (user_text or "").lower()
        vague_patterns = [
            "playing music", "playing audio", "playing sound",
            "music player", "my music", "close my music",
            "my game", "my browser", "my editor", "my chat app",
            "that app", "the app",
            "running game", "current game", "the game", "a game",
        ]
        return any(p in text for p in vague_patterns)

    def _extract_query_from_text(self, user_text: str, context: Dict[str, Any]) -> str:
        """
        Infer a simple query string (likely app or process name) from user text/history.
        Heuristic: look for words following verbs like open/launch/start/close/kill.
        Fallback to last_entities if present.
        """
        text = (user_text or "").strip().lower()
        # Quick patterns
        import re
        patterns = [
            r"(?:open|launch|start|run)\s+([^.,;\n]+)",
            r"(?:close|kill|end|terminate|stop)\s+([^.,;\n]+)",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                candidate = m.group(1).strip()
                # trim common extras
                candidate = re.sub(r"\b(app|application|program|the|that|is|playing|music|audio|sound|my|game|browser)\b", "", candidate).strip()
                if candidate:
                    return candidate
        # Fallback to last_entities
        last_entities = context.get("last_entities") or []
        if last_entities:
            return str(last_entities[-1]).lower()
        return ""

    def _infer_pending_slots(self, assistant_response: str) -> List[str]:
        """Infer likely missing slots from assistant clarification question text."""
        text = (assistant_response or "").strip().lower()
        if not text:
            return []
        if "which app" in text or "what app" in text or "which application" in text:
            return ["app_name"]
        if "which process" in text or "what process" in text:
            return ["process_name"]
        if "which song" in text or "what song" in text:
            return ["song_name"]
        if "which game" in text or "what game" in text:
            return ["process_name"]
        if "which device" in text or "what device" in text:
            return ["device_name"]
        return []

    def _next_pending_expiry_iso(self) -> str:
        """Return ISO timestamp for pending clarification grace expiry."""
        return (datetime.utcnow() + timedelta(seconds=self._pending_clarification_grace_seconds)).isoformat()

    def _clear_pending_clarification(self, context: Dict[str, Any]):
        """Clear pending clarification fields in-place."""
        context["pending_clarification"] = False
        context["pending_intent"] = None
        context["pending_slots"] = []
        context["pending_question"] = ""
        context["pending_expires_at"] = None

    def _is_pending_clarification_active(self, context: Dict[str, Any]) -> bool:
        """Check whether pending clarification is still inside grace window."""
        if not context.get("pending_clarification"):
            return False

        expires_at = context.get("pending_expires_at")
        if not expires_at:
            return True

        try:
            expires_dt = datetime.fromisoformat(str(expires_at))
            return expires_dt > datetime.utcnow()
        except Exception:
            # If malformed, keep safe behavior and treat as active.
            return True


# Global context manager instance
_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """Get or create global context manager"""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager
