"""
Main Aiden Assistant Orchestrator
Coordinates all components for intelligent voice interaction
"""
import asyncio
import logging
from typing import Optional

from src.ai.groq_client import get_groq_client
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
        self.groq = None
        
        # State
        self.is_processing = False
        
        logger.info("Aiden Assistant initialized")
    
    async def _ensure_groq(self):
        """Lazy initialize Groq client"""
        if self.groq is None:
            self.groq = await get_groq_client()
        return self.groq
    
    async def _auto_listen_for_followup(self):
        """
        Automatically listen for follow-up response without wake word
        Called when AI expects a follow-up (e.g., after asking a question)
        """
        try:
            import asyncio
            
            logger.info("⏳ Waiting 1 second before auto-listening...")
            await asyncio.sleep(1.0)  # Give user a moment after TTS finishes
            
            logger.info("🎤 Auto-listening for follow-up response...")
            
            # Listen for user response
            success, user_text, error = await self.stt.transcribe()
            
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
            
            # Process the follow-up message
            await self._process_user_message(user_text)
            
        except Exception as e:
            logger.error(f"Error during auto-listen: {e}", exc_info=True)
    
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
            groq = await self._ensure_groq()
            
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
    
    async def handle_voice_activation(self):
        """
        Handle voice activation (wake word or hotkey)
        Complete flow: Listen -> Understand -> Execute -> Respond
        """
        if self.is_processing:
            logger.warning("Already processing a request")
            return
        
        self.is_processing = True
        
        try:
            logger.info("=" * 60)
            logger.info("VOICE ACTIVATION - Starting interaction")
            logger.info("=" * 60)
            
            # Start or continue conversation
            if not self.context_manager.current_conversation_id:
                conversation_id = await self.context_manager.start_conversation(mode="voice")
                logger.info(f"Started new conversation: {conversation_id}")
            else:
                logger.info(f"Continuing conversation: {self.context_manager.current_conversation_id}")
            
            # CRITICAL: Give wake word detector time to release microphone
            import asyncio
            await asyncio.sleep(0.3)
            
            # Step 1: Listen for user input
            logger.info("About to call STT transcribe...")
            success, user_text, error = await self.stt.transcribe()
            logger.info(f"STT returned: success={success}, text={user_text}, error={error}")
            
            if not success:
                if error == "timeout":
                    logger.info("No speech detected - timeout")
                else:
                    logger.warning(f"STT failed: {error}")
                    await self.tts.speak("Sorry, I didn't catch that.")
                return
            
            if not user_text:
                logger.warning("Empty transcription")
                return
            
            logger.info(f"USER: {user_text}")
            
            # Step 2: Process with AI
            await self._process_user_message(user_text)
            
        except Exception as e:
            logger.error(f"Error handling voice activation: {e}", exc_info=True)
            await self.tts.speak("Sorry, something went wrong.")
        finally:
            self.is_processing = False
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
        Core message processing logic
        
        Args:
            user_text: User's message
            
        Returns:
            Assistant's response text
        """
        try:
            # Get conversation context
            context = await self.context_manager.get_context()
            
            # Build messages for AI
            messages = await self.context_manager.build_messages(user_text, context)
            
            # Call Groq AI
            logger.info("Calling Groq AI...")
            groq = await self._ensure_groq()
            ai_response = await groq.chat(messages)
            
            if not ai_response:
                logger.error("Empty response from Groq AI")
                response_text = "Sorry, I couldn't process that."
                await self.tts.speak(response_text)
                return response_text
            
            # Parse AI response
            intent = ai_response.get("intent", "unknown")
            commands = ai_response.get("commands", [])
            response_text = ai_response.get("response", "Done")
            update_context = ai_response.get("update_context", True)
            
            logger.info(f"AI INTENT: {intent}")
            logger.info(f"AI COMMANDS: {len(commands)}")
            logger.info(f"AI RESPONSE: {response_text}")
            
            # Execute commands concurrently if any
            if commands:
                # Execute commands first to get ESP32/system responses
                execution_results = await self.executor.execute_multiple(commands)
                
                # Check for ESP32 responses and enhance AI response
                esp32_responses = [r.get("response_data") for r in execution_results if r.get("response_data")]
                if esp32_responses:
                    esp32_feedback = esp32_responses[0]
                    logger.info(f"📡 ESP32 Response: {esp32_feedback}")
                    
                    # Ask AI to generate a better response based on ESP32 feedback
                    enhanced_response = await self._enhance_response_with_feedback(
                        user_text, 
                        response_text, 
                        esp32_feedback
                    )
                    response_text = enhanced_response if enhanced_response else response_text
                
                # Check for failures and update response
                failed = [r for r in execution_results if not r.get("success", False)]
                if failed:
                    logger.warning(f"Command execution failures: {failed}")
                    # Check if it's a connection error
                    errors = [r.get("error") for r in failed if r.get("error")]
                    if any("Connection failed" in str(e) or "Timeout" in str(e) for e in errors):
                        response_text = "I couldn't reach the ESP32. Please check if it's powered on and connected to the network."
                
                # Speak the (possibly enhanced) response
                await self.tts.speak(response_text)
            else:
                # No commands, just respond
                await self.tts.speak(response_text)
            
            # Update context if needed
            if update_context:
                await self.context_manager.update_context(
                    user_message=user_text,
                    ai_response=ai_response
                )
            
            # Keep conversation alive if expecting followup
            expecting_followup = ai_response.get("expecting_followup", False)
            response_text_lower = response_text.lower()
            
            # Smart detection: only auto-listen if response actually asks a question
            has_question = any(phrase in response_text_lower for phrase in [
                "would you like", "do you want", "should i", "can i help",
                "which one", "what would you prefer", "need anything else",
                "how can i help"
            ])
            
            if expecting_followup and has_question:
                logger.info("🔄 Expecting followup (question detected) - will auto-listen for response")
                # AUTO-LISTEN for follow-up without requiring wake word!
                await self._auto_listen_for_followup()
            else:
                # Conversation complete - no auto-listen
                if expecting_followup and not has_question:
                    logger.info("⚠️ AI set expecting_followup=true but no question asked - skipping auto-listen")
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

