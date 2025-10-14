"""
Process Manager
Kill and manage Windows processes dynamically
"""
import subprocess
import logging
from typing import Optional, List
import psutil

from src.utils.logger import get_logger

logger = get_logger(__name__)


class ProcessManager:
    """Manage Windows processes - kill, list, monitor"""
    
    def __init__(self):
        self.process_name_mappings = {
            "chrome": "chrome.exe",
            "google chrome": "chrome.exe",
            "firefox": "firefox.exe",
            "edge": "msedge.exe",
            "notepad": "notepad.exe",
            "vscode": "Code.exe",
            "vs code": "Code.exe",
            "visual studio code": "Code.exe",
            "spotify": "Spotify.exe",
            "discord": "Discord.exe",
            "python": "python.exe",
            "pythonw": "pythonw.exe",
            "cmd": "cmd.exe",
            "powershell": "powershell.exe",
            "explorer": "explorer.exe",
            "calculator": "CalculatorApp.exe",
            "calc": "CalculatorApp.exe",
        }
    
    async def kill_process(self, process_name: str) -> bool:
        """
        Kill process by name
        
        Args:
            process_name: Name of process to kill
            
        Returns:
            True if process was killed successfully
        """
        process_name = process_name.lower().strip()
        
        # Map common names to actual process names
        actual_name = self.process_name_mappings.get(process_name, process_name)
        
        # Ensure .exe extension
        if not actual_name.endswith('.exe'):
            actual_name = f"{actual_name}.exe"
        
        try:
            # First, check if process is running
            if not await self._is_process_running(actual_name):
                logger.info(f"Process {actual_name} is not running")
                return False
            
            # Use taskkill command
            command = f"taskkill /F /IM {actual_name}"
            logger.info(f"Executing: {command}")
            
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info(f"Successfully killed process: {actual_name}")
                return True
            else:
                logger.warning(f"Failed to kill {actual_name}: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error killing process {process_name}: {e}")
            return False
    
    async def _is_process_running(self, process_name: str) -> bool:
        """Check if process is currently running"""
        try:
            for proc in psutil.process_iter(['name']):
                if proc.info['name'].lower() == process_name.lower():
                    return True
            return False
        except Exception as e:
            logger.error(f"Error checking if process running: {e}")
            return False
    
    async def get_running_processes(self) -> List[dict]:
        """Get list of running processes"""
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    processes.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return processes
        except Exception as e:
            logger.error(f"Error getting running processes: {e}")
            return []
    
    async def kill_process_by_pid(self, pid: int) -> bool:
        """Kill process by PID"""
        try:
            command = f"taskkill /F /PID {pid}"
            result = subprocess.run(command, shell=True, capture_output=True)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error killing process {pid}: {e}")
            return False


# Global instance
_process_manager: Optional[ProcessManager] = None


def get_process_manager() -> ProcessManager:
    """Get or create global process manager"""
    global _process_manager
    if _process_manager is None:
        _process_manager = ProcessManager()
    return _process_manager





