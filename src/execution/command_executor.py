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
from src.database.neon_client import get_db_client
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
        self.esp32_client = None
        self.wake_word_manager = None
    
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
                
                case "fan_control":
                    success, response_data = await self._handle_fan_control(params)
                
                case "wake_word_control":
                    success = await self._handle_wake_word_control(params)
                
                case "shell_command":
                    success, error_message = await self._handle_shell_command(params)
                
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
    
    async def _handle_launch_app(self, params: Dict[str, Any]) -> bool:
        """Handle app launch command"""
        # Accept multiple parameter names for compatibility
        app_name = params.get("name") or params.get("app_name") or params.get("app") or params.get("application", "")
        if not app_name:
            logger.error(f"No app name provided in params: {params}")
            return False
        
        logger.info(f"Launching app: {app_name}")
        return await self.app_launcher.launch(app_name)
    
    async def _handle_kill_process(self, params: Dict[str, Any]) -> bool:
        """
        Handle process kill command with validation
        Checks if process is running before attempting to kill
        """
        process_name = params.get("name", "")
        if not process_name:
            logger.error("No process name provided")
            return False
        
        # Check if process is running before attempting to kill
        from src.utils.system_context import get_system_context
        sys_ctx = get_system_context()
        running_processes = await sys_ctx.get_running_processes(simplified=True)
        
        # Normalize process name for comparison
        process_name_lower = process_name.lower()
        
        # running_processes is a list of dicts: [{"name": "chrome.exe", "pid": 1234, "status": "running"}, ...]
        is_running = any(proc.get("name", "").lower() == process_name_lower for proc in running_processes)
        
        if not is_running:
            logger.warning(f"Process {process_name} is not running - skipping kill command")
            return True  # Return True to avoid error message (process already not running = success)
        
        logger.info(f"Process {process_name} is running - proceeding to kill")
        return await self.process_manager.kill_process(process_name)
    
    async def _handle_system_command(self, params: Dict[str, Any]) -> bool:
        """Handle system command (lock, shutdown, restart, sleep)"""
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
            case _:
                logger.error(f"Unknown system action: {action}")
                return False
    
    async def _handle_fan_control(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Handle ESP32 fan control command"""
        if not self.esp32_client:
            logger.warning("ESP32 client not configured - fan control unavailable")
            logger.info("To enable fan control, configure ESP32 settings in .env file")
            return False, None
        
        operation = params.get("operation", "").lower()
        
        match operation:
            case "on" | "turn_on" | "increase" | "speed_up" | "faster" | "high":
                # /on endpoint - cycles through speeds (1 → 2 → 3)
                success, response = await self.esp32_client.turn_on()
                return success, response
            case "off" | "turn_off" | "stop":
                # /off endpoint
                success, response = await self.esp32_client.turn_off()
                return success, response
            case "mode" | "change_mode" | "switch_mode":
                # /mode endpoint
                success, response = await self.esp32_client.change_mode()
                return success, response
            case _:
                logger.error(f"Unknown fan operation: {operation}")
                return False, None
    
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
    
    async def _handle_shell_command(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Handle arbitrary shell command"""
        command = params.get("command", "")
        if not command:
            logger.error("No shell command provided")
            return False, "No command provided"
        
        return await self.system_controller.execute_shell_command(command)


# Global instance
_command_executor: Optional[CommandExecutor] = None


def get_command_executor() -> CommandExecutor:
    """Get or create global command executor"""
    global _command_executor
    if _command_executor is None:
        _command_executor = CommandExecutor()
    return _command_executor



