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
    
    async def kill_process(self, process_name: str, pid: int = None) -> bool:
        """
        Kill process by name or PID
        
        Args:
            process_name: Name of process to kill (can include PID in format "name (PID: 1234)")
            pid: Optional PID to kill directly
            
        Returns:
            True if process was killed successfully
        """
        # Check if PID is embedded in process_name string (e.g., "Chrome.exe (PID: 1234)")
        if not pid and "(PID:" in process_name:
            try:
                # Extract PID from string like "Chrome.exe (PID: 1234)"
                pid_str = process_name.split("(PID:")[1].split(")")[0].strip()
                pid = int(pid_str)
                # Extract just the process name
                process_name = process_name.split("(PID:")[0].strip()
                logger.info(f"Extracted PID {pid} from process string")
            except (IndexError, ValueError) as e:
                logger.debug(f"Could not extract PID from string: {e}")
        
        # If we have a PID, use it directly (most reliable method)
        if pid:
            return await self.kill_process_by_pid(pid)
        
        process_name = process_name.lower().strip()
        
        try:
            # Use system context to find running processes
            from src.utils.system_context import get_system_context
            sys_ctx = get_system_context()
            matching_processes = await sys_ctx.find_process(process_name)
            
            if not matching_processes:
                # Fallback to legacy mapping
                actual_name = self.process_name_mappings.get(process_name, process_name)
                if not actual_name.endswith('.exe'):
                    actual_name = f"{actual_name}.exe"
                
                if not await self._is_process_running(actual_name):
                    logger.info(f"Process {process_name} is not running")
                    return False
                
                matching_processes = [{"name": actual_name, "pid": None}]
            
            # Kill all matching processes
            killed_any = False
            for proc in matching_processes:
                proc_pid = proc.get("pid")
                proc_name = proc.get("name", "")
                
                # Prefer killing by PID if available
                if proc_pid:
                    logger.info(f"Killing {proc_name} by PID {proc_pid}")
                    if await self.kill_process_by_pid(proc_pid):
                        killed_any = True
                    continue
                
                # Fallback to killing by name (with proper quoting for names with spaces)
                if not proc_name:
                    continue
                
                # Quote the process name if it contains spaces
                if ' ' in proc_name:
                    command = f'taskkill /F /IM "{proc_name}"'
                else:
                    command = f"taskkill /F /IM {proc_name}"
                
                logger.info(f"Executing: {command}")
                
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    logger.info(f"Successfully killed process: {proc_name}")
                    killed_any = True
                else:
                    logger.warning(f"Failed to kill {proc_name}: {result.stderr}")
            
            return killed_any
                
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
