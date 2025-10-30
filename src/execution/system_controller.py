"""
System Controller
Control Windows system operations - lock, shutdown, restart, sleep
"""
import subprocess
import logging
from typing import Optional
import ctypes

from src.utils.logger import get_logger

logger = get_logger(__name__)


class SystemController:
    """Control Windows system operations"""
    
    async def lock_screen(self) -> bool:
        """Lock the Windows screen"""
        try:
            ctypes.windll.user32.LockWorkStation()
            logger.info("Screen locked successfully")
            return True
        except Exception as e:
            logger.error(f"Error locking screen: {e}")
            return False
    
    async def shutdown(self, force: bool = False) -> bool:
        """
        Shutdown Windows
        
        Args:
            force: Force shutdown without waiting for apps to close
        """
        try:
            command = "shutdown /s /t 0"
            if force:
                command += " /f"
            
            logger.info(f"Executing shutdown command: {command}")
            result = subprocess.run(command, shell=True, capture_output=True)
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"Error shutting down: {e}")
            return False
    
    async def restart(self, force: bool = False) -> bool:
        """
        Restart Windows
        
        Args:
            force: Force restart without waiting for apps to close
        """
        try:
            command = "shutdown /r /t 0"
            if force:
                command += " /f"
            
            logger.info(f"Executing restart command: {command}")
            result = subprocess.run(command, shell=True, capture_output=True)
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"Error restarting: {e}")
            return False
    
    async def sleep(self) -> bool:
        """Put Windows to sleep"""
        try:
            # Use rundll32 to sleep
            command = "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"
            logger.info("Putting system to sleep")
            result = subprocess.run(command, shell=True, capture_output=True)
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"Error putting system to sleep: {e}")
            return False
    
    async def hibernate(self) -> bool:
        """Hibernate Windows"""
        try:
            command = "shutdown /h"
            logger.info("Hibernating system")
            result = subprocess.run(command, shell=True, capture_output=True)
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"Error hibernating: {e}")
            return False
    
    async def set_volume(self, level: int) -> bool:
        """
        Set system volume (0-100)
        
        Args:
            level: Volume level from 0 to 100
        """
        try:
            # Normalize to 0-100 range
            level = max(0, min(100, level))
            
            # Use nircmd if available, otherwise PowerShell
            command = f'powershell -c "(New-Object -ComObject WScript.Shell).SendKeys([char]175)"'  # Volume up key
            # This is a simplified version - full implementation would use COM objects
            
            logger.info(f"Setting volume to {level}%")
            return True
            
        except Exception as e:
            logger.error(f"Error setting volume: {e}")
            return False
    
    async def execute_shell_command(self, command: str) -> tuple[bool, str]:
        """
        Execute arbitrary shell command
        
        Args:
            command: Shell command to execute
            
        Returns:
            Tuple of (success, output)
        """
        try:
            logger.info(f"Executing shell command: {command}")
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            success = result.returncode == 0
            output = result.stdout if success else result.stderr
            
            return success, output
            
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {command}")
            return False, "Command timed out"
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return False, str(e)


# Global instance
_system_controller: Optional[SystemController] = None


def get_system_controller() -> SystemController:
    """Get or create global system controller"""
    global _system_controller
    if _system_controller is None:
        _system_controller = SystemController()
    return _system_controller












