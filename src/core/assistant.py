"""
Main Aiden Assistant Orchestrator
Coordinates all components for intelligent voice interaction
"""
import asyncio
import json
import logging
import re
import time
from typing import Optional, List, Dict, Any, Tuple

from src.ai.groq_client import get_groq_client
from src.ai.gemini_client import get_gemini_client
from src.ai.ollama_client import get_ollama_client
from src.core.context_manager import get_context_manager
from src.execution.command_executor import get_command_executor
from src.speech.stt import get_stt_engine
from src.speech.tts import get_tts_engine
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _normalize_intent_text(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
    return " ".join(normalized.split())


def infer_simple_fan_command(user_text: str) -> Optional[Dict[str, Any]]:
    """
    Recover obvious single-purpose fan power commands when STT typos or the LLM
    misses a simple request like "trun of fan".
    """
    normalized = _normalize_intent_text(user_text)
    if not normalized or "fan" not in normalized:
        return None

    # Only apply this heuristic to short, direct fan commands.
    if any(token in normalized.split() for token in {"and", "then", "after"}):
        return None

    off_patterns = (
        r"\b(?:turn|trun|switch|shut)\s+(?:the\s+)?fan\s+(?:off|of)\b",
        r"\b(?:turn|trun|switch|shut)\s+(?:off|of)\s+(?:the\s+)?fan\b",
        r"\bfan\s+(?:off|of)\b",
        r"\bstop\s+(?:the\s+)?fan\b",
    )
    on_patterns = (
        r"\b(?:turn|trun|switch)\s+(?:the\s+)?fan\s+on\b",
        r"\b(?:turn|trun|switch)\s+on\s+(?:the\s+)?fan\b",
        r"\bfan\s+on\b",
    )

    target: Optional[str] = None
    if any(re.search(pattern, normalized) for pattern in off_patterns):
        target = "off"
    elif any(re.search(pattern, normalized) for pattern in on_patterns):
        target = "on"

    if target is None:
        return None

    response = "Turning the fan off." if target == "off" else "Turning the fan on."
    return {
        "is_followup": False,
        "intent": "command",
        "commands": [{"type": "fan_control", "params": {"control_id": "power", "target": target}}],
        "response": response,
        "update_context": True,
        "expecting_followup": False,
    }


def build_fan_spoken_response(payload: Any) -> Optional[str]:
    """Generate deterministic, user-friendly spoken fan status."""
    if isinstance(payload, str):
        text = payload.strip()
        lowered = text.lower()
        if "already off" in lowered:
            return "The fan is already off."
        if "already on" in lowered:
            return "The fan is already on."
        return None

    if not isinstance(payload, dict):
        return None

    control_id = str(payload.get("control_id") or "").lower()
    target = str(payload.get("target") or "").lower() if payload.get("target") is not None else None
    message = str(payload.get("message") or "").strip().lower()
    device = payload.get("device") if isinstance(payload.get("device"), dict) else {}
    summary = device.get("summary") if isinstance(device, dict) else {}
    confirmed_state = str(summary.get("state") or "").lower() if isinstance(summary, dict) else ""

    if control_id == "power" and target in {"on", "off"}:
        if "already" in message:
            return f"The fan is already {target}."
        if confirmed_state == target:
            return f"The fan is {target}."
        return "I'm trying to turn the fan on." if target == "on" else "I'm trying to turn the fan off."

    if control_id == "speed" and target:
        return f"Fan speed set to {target}."

    if control_id == "timer" and target:
        if target == "off":
            return "Turning the fan timer off."
        return f"Setting the fan timer to {target} hours."

    if control_id == "osc" and target in {"on", "off"}:
        return f"Turning oscillation {target}."

    if control_id == "mode" and target:
        return f"Setting the fan mode to {target}."

    return None


class AidenAssistant:
    """
    Main assistant orchestrator
    Handles the complete interaction flow from speech to execution
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.user_name = self.settings.app.user_name
        
        # Core components (non-async)
        self.context_manager = get_context_manager()
        self.executor = get_command_executor()
        self.stt = get_stt_engine()
        self.tts = get_tts_engine()
        
        # Async components (initialized lazily)
        self.llm_client = None
        
        # State
        self.is_processing = False
        self._speak_tasks = set()
        self._current_request_task = None
        self._is_listening = False
        
        logger.info(f"Aiden Assistant initialized with {self.settings.app.llm_provider.upper()} LLM")

    async def _play_wake_acknowledgement(self) -> None:
        """Play the short voice wake acknowledgement before the mic-open cue."""
        try:
            import random

            sound_name = random.choice(("mmm1", "mmm2"))
            await self.tts.play_sound_now(sound_name)
        except Exception as exc:
            logger.debug("Could not play wake acknowledgement: %s", exc)

    async def _maybe_apply_vague_close_heuristic(
        self,
        user_text: str,
        needs_context: List[str],
        ai_response: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        If the user asked to close a vague 'game' or 'music player' and the LLM only asked a question,
        pick a kill target from the running-process table (singleton) or list concrete candidates.
        """
        if not ai_response or "running_processes" not in (needs_context or []):
            return ai_response
        if ai_response.get("commands"):
            return ai_response

        ut = (user_text or "").lower()
        wants_game = bool(
            re.search(
                r"\b(close|kill|end|quit|stop|force\s*quit)\s+(my|the|this)?\s*game\b",
                ut,
            )
        ) or ("close" in ut and "my game" in ut)
        wants_music = bool(
            re.search(
                r"\b(close|kill|end|quit|stop)\s+.*\b(music\s*player|my\s+music|app\s+playing\s+music|the\s+music\s+app)\b",
                ut,
            )
        ) or ("close" in ut and "playing music" in ut)

        if not wants_game and not wants_music:
            return ai_response

        from src.utils.system_context import get_system_context

        lines = (await get_system_context().get_ai_context()).get("running_processes") or []

        def parse_pid_rows(tag: str) -> List[Tuple[str, int, str]]:
            rows: List[Tuple[str, int, str]] = []
            for line in lines:
                if tag not in line:
                    continue
                m = re.match(r"^(.+?)\s+\(PID:\s*(\d+)\)", line.strip())
                if m:
                    rows.append((m.group(1).strip(), int(m.group(2)), line))
            return rows

        path_markers = (
            "steamapps",
            "epic games",
            "riot games",
            "ubisoft",
            "ea games",
            "electronic arts",
            "battle.net",
            "gog ",
            "xboxgames",
            "rockstar games",
        )

        def parse_rows_from_path_hints() -> List[Tuple[str, int, str]]:
            rows: List[Tuple[str, int, str]] = []
            for line in lines:
                low = line.lower()
                if not any(m in low for m in path_markers):
                    continue
                m = re.match(r"^(.+?)\s+\(PID:\s*(\d+)\)", line.strip())
                if m:
                    rows.append((m.group(1).strip(), int(m.group(2)), line))
            return rows

        candidates: List[Tuple[str, int, str]] = []
        if wants_game:
            candidates = parse_pid_rows("[game]")
            if not candidates:
                candidates = parse_rows_from_path_hints()
        elif wants_music:
            candidates = parse_pid_rows("[media/music]")

        # #region agent log
        try:
            with open("debug-a7b452.log", "a", encoding="utf-8") as _df:
                _df.write(
                    json.dumps(
                        {
                            "sessionId": "a7b452",
                            "timestamp": int(time.time() * 1000),
                            "location": "assistant.py:_maybe_apply_vague_close_heuristic",
                            "message": "vague_close_heuristic",
                            "hypothesisId": "H5",
                            "data": {
                                "wants_game": wants_game,
                                "wants_music": wants_music,
                                "candidate_count": len(candidates),
                                "llm_had_commands": bool(ai_response.get("commands")),
                            },
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass
        # #endregion

        if len(candidates) == 1:
            name, pid, _ = candidates[0]
            out = dict(ai_response)
            out["commands"] = [{"type": "kill_process", "params": {"name": f"{name} (PID: {pid})"}}]
            out["response"] = f"Closing {name}."
            out["expecting_followup"] = False
            out["intent"] = "command"
            logger.info(f"Vague close heuristic: killing singleton {name} (PID {pid})")
            return out

        if len(candidates) > 1:
            kind = "games" if wants_game else "music apps"
            names = [c[0] for c in candidates[:6]]
            out = dict(ai_response)
            out["commands"] = []
            out["response"] = f"I see several {kind} running: {', '.join(names)}. Which one should I close?"
            out["expecting_followup"] = True
            out["intent"] = "command"
            logger.info("Vague close heuristic: listed multiple candidates for user choice")
            return out

        return ai_response

    def _maybe_apply_simple_fan_heuristic(
        self,
        user_text: str,
        ai_response: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Recover a simple fan power request when the LLM fails to emit a
        `fan_control` command for an obvious, short command.
        """
        if not ai_response:
            return ai_response

        commands = ai_response.get("commands") or []
        if any((cmd.get("type") or "").lower() == "fan_control" for cmd in commands):
            return ai_response

        fan_response = infer_simple_fan_command(user_text)
        if fan_response is None:
            return ai_response

        logger.info("Applied simple fan heuristic for request: %s", user_text)
        return fan_response

    async def _ensure_llm_client(self):
        """Lazy initialize LLM client based on provider setting"""
        if self.llm_client is None:
            if self.settings.app.llm_provider == "gemini":
                logger.info("Initializing Google Gemini client...")
                self.llm_client = await get_gemini_client()
            elif self.settings.app.llm_provider == "groq":
                logger.info("Initializing Groq client...")
                self.llm_client = await get_groq_client()
            else:
                logger.info("Initializing Ollama client...")
                self.llm_client = await get_ollama_client()
        return self.llm_client
    
    async def _auto_listen_for_followup(self):
        """
        Automatically listen for follow-up response without wake word
        Called when AI expects a follow-up (e.g., after asking a question)
        """
        try:
            import asyncio
            
            # Wait for TTS to finish speaking before listening
            logger.debug("Waiting for TTS to complete before auto-listen...")
            await self.tts.wait_until_done(timeout=10.0)
            
            # Brief pause after TTS for natural conversation flow
            await asyncio.sleep(0.3)
            
            # Listen for user response (activation sound plays automatically)
            success, user_text, error = await self.stt.transcribe(play_activation_sound=True)
            
            if not success:
                if error == "timeout":
                    logger.info("No follow-up response - timeout")
                    await self.context_manager.refresh_pending_clarification_grace()
                    retry_prompt = "I did not catch that. Please repeat briefly."
                    try:
                        context = await self.context_manager.get_context()
                        if context.get("pending_clarification"):
                            pending_slots = context.get("pending_slots") or []
                            if "app_name" in pending_slots:
                                retry_prompt = "I did not catch that. You can just say the app name."
                            elif "process_name" in pending_slots:
                                retry_prompt = "I did not catch that. You can just say the process name."
                            elif "song_name" in pending_slots:
                                retry_prompt = "I did not catch that. You can just say the song name."
                            elif "device_name" in pending_slots:
                                retry_prompt = "I did not catch that. You can just say the device name."
                            else:
                                retry_prompt = "I did not catch that. You can answer briefly."
                    except Exception:
                        pass
                    await self.tts.speak(retry_prompt)
                else:
                    logger.warning(f"STT failed during auto-listen: {error}")
                    await self.context_manager.refresh_pending_clarification_grace()
                return
            
            if not user_text:
                logger.warning("Empty transcription during auto-listen")
                return
            
            logger.info(f"📝 USER FOLLOW-UP: {user_text}")
            
            # Broadcast follow-up user message to dashboard
            try:
                from src.utils.websocket_broadcast import broadcast_message
                await broadcast_message("message", {
                    "role": "user",
                    "content": user_text,
                    "timestamp": __import__('datetime').datetime.now().isoformat()
                })
            except Exception:
                pass  # Non-critical
            
            # Process the follow-up message
            await self._process_user_message(user_text)
            
        except asyncio.CancelledError:
            logger.info("Auto-listen follow-up cancelled")
            raise
        except Exception as e:
            logger.error(f"Error during auto-listen: {e}", exc_info=True)
    
    async def _speak_async(self, text: str, wait: bool = False):
        """
        Wrapper to speak asynchronously without blocking - streams by sentence
        
        Args:
            text: Text to speak
            wait: If True, waits for TTS to complete 
        """
        import asyncio
        task = asyncio.current_task()
        if task:
            self._speak_tasks.add(task)
            
        try:
            import re
            # Split text into sentences using regex, preserving punctuation
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+', text) if s.strip()]
            
            if not sentences:
                return

            # By queuing sentences individually, Aiden begins playing the first
            # sentence instantly while the rest are fetched in the background.
            for sentence in sentences:
                await self.tts.speak(sentence)

            if wait:
                await self.tts.wait_until_done()
                
        except asyncio.CancelledError:
            logger.info("Background TTS chunking cancelled (barge-in)")
        except Exception as e:
            logger.error(f"Background TTS error (non-critical): {e}")
        finally:
            if task:
                self._speak_tasks.discard(task)
    
    async def _enhance_response_with_feedback(
        self, 
        user_text: str, 
        original_response: str, 
        esp32_feedback: str
    ) -> Optional[str]:
        """
        Enhance AI response based on ESP32 feedback using prompts.yaml
        
        Args:
            user_text: Original user request
            original_response: AI's initial response
            esp32_feedback: Actual ESP32 response text
            
        Returns:
            Enhanced response or None if enhancement fails
        """
        try:
            llm = await self._ensure_llm_client()
            
            from src.utils.prompt_loader import get_prompt

            enhancement_template = get_prompt(
                "enhancement_prompt",
                "You are a voice assistant. Convert device responses to natural speech.",
            )
            enhancement_prompt = enhancement_template
            try:
                enhancement_prompt = enhancement_template.format(
                    user_request=user_text,
                    device_response=esp32_feedback
                )
            except Exception:
                pass
            
            # Build messages for AI - use direct API call instead of chat()
            # because chat() forces JSON response format which we don't need here
            import httpx
            
            enhancement_messages = [
                {
                    "role": "system",
                    "content": "You are a helpful voice assistant. Respond with natural speech only."
                },
                {
                    "role": "user",
                    "content": enhancement_prompt
                }
            ]
            
            # Make direct API call without JSON format requirement
            payload = {
                "model": self.settings.groq.model,
                "messages": enhancement_messages,
                "temperature": 0.3,
                "max_tokens": 50,
                # NO response_format - we want plain text response
            }
            
            headers = {
                "Authorization": f"Bearer {self.settings.groq.api_key}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                result = response.json()
                enhanced = result["choices"][0]["message"]["content"].strip()
            
            # Clean up any quotes or extra formatting
            enhanced = enhanced.strip('"\'')
            
            if enhanced and len(enhanced) > 0:
                logger.info(f"✨ Enhanced response: {enhanced}")
                return enhanced
            
            return None
            
        except Exception as e:
            logger.error(f"Error enhancing response: {e}")
            return None
    
    def _merge_command_responses(
        self,
        base_text: str,
        execution_results: List[Dict[str, Any]]
    ) -> str:
        """Append dynamic status messages from command execution to the spoken response."""
        status_messages: List[str] = []
        enriching_types = {"battery_status", "cpu_status", "gpu_status", "browser_media", "spotify", "media", "self_termination", "ups_status"}
        for result in execution_results:
            data = result.get("response_data")
            if not isinstance(data, dict):
                continue
            if data.get("type") in enriching_types:
                message = data.get("message")
                if message:
                    status_messages.append(message)
        if not status_messages:
            return base_text
        addition = " ".join(status_messages)
        return f"{base_text.strip()} {addition}".strip() if base_text else addition

    def _describe_failed_action(self, result: Dict[str, Any]) -> str:
        """Create a short, honest user-facing message for a failed command."""
        data = result.get("response_data")
        if isinstance(data, dict):
            data_type = (data.get("type") or "").strip().lower()
            message = (data.get("message") or "").strip()

            if data_type == "spotify":
                params = result.get("params") or {}
                action = (params.get("action") or "").lower()
                query = params.get("query")

                if action == "play_track" and query:
                    return f"I couldn't play {query} on Spotify."
                if action == "play_playlist" and query:
                    return f"I couldn't play the playlist {query} on Spotify."
                if action in {"play", "resume", "play_liked_songs"}:
                    return "I couldn't start Spotify playback."
                if action == "pause":
                    return "I couldn't pause Spotify."
                if action == "transfer":
                    return "I couldn't move Spotify to that device."
                return message or "I couldn't complete that on Spotify."

            if data_type == "browser_media":
                params = result.get("params") or {}
                action = (params.get("action") or "").lower()
                target = (params.get("target") or "browser media").replace("_", " ")

                if action in {"play", "resume", "play_pause"}:
                    return f"I couldn't control playback in {target}."
                if action == "play_track" and params.get("query"):
                    return f"I couldn't play {params.get('query')} in {target}."
                return message or f"I couldn't control {target}."

            if message:
                return message

        command = result.get("command")
        params = result.get("params") or {}

        if command == "system_command":
            action = (params.get("action") or "").lower()
            action_map = {
                "lock": "I couldn't lock your PC.",
                "shutdown": "I couldn't shut down your PC.",
                "restart": "I couldn't restart your PC.",
                "sleep": "I couldn't put the PC to sleep.",
                "hibernate": "I couldn't hibernate the PC.",
                "empty_recycle_bin": "I couldn't empty the recycle bin.",
                "clear_recycle_bin": "I couldn't empty the recycle bin.",
            }
            return action_map.get(action, "I couldn't complete that system action.")

        if command == "launch_app":
            app_name = params.get("name") or params.get("app_name") or "that app"
            return f"I couldn't open {app_name}."

        if command == "kill_process":
            process_name = params.get("name") or "that app"
            return f"I couldn't close {process_name}."

        if command == "scheduled_command":
            action = (params.get("action") or "that").lower()
            return f"I couldn't set the {action} timer."

        if command == "cancel_timer":
            return "I couldn't cancel the timer."

        if command == "shell_command":
            return "I couldn't run that command."

        if command == "media_control":
            return "I couldn't complete that media action."

        if command == "fan_control":
            return "I couldn't control the fan."

        return "I couldn't complete that action."

    def _build_failure_followup(
        self,
        execution_results: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Create a follow-up line only when one or more commands failed."""
        failed = [r for r in execution_results if not r.get("success", False)]
        if not failed:
            return None

        failure_messages: List[str] = []
        for result in failed:
            message = self._describe_failed_action(result).strip()
            if message and message not in failure_messages:
                failure_messages.append(message)

        if not failure_messages:
            return "I couldn't complete that."

        if len(failed) == len(execution_results):
            return " ".join(failure_messages[:2])

        if len(failure_messages) == 1:
            return f"I completed part of that, but {failure_messages[0][0].lower()}{failure_messages[0][1:]}"

        return f"I completed part of that, but {' '.join(failure_messages[:2])}"
    
    async def handle_voice_activation(self, from_hotkey: bool = False):
        """
        Handle voice activation (wake word or hotkey)
        Complete flow: Listen -> Understand -> Execute -> Respond
        
        Args:
            from_hotkey: True if activated via hotkey (plays activation sound)
        """
        import asyncio
        
        # BARGE-IN: Cancel the main conversation task if one is currently processing
        if self._current_request_task and not self._current_request_task.done():
            logger.warning("Barge-in: Cancelling old request context")
            self._current_request_task.cancel()
            
        self._current_request_task = asyncio.current_task()
            
        # BARGE-IN: Cancel any currently downloading TTS sentences
        for task in list(self._speak_tasks):
            if not task.done():
                task.cancel()
        self._speak_tasks.clear()
        
        # BARGE-IN: Stop any currently playing audio instantly
        self.tts.stop()

        self.is_processing = True

        # Broadcast listening status IMMEDIATELY so the overlay starts
        # appearing while media ducking and sounds play concurrently.
        from src.utils.websocket_broadcast import broadcast_voice_status
        await broadcast_voice_status("listening", speaking=False, active=True)

        duck_state = None
        duck_state_consumed = False

        # Prepare media ducking before the mic-open cue so STT can start as soon
        # as the sound finishes instead of doing this work afterward.
        try:
            from src.media.media_router import get_media_router
            duck_state = await get_media_router().duck_for_listening()
        except Exception as exc:
            logger.debug(f"STT media ducking unavailable before activation cue: {exc}")

        # For voice wake, cleanly play the vocal acknowledgement ("mmm?").
        # For hotkey, play the standard activation beep.
        # This prevents overlapping audio cues from echoing into STT.
        if not from_hotkey:
            await self._play_wake_acknowledgement()
        else:
            await self.tts.play_sound_now("activation")
        
        import time as _time
        _t0 = _time.monotonic()

        try:
            # (listening status already broadcast above)
            
            # ── Step 1: STT ──────────────────────────────────────────────
            _t_stt_start = _time.monotonic()
            self._is_listening = True
            duck_state_consumed = True
            success, user_text, error = await self.stt.transcribe(
                play_activation_sound=False,
                duck_state=duck_state,
                media_already_ducked=True,
            )
            self._is_listening = False
            logger.info("[TIMING] STT: %.0f ms", (_time.monotonic() - _t_stt_start) * 1000)
            
            # Start conversation in background while user was speaking
            if not self.context_manager.current_conversation_id:
                conversation_id = await self.context_manager.start_conversation(mode="voice")
            
            if not success:
                await broadcast_voice_status("idle", speaking=False, active=False)
                if error == "timeout":
                    logger.info("No speech detected - timeout")
                elif error == "cancelled":
                    logger.info("Voice listening cancelled by user hotkey")
                else:
                    logger.warning(f"STT failed: {error}")
                    await self.tts.speak("Sorry, I didn't catch that.")
                return
            
            if not user_text:
                logger.warning("Empty transcription")
                await broadcast_voice_status("idle", speaking=False, active=False)
                return
            
            logger.info(f"USER: {user_text}")
            
            # Broadcast user message to dashboard
            try:
                from src.utils.websocket_broadcast import broadcast_message
                await broadcast_message("message", {
                    "role": "user",
                    "content": user_text,
                    "timestamp": __import__('datetime').datetime.now().isoformat()
                })
            except Exception:
                pass  # Non-critical
            
            # Broadcast processing status
            await broadcast_voice_status("processing", speaking=False, active=True)
            
            # ── Step 2: AI ───────────────────────────────────────────────
            _t_ai_start = _time.monotonic()
            await self._process_user_message(user_text)
            logger.info("[TIMING] AI+TTS queue: %.0f ms | Total wall: %.0f ms",
                        (_time.monotonic() - _t_ai_start) * 1000,
                        (_time.monotonic() - _t0) * 1000)
            
        except asyncio.CancelledError:
            logger.info("Voice activation cancelled by user")
        except Exception as e:
            logger.error(f"Error handling voice activation: {e}", exc_info=True)
            await self.tts.speak("Sorry, something went wrong.")
            # Broadcast idle status on error
            await broadcast_voice_status("idle", speaking=False, active=False)
        finally:
            if duck_state is not None and not duck_state_consumed:
                try:
                    from src.media.media_router import get_media_router
                    await get_media_router().restore_after_listening(duck_state)
                except Exception as exc:
                    logger.debug(f"STT media restore skipped after activation failure: {exc}")
            self._is_listening = False
            self.is_processing = False
            # Broadcast idle status when conversation ends
            await broadcast_voice_status("idle", speaking=False, active=False)
            logger.info("=" * 60)

    def request_immediate_stop(self) -> bool:
        """Best-effort synchronous stop for hotkey threads."""
        cancelled = False

        if self._is_listening:
            self.stt.request_stop()
            cancelled = True

        self.tts.stop_playback_now()
        return cancelled

    async def cancel_active_listening(self) -> bool:
        """Stop an active STT listen or current request pipeline."""
        cancelled = self.request_immediate_stop()

        if self._is_listening:
            logger.info("Cancelling active STT listen")

        if self._current_request_task and not self._current_request_task.done():
            logger.info("Cancelling active assistant request task")
            self._current_request_task.cancel()
            cancelled = True

        for task in list(self._speak_tasks):
            if not task.done():
                task.cancel()
                cancelled = True

        if cancelled:
            try:
                await self.tts.play_sound_now("stopped")
            except Exception as e:
                logger.debug(f"Could not play stopped sound: {e}")

        return cancelled
    
    async def handle_text_message(self, text: str) -> str:
        """
        Handle text-based message (from dashboard/API)
        
        Args:
            text: User's text message
            
        Returns:
            Assistant's response text
        """
        try:
            logger.info(f"TEXT MESSAGE: {text}")
            
            # Process with AI
            response = await self._process_user_message(text)
            
            return response
            
        except Exception as e:
            logger.error(f"Error handling text message: {e}", exc_info=True)
            return "Sorry, something went wrong."
    
    async def _process_user_message(self, user_text: str) -> str:
        """
        Core message processing logic with 2-pass AI system:
        Pass 1: AI decides what context it needs
        Pass 2: AI gets the context and responds
        
        Args:
            user_text: User's message
            
        Returns:
            Assistant's response text
        """
        try:
            # Get conversation context
            context = await self.context_manager.get_context()

            llm = await self._ensure_llm_client()

            # --- Fast path: skip Pass 1 for requests that obviously don't need system context ---
            # This saves a full LLM round trip (~300-800 ms) for the majority of commands.
            if self._no_context_needed(user_text, context):
                logger.info("⚡ Pass 1 skipped (local classifier: no system context needed)")
                messages_direct = await self.context_manager.build_messages(
                    user_text, context, needs_context=[]
                )
                ai_response = await llm.chat(messages_direct)
                if not ai_response:
                    logger.error(f"Empty response from {self.settings.app.llm_provider.upper()} AI (direct)")
                    response_text = "Sorry, I couldn't process that."
                    await self.tts.speak(response_text)
                    return response_text
                needs_context = []
            else:
                # PASS 1: Ask AI what context it needs (lightweight, no system context)
                logger.info("🧠 Pass 1: AI analyzing request...")
                messages_pass1 = await self.context_manager.build_messages(user_text, context, needs_context=None)
                ai_response_pass1 = await llm.chat(messages_pass1)

                if not ai_response_pass1:
                    logger.error(f"Empty response from {self.settings.app.llm_provider.upper()} AI (Pass 1)")
                    response_text = "Sorry, I couldn't process that."
                    await self.tts.speak(response_text)
                    return response_text

                needs_context = ai_response_pass1.get("needs_context", [])

                if needs_context:
                    # PASS 2: Provide requested context and get final response
                    logger.info(f"🧠 Pass 2: Fetching {needs_context} and re-processing...")
                    messages_pass2 = await self.context_manager.build_messages(
                        user_text, context, needs_context=needs_context
                    )
                    ai_response = await llm.chat(messages_pass2)
                    if not ai_response:
                        logger.warning("Pass 2 failed, using Pass 1 response")
                        ai_response = ai_response_pass1
                else:
                    logger.info("✅ No additional context needed")
                    ai_response = ai_response_pass1

            if needs_context and "running_processes" in needs_context:
                ai_response = await self._maybe_apply_vague_close_heuristic(
                    user_text, needs_context, ai_response
                )

            ai_response = self._maybe_apply_simple_fan_heuristic(user_text, ai_response)
            
            # Parse AI response
            intent = ai_response.get("intent", "unknown")
            commands = ai_response.get("commands", [])
            response_text = ai_response.get("response", "Done")
            update_context = ai_response.get("update_context", True)
            
            logger.info(f"AI INTENT: {intent}")
            logger.info(f"AI COMMANDS: {len(commands)}")
            logger.info(f"AI RESPONSE: {response_text}")
            
            # Broadcast assistant response to dashboard
            try:
                from src.utils.websocket_broadcast import broadcast_message
                await broadcast_message("message", {
                    "role": "assistant",
                    "content": response_text,
                    "timestamp": __import__('datetime').datetime.now().isoformat()
                })
            except Exception:
                pass  # Non-critical
            
            # Trust the AI's decision on whether to expect follow-up
            expecting_followup = ai_response.get("expecting_followup", False)

            # Safety gate: if the AI is asking a clarification question, do not execute commands yet.
            # This prevents accidental actions like launching placeholder apps while waiting for user detail.
            if expecting_followup and commands:
                logger.warning(
                    "Safety gate triggered: blocking %d command(s) because follow-up clarification is pending",
                    len(commands),
                )
                ai_response["blocked_commands"] = commands
                commands = []
                ai_response["commands"] = []
            
            # Execute commands concurrently if any
            if commands:
                has_self_termination = any(cmd.get("type") == "self_termination" for cmd in commands)
                should_delay_response = has_self_termination or any(
                    self.executor.command_requires_post_response(cmd)
                    for cmd in commands
                )

                initial_tts_task = None
                if should_delay_response or expecting_followup:
                    execution_results = await self.executor.execute_multiple(commands)
                else:
                    initial_tts_task = asyncio.create_task(self._speak_async(response_text))
                    execution_results = await self.executor.execute_multiple(commands)
                
                # Merge dynamic command responses (battery/cpu/gpu stats) into spoken text
                original_response = response_text
                response_text = self._merge_command_responses(response_text, execution_results)
                
                # Check for fan/ESP32 responses — only override spoken text if
                # TTS hasn't started yet (i.e. we were in delay-response mode).
                # When initial_tts_task is already running, the AI text is already
                # being spoken so we don't interrupt it with the device message.
                esp32_payloads = [
                    r.get("response_data")
                    for r in execution_results
                    if r.get("command") == "fan_control" and r.get("response_data")
                ]
                if esp32_payloads:
                    esp32_feedback = esp32_payloads[0]
                    device_message = esp32_feedback.get("message", "") if isinstance(esp32_feedback, dict) else esp32_feedback
                    logger.info(f"📡 ESP32 Response: {device_message}")
                    if initial_tts_task is None:  # Only override if we haven't spoken yet
                        deterministic_fan_response = build_fan_spoken_response(esp32_feedback)
                        if deterministic_fan_response:
                            response_text = deterministic_fan_response

                # Check for failures and turn them into honest spoken feedback
                failed = [r for r in execution_results if not r.get("success", False)]
                if failed:
                    for r in failed:
                        err_payload = r.get("response_data")
                        err_msg = (err_payload or {}).get("message") if isinstance(err_payload, dict) else None
                        logger.warning(f"Command failed ({r.get('command')}): {err_msg or r.get('error')}")

                failure_followup = self._build_failure_followup(execution_results)

                # Broadcast the enriched initial response if execution changed it
                if response_text != original_response:
                    try:
                        from src.utils.websocket_broadcast import broadcast_message
                        await broadcast_message("message", {
                            "role": "assistant",
                            "content": response_text,
                            "timestamp": __import__('datetime').datetime.now().isoformat()
                        })
                    except Exception:
                        pass  # Non-critical

                if should_delay_response or expecting_followup:
                    await self._speak_async(response_text)
                elif initial_tts_task:
                    await initial_tts_task

                if failure_followup:
                    try:
                        from src.utils.websocket_broadcast import broadcast_message
                        await broadcast_message("message", {
                            "role": "assistant",
                            "content": failure_followup,
                            "timestamp": __import__('datetime').datetime.now().isoformat()
                        })
                    except Exception:
                        pass  # Non-critical

                    if expecting_followup:
                        await self._speak_async(failure_followup)
                    else:
                        asyncio.create_task(self._speak_async(failure_followup))
            else:
                # No commands, just respond
                # Wait for TTS if we're expecting follow-up, otherwise background
                if expecting_followup:
                    await self._speak_async(response_text)  # Wait for TTS
                else:
                    asyncio.create_task(self._speak_async(response_text))  # Background
            
            # Update context if needed
            if update_context:
                await self.context_manager.update_context(
                    user_message=user_text,
                    ai_response=ai_response
                )
            
            # Let AI decide if we should continue listening
            if expecting_followup:
                logger.info("🔄 AI expects follow-up - will auto-listen for response")
                # AUTO-LISTEN for follow-up without requiring wake word!
                await self._auto_listen_for_followup()
            else:
                logger.info("✅ Conversation complete - no follow-up expected")
                # Conversation stays active for 5 minutes (Redis TTL handles cleanup)
            
            return response_text
            
        except asyncio.CancelledError:
            logger.info("User message processing cancelled")
            raise
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            response_text = "Sorry, I encountered an error."
            await self.tts.speak(response_text)
            return response_text
    
    async def greet_user(self):
        """Greet the user on startup"""
        try:
            greeting = f"Hello {self.user_name}, Aiden is ready!"
            logger.info(f"GREETING: {greeting}")
            
            # Play startup sound
            await self.tts.play_sound("startup")
            
            # Speak greeting
            await self.tts.speak(greeting)
            
        except Exception as e:
            logger.error(f"Error greeting user: {e}")

    # ------------------------------------------------------------------
    # Pass-1 bypass classifier
    # ------------------------------------------------------------------

    def _no_context_needed(self, user_text: str, context: dict) -> bool:
        """
        Local heuristic: returns True when the request obviously doesn't need
        system context (running_processes / installed_apps) from the OS.

        When this returns True we skip Pass 1 entirely and send the request
        straight to Pass 2 with needs_context=[], saving one full LLM round
        trip (~300–800 ms depending on model/network).

        Conservative: when in doubt we return False and let Pass 1 decide.
        """
        import re

        # Never skip when the AI is expecting a follow-up answer — that turn
        # may need context to resolve a pending slot (e.g. "close which app?")
        if context.get("expecting_followup") or context.get("pending_clarification"):
            return False

        text = user_text.lower().strip()

        # Patterns that never need OS process / app lists:
        _SIMPLE_PATTERNS = (
            # Greetings / chitchat
            r"^(hi|hello|hey|good (morning|afternoon|evening|night))[\s!?.]*$",
            r"^(thank(s| you)|thanks!?)[\s!?.]*$",
            r"^(how are you|what('s| is) up)[\s!?.]*$",
            # Time / date
            r"\b(what('s| is)?\s+the\s+)?(time|date|day|month|year)\b",
            # Fan / oscillation / UPS — all handled by deterministic heuristics already
            r"\b(fan|oscillat|swing|rotate)\b",
            r"\b(turn (on|off) the fan)\b",
            r"\b(ups|power|battery (status|level)?)\b",
            # Timers / alarms / reminders (no app lookup needed)
            r"\b(set (a |an )?(timer|alarm|reminder)|remind me)\b",
            # Volume (system volume, no process lookup)
            r"\b(volume|mute|unmute)\b",
            # Weather
            r"\b(weather|forecast|temperature outside|rain|snow|humid)\b",
            # Jokes / facts / trivia (pure LLM)
            r"\b(tell me (a )?joke|fun fact|trivia|what is|who is|when (was|did|is|are))\b",
            # Arithmetic / conversions
            r"\b(calc(ulate)?|how many|convert|what('s| is) \d+)\b",
            # Simple smart home that doesn't need process lists
            r"\b(light(s)?|lamp|dimmer|bulb|switch)\b",
        )

        for pattern in _SIMPLE_PATTERNS:
            if re.search(pattern, text):
                logger.debug(f"[FAST-PATH] Skipping Pass 1 — matched no-context pattern: {pattern!r}")
                return True

        return False


# Global instance
_assistant: Optional[AidenAssistant] = None


async def get_assistant() -> AidenAssistant:
    """Get or create global assistant instance"""
    global _assistant
    if _assistant is None:
        _assistant = AidenAssistant()
    return _assistant


def reset_assistant() -> None:
    global _assistant
    _assistant = None
