"""
UPS Event Handler - Integrates UPS monitoring with Aiden's voice system
Handles power loss alerts, battery warnings, and shutdown coordination
"""
import asyncio
import platform
import subprocess
from typing import Optional

from src.speech.stt import get_stt_engine
from src.speech.tts import get_tts_engine
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class UPSEventHandler:
    """
    Handles UPS events and coordinates with Aiden assistant
    
    Provides cool voice alerts and smart shutdown logic
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.tts = get_tts_engine()
        self.shutdown_task = None
        self.waiting_for_response = False
        
        logger.info("UPS Event Handler initialized")
    
    async def handle_power_lost(self):
        """
        Handle power loss - immediate engagement
        
        Ask user right away if they want to shutdown or need time
        """
        logger.info("🔋 Power loss detected - asking user immediately")
        
        # Play warning sound before speaking
        await self.tts.play_sound("warning")

        # Immediate engagement - ask right away
        message = (
            f"Sir, we've lost power. We're running on UPS battery. "
            f"Should I shut down the system now to be safe, or do you need time to save your work?"
        )

        await self.tts.speak(message)
        
        # Mark waiting for response
        self.waiting_for_response = True
        
        # Inject context so the LLM knows what we just asked
        from src.core.context_manager import get_context_manager
        ctx = get_context_manager()
        await ctx.inject_assistant_message(message, expecting_followup=True)

        # Open follow-up listening after the warning finishes speaking
        asyncio.create_task(self._trigger_auto_listen())
        
        # Start timeout for no response (30 seconds)
        self.shutdown_task = asyncio.create_task(
            self._initial_response_timeout()
        )
        
        logger.info("Waiting for immediate response (30s timeout)")
    
    async def handle_battery_alert(self, elapsed_minutes: int):
        """
        Handle 2-minute alert
        
        Args:
            elapsed_minutes: Minutes elapsed on battery power
        """
        logger.info(f"⚠️ 2-minute alert: {elapsed_minutes} minutes on battery")
        
        # Play warning sound before speaking
        await self.tts.play_sound("warning")

        message = (
            f"Sir, you've had {elapsed_minutes} minutes on battery. "
            f"I need to know - should I shut down now?"
        )

        await self.tts.speak(message)
        
        # Mark that we're waiting for response
        self.waiting_for_response = True
        
        # Inject context so the LLM knows what we just asked
        from src.core.context_manager import get_context_manager
        ctx = get_context_manager()
        await ctx.inject_assistant_message(message, expecting_followup=True)

        # Open follow-up listening after the warning finishes speaking
        asyncio.create_task(self._trigger_auto_listen())
        
        logger.info("Waiting for user response (2 minutes until force shutdown)")
    
    async def handle_battery_critical(self, elapsed_minutes: int):
        """
        Handle battery critical (no longer used - kept for backwards compatibility)
        The 3-minute warning has been removed. Now we just:
        - Ask immediately on power loss
        - Check in at 2 minutes
        - Force shutdown at 4 minutes
        
        Args:
            elapsed_minutes: Minutes elapsed on battery power
        """
        logger.warning(f"handle_battery_critical called but no longer used (elapsed: {elapsed_minutes} min)")
        pass
    
    async def handle_shutdown_request(self, force: bool = False, reason: str = "unknown"):
        """
        Handle shutdown request
        
        Args:
            force: Force shutdown without confirmation
            reason: Reason for shutdown
        """
        logger.warning(f"🔌 Shutdown requested (force={force}, reason={reason})")
        
        self.waiting_for_response = False
        
        # Cancel timeout task
        if self.shutdown_task:
            self.shutdown_task.cancel()
            self.shutdown_task = None

        # Play error sound for forced shutdown, success for user-confirmed
        if force:
            await self.tts.play_sound("error")
        else:
            await self.tts.play_sound("success")

        # Cool shutdown message
        if force and reason == "critical_voltage":
            message = (
                "Sir, battery voltage is critically low. "
                "I'm forcing an emergency shutdown to protect the system. "
                "Initiating shutdown now."
            )
        elif force and reason == "timeout":
            message = (
                "Sir, it's been 4 minutes on battery with no response. "
                "Forcing shutdown to protect your data. "
                "Goodbye, Sir."
            )
        elif force and reason == "critical_battery":
            message = (
                "I'm forcing the system down to avoid data corruption. "
                "All unsaved work will be lost. "
                "Initiating shutdown now."
            )
        else:
            message = (
                "Understood, Sir. "
                "Initiating graceful shutdown. "
                "See you on the other side."
            )

        await self.tts.speak(message)
        
        # Give TTS time to finish
        await asyncio.sleep(1)
        
        # Execute shutdown
        await self._execute_shutdown()

    async def handle_power_restored(self):
        """Handle mains power returning while UPS protection is active."""
        logger.info("⚡ Power restored callback received - clearing UPS shutdown state")

        self._clear_waiting_state()

        abort_result = self._abort_pending_shutdown()
        if abort_result is True:
            logger.info("✅ Pending Windows shutdown aborted after power restore")
        elif abort_result is False:
            logger.info("No pending Windows shutdown to abort after power restore")

        await self.tts.play_sound("success")

        message = "Power is back online, Sir. Abort sequence confirmed."
        await self.tts.speak(message)

        try:
            from src.core.context_manager import get_context_manager

            ctx = get_context_manager()
            await ctx.inject_assistant_message(message, expecting_followup=False)
        except Exception as e:
            logger.error(f"Failed to inject power restore context: {e}", exc_info=True)
    
    async def _trigger_auto_listen(self):
        """
        Trigger the assistant to listen for user response after asking a question
        """
        try:
            # Wait for the question to finish speaking before listening
            await self.tts.wait_until_done(timeout=10.0)
            await asyncio.sleep(0.3)

            stt = get_stt_engine()
            success, user_text, error = await stt.transcribe(play_activation_sound=True)

            if not success:
                if error == "timeout":
                    logger.info("No UPS follow-up response detected before listen timeout")
                else:
                    logger.warning(f"UPS follow-up STT failed: {error}")
                return

            transcript = (user_text or "").strip()
            if not transcript:
                logger.info("UPS follow-up produced an empty transcript")
                return

            logger.info(f"UPS follow-up transcript: '{transcript}'")

            decision = self._interpret_shutdown_response(transcript)
            if decision is None:
                logger.warning(f"Ignoring unrelated UPS follow-up transcript: '{transcript}'")
                return

            self.user_confirmed_shutdown(decision)
        
        except Exception as e:
            logger.error(f"Failed to trigger auto-listen: {e}", exc_info=True)

    def _interpret_shutdown_response(self, transcript: str) -> Optional[bool]:
        """Interpret a UPS shutdown follow-up as yes or no."""
        normalized = " ".join((transcript or "").lower().split())
        if not normalized:
            return None

        positive_phrases = (
            "yes",
            "yeah",
            "yep",
            "sure",
            "do it",
            "go ahead",
            "shut down",
            "shutdown",
            "turn it off",
            "power it off",
            "proceed",
            "confirm",
            "okay shut down",
            "ok shut down",
        )
        negative_phrases = (
            "no",
            "nope",
            "don't",
            "do not",
            "not now",
            "wait",
            "cancel",
            "abort",
            "keep running",
            "keep it on",
            "stay on",
            "i need time",
            "give me time",
        )

        if any(phrase in normalized for phrase in negative_phrases):
            return False

        if any(phrase in normalized for phrase in positive_phrases):
            return True

        return None
    
    async def _shutdown_timeout(self, timeout_seconds: int):
        """
        Timeout handler - no longer used with time-based system
        
        Time-based alerts handle the countdown automatically
        """
        pass
    
    async def _initial_response_timeout(self):
        """
        Handle no response to initial power loss question (30 seconds)
        No longer triggers immediate action - user has until 4-minute mark
        """
        try:
            await asyncio.sleep(30)
            
            # If still waiting for response, just log it
            if self.waiting_for_response:
                logger.info("No response to initial question - user has until 4-minute mark")
        
        except asyncio.CancelledError:
            logger.info("Initial timeout cancelled (user responded)")

    def _clear_waiting_state(self):
        """Clear any in-memory UPS response state."""
        self.waiting_for_response = False

        if self.shutdown_task:
            self.shutdown_task.cancel()
            self.shutdown_task = None

    def _abort_pending_shutdown(self) -> Optional[bool]:
        """
        Abort a pending Windows shutdown countdown.

        Returns:
            True if a shutdown countdown was aborted,
            False if no shutdown was pending,
            None if shutdown abort is unsupported on this platform.
        """
        if platform.system() != "Windows":
            logger.info("Shutdown abort skipped - only supported on Windows")
            return None

        try:
            result = subprocess.run(
                ["shutdown", "/a"],
                capture_output=True,
                text=True
            )
        except Exception as e:
            logger.error(f"Failed to abort pending shutdown: {e}", exc_info=True)
            return False

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        output = stdout or stderr

        if result.returncode == 0:
            logger.info("Windows shutdown abort command completed successfully")
            return True

        lowered_output = output.lower()
        if "no shutdown was in progress" in lowered_output:
            logger.info("Windows reported no shutdown was in progress")
            return False

        logger.warning(f"Shutdown abort command returned {result.returncode}: {output or 'no output'}")
        return False
    
    async def _execute_shutdown(self):
        """Execute system shutdown"""
        try:
            logger.critical("🔌 EXECUTING SYSTEM SHUTDOWN")
            
            # Windows shutdown command
            if platform.system() == "Windows":
                # Forced shutdown with 30 second warning so it still works from a locked session
                # Note: /c comment must be the last parameter
                result = subprocess.run(
                    ["shutdown", "/s", "/f", "/t", "30", "/c", "Aiden: UPS battery low - shutting down to protect data"],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    logger.info("✅ Shutdown command executed successfully")
                else:
                    logger.error(f"Shutdown command failed: {result.stderr}")
                    # Try simpler command without comment
                    logger.info("Retrying shutdown without comment...")
                    subprocess.run(["shutdown", "/s", "/f", "/t", "30"], check=True)
            else:
                logger.error("Shutdown only supported on Windows")
        
        except Exception as e:
            logger.error(f"Failed to execute shutdown: {e}", exc_info=True)
            # Last resort - immediate shutdown without comment
            try:
                logger.warning("Attempting immediate shutdown as fallback...")
                subprocess.run(["shutdown", "/s", "/f", "/t", "0"], check=False)
            except Exception as fallback_error:
                logger.error(f"Fallback shutdown also failed: {fallback_error}")
    
    def user_confirmed_shutdown(self, confirmed: bool):
        """
        User confirmed or cancelled shutdown via voice command
        
        Args:
            confirmed: True to proceed, False to cancel
        """
        if not self.waiting_for_response:
            logger.warning("Not waiting for shutdown confirmation")
            return
        
        self._clear_waiting_state()
        
        if confirmed:
            logger.info("✅ User confirmed shutdown")
            asyncio.create_task(
                self.handle_shutdown_request(force=False, reason="user_confirmed")
            )
        else:
            logger.info("❌ User cancelled shutdown - will monitor battery and force shutdown at critical level")
    
    def is_waiting_for_response(self) -> bool:
        """Check if handler is waiting for user response"""
        return self.waiting_for_response


# Global instance
_ups_handler: Optional[UPSEventHandler] = None


def get_ups_handler() -> UPSEventHandler:
    """Get or create global UPS handler instance"""
    global _ups_handler
    if _ups_handler is None:
        _ups_handler = UPSEventHandler()
    return _ups_handler
