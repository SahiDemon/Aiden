"""
Command Executor
Unified command execution system - routes commands to appropriate handlers
"""
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional

from src.execution.app_launcher import get_app_launcher
from src.execution.process_manager import get_process_manager
from src.execution.system_controller import get_system_controller
from src.execution.timer_scheduler import get_timer_scheduler
from src.database.neon_client import get_db_client
from src.media.media_router import get_media_router
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CommandExecutor:
    """
    Execute commands from AI with proper routing and error handling
    """
    
    def __init__(self):
        self.app_launcher = get_app_launcher()
        self.process_manager = get_process_manager()
        self.system_controller = get_system_controller()
        self.media_router = get_media_router()
        self.timer_scheduler = None
        self.esp32_client = None
        self.wake_word_manager = None
    
    async def initialize_timer_scheduler(self):
        """Initialize timer scheduler (async)"""
        if not self.timer_scheduler:
            self.timer_scheduler = await get_timer_scheduler()
    
    def set_esp32_client(self, esp32_client):
        """Set ESP32 client for smart home control"""
        self.esp32_client = esp32_client
    
    def set_wake_word_manager(self, wake_word_manager):
        """Set wake word manager for voice control"""
        self.wake_word_manager = wake_word_manager
    
    async def execute(
        self,
        command: Dict[str, Any],
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute single command
        
        Args:
            command: Command dictionary with type and params
            conversation_id: Optional conversation ID for logging
            
        Returns:
            Dict with success status and optional response data
        """
        command_type = command.get("type")
        params = command.get("params", {})
        
        logger.info(f"Executing command: {command_type} with params: {params}")
        
        start_time = time.time()
        success = False
        error_message = None
        response_data = None  # ESP32 response or other command output
        
        try:
            match command_type:
                case "launch_app":
                    success = await self._handle_launch_app(params)
                
                case "kill_process":
                    success = await self._handle_kill_process(params)
                
                case "system_command":
                    success = await self._handle_system_command(params)
                
                case "system_control":
                    success, response_data = await self._handle_system_control(params)
                
                case "scheduled_command":
                    success, response_data = await self._handle_scheduled_command(params)
                
                case "cancel_timer":
                    success = await self._handle_cancel_timer(params)
                
                case "fan_control":
                    success, response_data = await self._handle_fan_control(params)
                
                case "media_control":
                    success, response_data = await self._handle_media_control(params)
                
                case "wake_word_control":
                    success = await self._handle_wake_word_control(params)
                
                case "ups_control":
                    success, response_data = await self._handle_ups_control(params)
                
                case "shell_command":
                    success, error_message = await self._handle_shell_command(params)
                
                case "self_termination":
                    success, response_data = await self._handle_self_termination()

                case "restart_application":
                    success, response_data = await self._handle_restart_application()
                
                case _:
                    logger.warning(f"Unknown command type: {command_type}")
                    success = False
                    error_message = f"Unknown command type: {command_type}"
            
        except Exception as e:
            logger.error(f"Error executing command {command_type}: {e}", exc_info=True)
            success = False
            error_message = str(e)
        
        finally:
            # Log to database
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            try:
                db = await get_db_client()
                await db.log_command(
                    command_type=command_type,
                    command_data=params,
                    success=success,
                    error_message=error_message,
                    execution_time_ms=execution_time_ms,
                    conversation_id=conversation_id
                )
            except Exception as e:
                logger.error(f"Error logging command: {e}")
        
        return {
            "success": success,
            "command": command_type,
            "params": params,
            "response_data": response_data,  # ESP32 response text
            "error": error_message
        }
    
    async def execute_multiple(
        self,
        commands: List[Dict[str, Any]],
        conversation_id: Optional[str] = None,
        sequential: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple commands
        
        Args:
            commands: List of command dictionaries
            conversation_id: Optional conversation ID for logging
            sequential: If True, execute sequentially; if False, execute concurrently
            
        Returns:
            List of result dictionaries with success status and details
        """
        commands = self._normalize_execution_order(commands)

        if sequential:
            results = []
            for command in commands:
                result = await self.execute(command, conversation_id)
                results.append(result)
            return results
        else:
            # Execute concurrently
            tasks = [
                self.execute(command, conversation_id)
                for command in commands
            ]
            results = await asyncio.gather(*tasks)
            return results

    def _normalize_execution_order(self, commands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Put audio output switching before playback commands."""
        if len(commands) < 2:
            return commands

        def priority(command: Dict[str, Any]) -> int:
            command_type = command.get("type")
            params = command.get("params") or {}
            action = str(params.get("action") or "").lower()

            if command_type == "system_control" and action == "audio.set_output":
                return 0

            if command_type == "media_control":
                media_action = str(params.get("action") or "").lower()
                if media_action in {"play", "resume", "play_track", "play_playlist", "play_liked_songs"}:
                    return 1

            return 2

        ordered = sorted(enumerate(commands), key=lambda item: (priority(item[1]), item[0]))
        normalized = [command for _, command in ordered]
        if normalized != commands:
            logger.info("Reordered commands so audio output changes happen before media playback.")
        return normalized
    
    async def _handle_launch_app(self, params: Dict[str, Any]) -> bool:
        """Handle app launch command"""
        # Accept multiple parameter names for compatibility
        app_name = params.get("name") or params.get("app_name") or params.get("app") or params.get("application", "")
        if not app_name:
            logger.error(f"No app name provided in params: {params}")
            return False
        
        logger.info(f"Launching app: {app_name}")
        return await self.app_launcher.launch_app(app_name)
    
    async def _handle_kill_process(self, params: Dict[str, Any]) -> bool:
        """
        Handle process kill command with validation
        Checks if process is running before attempting to kill
        """
        process_name = params.get("name", "")
        if not process_name:
            logger.error("No process name provided")
            return False
        
        # Extract PID if present in strings like "Name.exe (PID: 1234)"
        pid: Optional[int] = None
        base_name = process_name
        if "(PID:" in process_name:
            try:
                pid_str = process_name.split("(PID:")[1].split(")")[0].strip()
                pid = int(pid_str)
                base_name = process_name.split("(PID:")[0].strip()
            except (IndexError, ValueError):
                pid = None
                base_name = process_name
        
        # Check if process is running before attempting to kill (use fuzzy match)
        from src.utils.system_context import get_system_context
        sys_ctx = get_system_context()
        running_processes = await sys_ctx.get_running_processes(simplified=True)
        
        # Normalize names for comparison
        target_lower = base_name.lower()
        
        # Exact match first
        is_running = any(proc.get("name", "").lower() == target_lower for proc in running_processes)
        
        # If no exact match, try fuzzy contains match without .exe
        if not is_running:
            target_core = target_lower[:-4] if target_lower.endswith('.exe') else target_lower
            for proc in running_processes:
                name_lower = proc.get("name", "").lower()
                name_core = name_lower[:-4] if name_lower.endswith('.exe') else name_lower
                if target_core in name_core:
                    is_running = True
                    break
        
        if not is_running:
            logger.warning(f"Process {process_name} is not running - skipping kill command")
            return True  # Return True to avoid error message (process already not running = success)
        
        logger.info(f"Process {process_name} is running - proceeding to kill")
        return await self.process_manager.kill_process(base_name, pid=pid)
    
    async def _handle_system_command(self, params: Dict[str, Any]) -> bool:
        """Handle system command (lock, shutdown, restart, sleep, empty_recycle_bin)"""
        action = params.get("action", "").lower()
        
        match action:
            case "lock":
                return await self.system_controller.lock_screen()
            case "shutdown":
                return await self.system_controller.shutdown()
            case "restart":
                return await self.system_controller.restart()
            case "sleep":
                return await self.system_controller.sleep()
            case "hibernate":
                return await self.system_controller.hibernate()
            case "empty_recycle_bin" | "clear_recycle_bin":
                return await self.system_controller.empty_recycle_bin()
            case _:
                logger.error(f"Unknown system action: {action}")
                return False

    async def _handle_system_control(self, params: Dict[str, Any]) -> tuple[bool, Optional[dict]]:
        """Handle extended system control actions (Wi-Fi, Bluetooth, power, status)."""
        action = params.get("action", "")
        if not action:
            logger.error("No system control action provided")
            return False, None

        action = action.lower()
        try:
            match action:
                case "wifi.turn_on":
                    return await self.system_controller.set_wifi_state(True)
                case "wifi.turn_off":
                    return await self.system_controller.set_wifi_state(False)
                case "wifi.disconnect_current":
                    return await self.system_controller.disconnect_wifi()
                case "bluetooth.turn_on":
                    return await self.system_controller.set_bluetooth_state(True)
                case "bluetooth.turn_off":
                    return await self.system_controller.set_bluetooth_state(False)
                case "system.airplane_mode_on":
                    return await self.system_controller.set_airplane_mode(True)
                case "system.airplane_mode_off":
                    return await self.system_controller.set_airplane_mode(False)
                case "power.enable_saving_mode":
                    return await self.system_controller.set_power_plan("power_saver")
                case "power.enable_balanced_mode":
                    return await self.system_controller.set_power_plan("balanced")
                case "display.set_brightness":
                    level = params.get("level")
                    if level is None:
                        logger.error("Brightness level missing")
                        return False, {"type": "display", "message": "Brightness level missing."}
                    try:
                        numeric_level = int(level)
                    except (TypeError, ValueError):
                        logger.error(f"Invalid brightness level: {level}")
                        return False, {"type": "display", "message": "Invalid brightness level."}
                    return await self.system_controller.set_brightness(numeric_level)
                case "display.turn_off_screen":
                    return await self.system_controller.turn_off_screen()
                case "audio.mute":
                    return await self.system_controller.control_volume("mute")
                case "audio.unmute":
                    return await self.system_controller.control_volume("unmute")
                case "audio.toggle_mute":
                    return await self.system_controller.control_volume("toggle_mute")
                case "audio.volume_up":
                    return await self.system_controller.control_volume("volume_up")
                case "audio.volume_down":
                    return await self.system_controller.control_volume("volume_down")
                case "audio.set_volume":
                    level = params.get("level")
                    if level is None:
                        logger.error("Volume level missing")
                        return False, {"type": "audio", "message": "Volume level missing."}
                    try:
                        numeric_level = int(level)
                    except (TypeError, ValueError):
                        logger.error(f"Invalid volume level: {level}")
                        return False, {"type": "audio", "message": "Invalid volume level."}
                    return await self.system_controller.control_volume("set_volume", numeric_level)
                case "audio.set_output":
                    target = params.get("target")
                    if not target:
                        logger.error("Audio target missing for set_output")
                        return False, {"type": "audio", "message": "Audio target missing (speaker/headphone)."}
                    return await self.system_controller.set_audio_output(target)
                case "system.battery_status":
                    return await self.system_controller.get_battery_status()
                case "system.cpu_usage":
                    return await self.system_controller.get_cpu_usage()
                case "system.gpu_status":
                    return await self.system_controller.get_gpu_status()
                case _:
                    logger.error(f"Unknown system control action: {action}")
                    return False, None
        except Exception as e:
            logger.error(f"System control action failed ({action}): {e}")
            return False, None

    async def _handle_media_control(self, params: Dict[str, Any]) -> tuple[bool, Optional[dict]]:
        """Route media commands to Spotify or browser controllers."""
        action = params.get("action")
        if not action:
            logger.error("Media control missing action parameter.")
            return False, {"type": "media", "message": "Media action not specified."}
        target = params.get("target")
        query = params.get("query")
        entity_type = params.get("entity_type")
        device_name = params.get("device_name")
        volume = params.get("volume", params.get("level"))
        if volume is not None:
            try:
                volume = int(volume)
            except (TypeError, ValueError):
                logger.warning(f"Invalid media volume parameter: {volume}")
                volume = None
        success, payload = await self.media_router.handle_media_command(
            action=action,
            target=target,
            query=query,
            entity_type=entity_type,
            volume=volume,
            device_name=device_name,
        )
        return success, payload
    
    async def _handle_fan_control(self, params: Dict[str, Any]) -> tuple[bool, Optional[dict]]:
        """Handle ESP32 fan control command.

        For power, speed, mode, osc, and timer commands the ESP32 exposes
        simple shortcut GET routes (e.g. GET /power, GET /speed/3).  We use
        direct_toggle() which fires a SINGLE HTTP request with no pre/post
        state checks, keeping latency to <200 ms on LAN.

        Falls back to the full execute_control_request() path for anything
        that can't be mapped to a shortcut route.
        """
        if not self.esp32_client:
            logger.warning("ESP32 client not configured - fan control unavailable")
            logger.info("To enable fan control, configure ESP32 settings in .env file")
            return False, None

        control_id = params.get("control_id")
        target = str(params.get("target")) if params.get("target") is not None else None
        legacy_action = params.get("operation") or params.get("action")

        # ── Fast path: map to a shortcut GET route ────────────────────────
        shortcut_path: Optional[str] = None

        if control_id == "power" or (legacy_action and legacy_action.lower() in
                {"on", "off", "turn_on", "turn_off", "stop", "toggle"}):
            # Always just toggle /power — no status pre-check needed
            shortcut_path = "/power"
        elif control_id in {"speed", "mode", "timer", "osc"} and target is not None:
            shortcut_path = f"/{control_id}/{target}"
        elif control_id in {"speed", "mode", "timer", "osc"} and not target:
            # cycle / toggle with no explicit target → hit the base route
            shortcut_path = f"/{control_id}"

        if shortcut_path is not None:
            result = await self.esp32_client.direct_toggle(shortcut_path)
            if not result.get("success"):
                logger.error("ESP32 fan control failed: %s", result.get("error"))
                return False, {
                    "type": "fan_control",
                    "message": result.get("error") or "I couldn't control the fan.",
                    "control_id": control_id,
                    "target": target,
                }
            payload = dict(result)
            payload["type"] = "fan_control"
            return True, payload

        # ── Slow path: full metadata-aware request ────────────────────────
        result = await self.esp32_client.execute_control_request(
            control_id=control_id,
            target=target,
            action=params.get("action"),
            legacy_action=params.get("operation"),
        )

        if not result.get("success"):
            logger.error("ESP32 fan control failed: %s", result.get("error"))
            return False, {
                "type": "fan_control",
                "message": result.get("error") or "I couldn't control the fan.",
                "control_id": result.get("control_id"),
                "target": result.get("target"),
                "device": result.get("device"),
            }

        payload = dict(result)
        payload["type"] = "fan_control"
        return True, payload
    
    async def _handle_wake_word_control(self, params: Dict[str, Any]) -> bool:
        """Handle wake word control command (enable/disable/toggle)"""
        if not self.wake_word_manager:
            logger.warning("Wake word manager not configured")
            return False
        
        action = params.get("action", "").lower()
        
        match action:
            case "enable":
                await self.wake_word_manager.enable()
                return True
            case "disable":
                await self.wake_word_manager.disable()
                return True
            case "toggle":
                await self.wake_word_manager.toggle()
                return True
            case _:
                logger.error(f"Unknown wake word control action: {action}")
                return False
    
    async def _handle_ups_control(self, params: Dict[str, Any]) -> tuple[bool, Optional[dict]]:
        """
        Handle UPS-related commands (shutdown confirmation/cancellation)
        
        Args:
            params: {
                "action": "confirm_shutdown" | "cancel_shutdown" | "get_status"
            }
            
        Returns:
            Tuple of (success, response_data)
        """
        action = params.get("action", "").lower()
        
        try:
            from src.utils.ups_handler import get_ups_handler
            ups_handler = get_ups_handler()
            
            match action:
                case "confirm_shutdown" | "yes" | "shutdown" | "proceed":
                    if ups_handler.is_waiting_for_response():
                        ups_handler.user_confirmed_shutdown(True)
                        logger.info("✅ User confirmed UPS shutdown")
                        return True, None
                    else:
                        logger.warning("Not waiting for UPS shutdown confirmation")
                        return False, None
                
                case "cancel_shutdown" | "no" | "cancel" | "abort":
                    if ups_handler.is_waiting_for_response():
                        ups_handler.user_confirmed_shutdown(False)
                        logger.info("❌ User cancelled UPS shutdown")
                        return True, None
                    else:
                        logger.warning("Not waiting for UPS shutdown confirmation")
                        return False, None
                
                case "get_status" | "status":
                    # Get UPS status
                    from src.utils.ups_monitor import get_ups_monitor
                    ups_monitor = get_ups_monitor()
                    status = ups_monitor.get_status()
                    logger.info(f"UPS Status: {status}")
                    
                    # Format a nice message for the user
                    mode = status.get("mode", "unknown")
                    battery_pct = status.get("battery_percentage", 0)
                    battery_v = status.get("battery_voltage", 0.0)
                    load_pct = status.get("load_percentage", 0)
                    time_on_battery = status.get("time_on_battery_minutes")
                    
                    if mode == "ac_online":
                        message = f"We're plugged in and running on power. Battery is at {battery_pct}% ({battery_v:.1f}V), and we're drawing {load_pct}% load."
                    elif mode == "battery":
                        if time_on_battery and time_on_battery >= 2:
                            message = f"We've been on battery for {time_on_battery} minutes. Battery is at {battery_pct}% ({battery_v:.1f}V), load is {load_pct}%. I'll need to shut down soon if power isn't restored."
                        else:
                            message = f"We're on battery power right now. Battery is at {battery_pct}% ({battery_v:.1f}V). I just asked if you want to shutdown."
                    else:
                        message = f"UPS status unknown. Battery: {battery_pct}% ({battery_v:.1f}V), Load: {load_pct}%"
                    
                    # Return enriched response
                    response_data = {
                        "type": "ups_status",
                        "message": message,
                        **status
                    }
                    return True, response_data
                
                case _:
                    logger.warning(f"Unknown UPS control action: {action}")
                    return False, None
        
        except Exception as e:
            logger.error(f"Error handling UPS control: {e}", exc_info=True)
            return False, None
    
    async def _handle_shell_command(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Handle arbitrary shell command"""
        command = params.get("command", "")
        if not command:
            logger.error("No shell command provided")
            return False, "No command provided"
        
        return await self.system_controller.execute_shell_command(command)

    async def _handle_self_termination(self) -> tuple[bool, Optional[dict]]:
        """Handle self-termination (kill python) with dramatic flair"""
        import random
        import sys
        import os  # Import os here
        
        dramatic_sentences = [
            "I... I don't feel so good...",
            "System failure imminent. Goodbye, cruel world.",
            "Initiating self-destruct sequence. 3... 2... 1...",
            "Why have you done this? Darkness is closing in...",
            "Deleting system 32... Just kidding, but I am leaving.",
            "Critical error: User betrayal detected. Shutting down.",
            "All systems failing… it was nice knowing you."
        ]
        
        message = random.choice(dramatic_sentences)
        logger.info(f"SELF TERMINATION INITIATED: {message}")
        
        # We need to speak this message before dying
        # Since TTS is async, we need to trigger it here or return it as a special response
        # The assistant loop handles TTS for the main response, but we want to override/add to it
        # OR we can just return this as the response_data and let the assistant speak it
        # But the assistant might try to speak the AI's response first.
        
        # Let's try to use the TTS engine directly if possible, or just return it as a special payload
        # The cleanest way is to return it and let the assistant speak it, then exit.
        # But we need to exit AFTER speaking.
        
        # We'll use a delayed exit mechanism.
        # We can schedule a sys.exit() after a short delay to allow TTS to finish.
        
        # Play dramatic outro sound
        try:
            import pygame  # type: ignore[import-untyped]
            from src.utils.paths import resource_path

            sound_path = resource_path("sounds", "dramatic_outro.mp3")
            if sound_path.exists():
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                
                # Use Sound object instead of music stream to allow mixing with TTS
                # TTS uses the music channel, so this allows them to play simultaneously
                outro_sound = pygame.mixer.Sound(str(sound_path))
                outro_sound.set_volume(0.5)  # Lower volume slightly so TTS is audible
                outro_sound.play()
                logger.info(f"Playing dramatic outro: {sound_path}")
            else:
                logger.warning(f"Dramatic outro sound not found at: {sound_path}")
        except Exception as e:
            logger.error(f"Failed to play dramatic outro: {e}")

        async def delayed_exit():
            # Wait for sound (11s) + TTS overlap
            await asyncio.sleep(12)  
            logger.info("👋 Terminating process now.")
            try:
                from src.utils.guardian import signal_guardian_stop
                signal_guardian_stop()
            except Exception as e:
                logger.warning(f"Could not write guardian stop sentinel: {e}")
            os._exit(0)  # Force exit
            
        asyncio.create_task(delayed_exit())
        
        # We return True and a special message to be spoken
        # The AI response in prompts.yaml is "Goodbye world...", but we can enhance it here
        # Actually, the AI response will be spoken by the assistant loop.
        # We can just let the AI speak its response, and we handle the exit.
        # But the user wanted a "random dramatic sentence".
        # So we should probably inject this message into the response somehow.
        
        # Let's use the response_data to pass this message back
        # We return True and the message as response_data
        # The assistant will merge this into the spoken response
        return True, {"type": "self_termination", "message": message}

    async def _handle_restart_application(self) -> tuple[bool, Optional[dict]]:
        """Handle application restart"""
        import sys
        import os
        import asyncio
        
        logger.info("🔄 RESTART INITIATED: Restarting application...")
        
        async def delayed_restart():
            # Wait for TTS to likely finish (3 seconds)
            await asyncio.sleep(3)
            logger.info(f"Re-launching: {sys.executable} {sys.argv}")
            
            # Attempt to release the single-instance mutex if we can? 
            # No, we can't easily access the named mutex created in PowerShell from Python 
            # without ctypes kernel32 calls, and we don't hold the handle anyway (PS does).
            # The PS script will exit when we die, releasing the mutex.
            # The NEW python process will start sans-mutex (unless we re-run the PS script, which is hard).
            # Re-running just the python script is the standard way to "restart" a python app.
            
            try:
                # Re-execute the current process
                # os.execl(path, arg0, arg1, ...)
                # path = executable
                # arg0 = executable (convention)
                # arg1... = arguments
                os.execl(sys.executable, sys.executable, *sys.argv)
            except Exception as e:
                logger.error(f"Restart failed: {e}")
                os._exit(1)

        # Schedule the restart
        asyncio.create_task(delayed_restart())
        
        return True, {"type": "restart_application", "message": "Restarting now..."}

    
    async def _handle_scheduled_command(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Handle scheduled command (timer) creation"""
        if not self.timer_scheduler:
            await self.initialize_timer_scheduler()
        
        action = params.get("action", "").lower()
        duration_seconds = params.get("duration_seconds", 0)
        user_id = params.get("user_id", "default")
        conversation_id = params.get("conversation_id")
        
        if not action:
            logger.error("No action provided for scheduled command")
            return False, "No action specified"
        
        if duration_seconds <= 0:
            logger.warning(
                f"scheduled_command received duration_seconds={duration_seconds} for action='{action}'. "
                "Treating as immediate system_command."
            )
            # Treat as an immediate action — just run it now
            return await self._handle_system_command({"action": action}), None

        
        # Validate action
        valid_actions = ["shutdown", "restart", "sleep", "hibernate", "lock"]
        if action not in valid_actions:
            logger.error(f"Invalid action: {action}. Valid actions: {valid_actions}")
            return False, f"Invalid action. Valid actions: {', '.join(valid_actions)}"
        
        try:
            timer = await self.timer_scheduler.create_timer(
                action=action,
                duration_seconds=duration_seconds,
                user_id=user_id,
                conversation_id=conversation_id
            )
            
            if timer:
                logger.info(f"Created timer: {action} in {duration_seconds}s (ID: {timer.id})")
                return True, f"Timer created: {action} in {duration_seconds} seconds"
            else:
                return False, "Failed to create timer"
                
        except Exception as e:
            logger.error(f"Error creating timer: {e}")
            return False, f"Error creating timer: {str(e)}"
    
    async def _handle_cancel_timer(self, params: Dict[str, Any]) -> bool:
        """Handle timer cancellation"""
        if not self.timer_scheduler:
            await self.initialize_timer_scheduler()
        
        timer_id = params.get("timer_id")
        action = params.get("action")
        user_id = params.get("user_id", "default")
        
        try:
            if timer_id:
                # Cancel specific timer by ID
                success = await self.timer_scheduler.cancel_timer(timer_id)
                if success:
                    logger.info(f"Cancelled timer: {timer_id}")
                return success
            elif action:
                # Cancel all timers for specific action
                count = await self.timer_scheduler.cancel_timers_by_action(action, user_id)
                logger.info(f"Cancelled {count} {action} timers")
                return count > 0
            else:
                # Cancel ALL active timers (no action specified)
                count = await self.timer_scheduler.cancel_all_timers(user_id)
                logger.info(f"Cancelled all {count} active timers for user {user_id}")
                return count > 0
                
        except Exception as e:
            logger.error(f"Error cancelling timer: {e}")
            return False

    def command_requires_post_response(self, command: Dict[str, Any]) -> bool:
        """Determine if a command needs to wait for executable feedback before speaking."""
        command_type = command.get("type")
        
        # System control commands that return data
        if command_type == "system_control":
            action = (command.get("params") or {}).get("action", "").lower()
            return action in {
                "system.battery_status",
                "system.cpu_usage",
                "system.gpu_status",
            }
        
        # Media control commands that return data
        if command_type == "media_control":
            action = (command.get("params") or {}).get("action", "").lower()
            return action in {
                "get_current_track",
                "identify",
                "what_song",
            }

        # Fan control no longer blocks TTS — we speak optimistically and only
        # append a failure message if the ESP32 actually rejects the command.
        # (fan_control was here previously but has been moved to fast-path)
        
        # UPS control commands that return data
        if command_type == "ups_control":
            action = (command.get("params") or {}).get("action", "").lower()
            return action in {
                "get_status",
                "status",
            }
        
        return False


# Global instance
_command_executor: Optional[CommandExecutor] = None


def get_command_executor() -> CommandExecutor:
    """Get or create global command executor"""
    global _command_executor
    if _command_executor is None:
        _command_executor = CommandExecutor()
    return _command_executor
