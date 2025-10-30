"""
Main Aiden Assistant Orchestrator
Coordinates all components for intelligent voice interaction
"""
import asyncio
import logging
from typing import Optional

from src.ai.groq_client import get_groq_client
from src.ai.gemini_client import get_gemini_client
from src.core.context_manager import get_context_manager
from src.execution.command_executor import get_command_executor
from src.speech.stt import get_stt_engine
from src.speech.tts import get_tts_engine
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


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
        
        logger.info(f"Aiden Assistant initialized with {self.settings.app.llm_provider.upper()} LLM")
    
    async def _ensure_llm_client(self):
        """Lazy initialize LLM client based on provider setting"""
        if self.llm_client is None:
            if self.settings.app.llm_provider == "gemini":
                logger.info("Initializing Google Gemini client...")
                self.llm_client = await get_gemini_client()
            else:  # groq
                logger.info("Initializing Groq client...")
                self.llm_client = await get_groq_client()
        return self.llm_client
    
    async def _auto_listen_for_followup(self):
        """
        Automatically listen for follow-up response without wake word
        Called when AI expects a follow-up (e.g., after asking a question)
        """
        try:
            import asyncio
            
            # Wait briefly before auto-listen
            await asyncio.sleep(0.3)
            
            # Listen for user response (activation sound plays automatically)
            success, user_text, error = await self.stt.transcribe(play_activation_sound=True)
            
            if not success:
                if error == "timeout":
                    logger.info("No follow-up response - timeout")
                    await self.tts.speak("Okay, let me know if you need anything.")
                else:
                    logger.warning(f"STT failed during auto-listen: {error}")
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
            
        except Exception as e:
            logger.error(f"Error during auto-listen: {e}", exc_info=True)
    
    async def _speak_async(self, text: str, wait: bool = False):
        """
        Wrapper to speak asynchronously without blocking
        
        Args:
            text: Text to speak
            wait: If True, waits for TTS to complete (needed for follow-ups)
        
        Catches errors to prevent TTS from blocking execution
        """
        try:
            await self.tts.speak(text)
        except Exception as e:
            logger.error(f"Background TTS error (non-critical): {e}")
    
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
            
            # Load enhancement prompt from prompts.yaml
            from pathlib import Path
            import yaml
            
            enhancement_prompt = "You are a voice assistant. Convert device responses to natural speech."
            try:
                prompts_file = Path("config/prompts.yaml")
                if prompts_file.exists():
                    with open(prompts_file, 'r', encoding='utf-8') as f:
                        prompts = yaml.safe_load(f)
                        enhancement_template = prompts.get("enhancement_prompt", "")
                        if enhancement_template:
                            # Fill in the template
                            enhancement_prompt = enhancement_template.format(
                                user_request=user_text,
                                device_response=esp32_feedback
                            )
            except Exception as e:
                logger.warning(f"Could not load enhancement_prompt from prompts.yaml: {e}")
            
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
    
    async def handle_voice_activation(self, from_hotkey: bool = False):
        """
        Handle voice activation (wake word or hotkey)
        Complete flow: Listen -> Understand -> Execute -> Respond
        
        Args:
            from_hotkey: True if activated via hotkey (plays activation sound)
        """
        if self.is_processing:
            logger.warning("Already processing a request")
            return
        
        self.is_processing = True
        
        try:
            # Broadcast listening status
            from src.utils.websocket_broadcast import broadcast_voice_status
            await broadcast_voice_status("listening", speaking=False)
            
            # Step 1: Listen IMMEDIATELY (activation sound plays inside transcribe)
            # Don't wait for anything - just start listening!
            success, user_text, error = await self.stt.transcribe(play_activation_sound=True)
            
            # Start conversation in background while user was speaking
            if not self.context_manager.current_conversation_id:
                conversation_id = await self.context_manager.start_conversation(mode="voice")
            
            if not success:
                # Broadcast idle status
                await broadcast_voice_status("idle", speaking=False)
                if error == "timeout":
                    logger.info("No speech detected - timeout")
                else:
                    logger.warning(f"STT failed: {error}")
                    await self.tts.speak("Sorry, I didn't catch that.")
                return
            
            if not user_text:
                logger.warning("Empty transcription")
                # Broadcast idle status
                await broadcast_voice_status("idle", speaking=False)
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
            await broadcast_voice_status("processing", speaking=False)
            
            # Step 2: Process with AI
            await self._process_user_message(user_text)
            
        except Exception as e:
            logger.error(f"Error handling voice activation: {e}", exc_info=True)
            await self.tts.speak("Sorry, something went wrong.")
            # Broadcast idle status on error
            await broadcast_voice_status("idle", speaking=False)
        finally:
            self.is_processing = False
            # Broadcast idle status when conversation ends
            await broadcast_voice_status("idle", speaking=False)
            logger.info("=" * 60)
    
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
            
            # PASS 1: Ask AI what context it needs (lightweight, no system context)
            logger.info("🧠 Pass 1: AI analyzing request...")
            messages_pass1 = await self.context_manager.build_messages(user_text, context, needs_context=None)
            
            llm = await self._ensure_llm_client()
            ai_response_pass1 = await llm.chat(messages_pass1)
            
            if not ai_response_pass1:
                logger.error(f"Empty response from {self.settings.app.llm_provider.upper()} AI (Pass 1)")
                response_text = "Sorry, I couldn't process that."
                await self.tts.speak(response_text)
                return response_text
            
            # Check if AI needs additional context
            needs_context = ai_response_pass1.get("needs_context", [])
            
            if needs_context:
                # PASS 2: Provide requested context and get final response
                logger.info(f"🧠 Pass 2: Fetching {needs_context} and re-processing...")
                messages_pass2 = await self.context_manager.build_messages(user_text, context, needs_context=needs_context)
                ai_response = await llm.chat(messages_pass2)
                
                if not ai_response:
                    # Fallback to Pass 1 response
                    logger.warning("Pass 2 failed, using Pass 1 response")
                    ai_response = ai_response_pass1
            else:
                # No additional context needed, use Pass 1 response
                logger.info("✅ No additional context needed")
                ai_response = ai_response_pass1
            
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
            
            # Execute commands concurrently if any
            if commands:
                # Start TTS in background immediately (fire and forget)
                # But store task if we need to wait for follow-up
                tts_task = asyncio.create_task(self._speak_async(response_text))
                
                # Execute commands FIRST for instant action
                execution_results = await self.executor.execute_multiple(commands)
                
                # Check for ESP32 responses and enhance AI response
                esp32_responses = [r.get("response_data") for r in execution_results if r.get("response_data")]
                if esp32_responses and self.settings.app.enable_enhanced_responses:
                    esp32_feedback = esp32_responses[0]
                    logger.info(f"📡 ESP32 Response: {esp32_feedback}")
                    
                    # Ask AI to generate a better response based on ESP32 feedback
                    enhanced_response = await self._enhance_response_with_feedback(
                        user_text, 
                        response_text, 
                        esp32_feedback
                    )
                    response_text = enhanced_response if enhanced_response else response_text
                elif esp32_responses and not self.settings.app.enable_enhanced_responses:
                    # Log original ESP32 feedback but skip enhancement
                    esp32_feedback = esp32_responses[0]
                    logger.info(f"📡 ESP32 Response: {esp32_feedback}")
                
                # Check for failures and update response
                failed = [r for r in execution_results if not r.get("success", False)]
                if failed:
                    logger.warning(f"Command execution failures: {failed}")
                    # Check if it's a connection error
                    errors = [r.get("error") for r in failed if r.get("error")]
                    if any("Connection failed" in str(e) or "Timeout" in str(e) for e in errors):
                        response_text = "I couldn't reach the ESP32. Please check if it's powered on and connected to the network."
                
                # Wait for TTS to finish if we're auto-listening (prevent mic from hearing itself)
                if expecting_followup:
                    await tts_task
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


# Global instance
_assistant: Optional[AidenAssistant] = None


async def get_assistant() -> AidenAssistant:
    """Get or create global assistant instance"""
    global _assistant
    if _assistant is None:
        _assistant = AidenAssistant()
    return _assistant

