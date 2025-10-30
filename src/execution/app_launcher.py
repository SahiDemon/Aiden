"""
Dynamic App Launcher
Finds and launches applications without hardcoding - uses intelligent search and caching
"""
import os
import subprocess
import logging
from typing import Optional, List
from pathlib import Path
import winreg

from src.database.redis_client import get_redis_client
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AppLauncher:
    """Dynamically find and launch applications on Windows"""
    
    def __init__(self):
        self.common_search_paths = [
            r"C:\Program Files",
            r"C:\Program Files (x86)",
            os.path.join(os.environ.get("APPDATA", ""), "..\\Local\\Programs"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
            os.environ.get("PROGRAMFILES", ""),
            os.environ.get("PROGRAMFILES(X86)", ""),
        ]
        
        # Common app name mappings for better search
        self.app_aliases = {
            "chrome": [r"C:\Program Files\Google\Chrome\Application\chrome.exe", "chrome.exe", "Google Chrome", "chrome"],
            "chrome.exe": [r"C:\Program Files\Google\Chrome\Application\chrome.exe", "chrome.exe", "Google Chrome", "chrome"],
            "firefox": ["firefox.exe", "Mozilla Firefox", "firefox"],
            "firefox.exe": ["firefox.exe", "Mozilla Firefox", "firefox"],
            "edge": ["msedge.exe", "Microsoft Edge", "edge"],
            "msedge.exe": ["msedge.exe", "Microsoft Edge", "edge"],
            "notepad": ["notepad.exe"],
            "notepad.exe": ["notepad.exe"],
            "vscode": ["Code.exe", "Visual Studio Code", "code"],
            "vs code": ["Code.exe", "Visual Studio Code", "code"],
            "visual studio code": ["Code.exe", "Visual Studio Code"],
            "code": ["Code.exe", "Visual Studio Code"],
            "code.exe": ["Code.exe", "Visual Studio Code"],
            "spotify": ["Spotify.exe"],
            "discord": ["Discord.exe"],
            "calculator": ["calc.exe"],
            "calc": ["calc.exe"],
            "paint": ["mspaint.exe"],
            "explorer": ["explorer.exe"],
            "cmd": ["cmd.exe"],
            "powershell": ["powershell.exe"],
            "terminal": ["wt.exe", "WindowsTerminal.exe"],
            "word": ["WINWORD.EXE", "Microsoft Word"],
            "excel": ["EXCEL.EXE", "Microsoft Excel"],
            "outlook": ["OUTLOOK.EXE", "Microsoft Outlook"],
            "teams": ["Teams.exe", "Microsoft Teams"],
        }
    
    async def launch(self, app_name: str) -> bool:
        """
        Find and launch application
        
        Args:
            app_name: Name of application to launch
            
        Returns:
            True if successfully launched
        """
        app_name_lower = app_name.lower().strip()
        
        try:
            # 1. Try direct path from aliases first (for common apps like Chrome)
            possible_paths = self.app_aliases.get(app_name_lower, [])
            for path in possible_paths:
                if os.path.exists(path) and path.endswith('.exe'):
                    logger.info(f"Launching {app_name} from direct path: {path}")
                    return self._launch_exe(path)
            
            # 2. Use system context to find app (comprehensive registry + start menu scan)
            from src.utils.system_context import get_system_context
            sys_ctx = get_system_context()
            app_info = await sys_ctx.find_app(app_name_lower)
            
            if app_info:
                # Try exe_path first
                if app_info.get("exe_path") and os.path.exists(app_info["exe_path"]):
                    logger.info(f"Launching {app_name} from system context: {app_info['exe_path']}")
                    return self._launch_exe(app_info["exe_path"])
                
                # Try finding exe in install_path
                if app_info.get("install_path") and os.path.exists(app_info["install_path"]):
                    found_exe = self._find_exe_in_directory(app_info["install_path"])
                    if found_exe:
                        logger.info(f"Found exe in install path: {found_exe}")
                        return self._launch_exe(found_exe)
            
            # 3. Try system PATH
            if self._try_launch_from_path(app_name_lower):
                return True
            
            # 4. Check Redis cache (legacy)
            redis = await get_redis_client()
            cached_path = await redis.get_app_path(app_name_lower)
            
            if cached_path and os.path.exists(cached_path):
                logger.info(f"Launching {app_name} from cache: {cached_path}")
                return self._launch_exe(cached_path)
            
            # 5. Try Windows Start Menu shortcuts (fallback)
            if await self._launch_from_start_menu(app_name_lower):
                return True
            
            logger.warning(f"Could not find application: {app_name}")
            return False
            
        except Exception as e:
            logger.error(f"Error launching {app_name}: {e}")
            return False
    
    def _find_exe_in_directory(self, directory: str, max_depth: int = 2) -> Optional[str]:
        """Find first .exe file in directory (limited depth for performance)"""
        try:
            for root, dirs, files in os.walk(directory):
                # Limit depth
                depth = root[len(directory):].count(os.sep)
                if depth > max_depth:
                    continue
                
                for file in files:
                    if file.lower().endswith('.exe'):
                        return os.path.join(root, file)
        except Exception as e:
            logger.debug(f"Error searching directory {directory}: {e}")
        
        return None
    
    def _try_launch_from_path(self, app_name: str) -> bool:
        """Try launching app from system PATH"""
        try:
            # Try direct name (suppress output)
            subprocess.Popen(app_name, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"Launched {app_name} from PATH")
            return True
        except:
            pass
        
        # Try with .exe extension
        if not app_name.endswith(".exe"):
            try:
                subprocess.Popen(f"{app_name}.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                logger.info(f"Launched {app_name}.exe from PATH")
                return True
            except:
                pass
        
        return False
    
    async def _find_app_path(self, app_name: str) -> Optional[str]:
        """Search for application executable"""
        # Get possible names
        possible_names = self.app_aliases.get(app_name, [app_name])
        if not app_name.endswith(".exe"):
            possible_names.append(f"{app_name}.exe")
        
        # Search in common locations
        for search_path in self.common_search_paths:
            if not os.path.exists(search_path):
                continue
            
            for possible_name in possible_names:
                # Search recursively (limit depth to 3 for performance)
                found_path = await self._search_directory(
                    search_path,
                    possible_name,
                    max_depth=3
                )
                if found_path:
                    return found_path
        
        return None
    
    async def _search_directory(
        self,
        directory: str,
        target: str,
        max_depth: int = 3,
        current_depth: int = 0
    ) -> Optional[str]:
        """Recursively search directory for executable"""
        if current_depth >= max_depth:
            return None
        
        try:
            for entry in os.scandir(directory):
                try:
                    if entry.is_file():
                        if entry.name.lower() == target.lower():
                            return entry.path
                    elif entry.is_dir() and not entry.name.startswith('.'):
                        result = await self._search_directory(
                            entry.path,
                            target,
                            max_depth,
                            current_depth + 1
                        )
                        if result:
                            return result
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            pass
        
        return None
    
    async def _launch_from_start_menu(self, app_name: str) -> bool:
        """Try to launch from Windows Start Menu"""
        try:
            # Common Start Menu locations
            start_menu_paths = [
                os.path.join(os.environ.get("APPDATA", ""), "Microsoft\\Windows\\Start Menu\\Programs"),
                os.path.join(os.environ.get("PROGRAMDATA", ""), "Microsoft\\Windows\\Start Menu\\Programs"),
            ]
            
            for start_path in start_menu_paths:
                if not os.path.exists(start_path):
                    continue
                
                # Search for .lnk files
                for root, dirs, files in os.walk(start_path):
                    for file in files:
                        if file.lower().endswith('.lnk'):
                            if app_name in file.lower():
                                shortcut_path = os.path.join(root, file)
                                logger.info(f"Launching from Start Menu: {shortcut_path}")
                                os.startfile(shortcut_path)
                                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error launching from Start Menu: {e}")
            return False
    
    def _launch_exe(self, path: str) -> bool:
        """Launch executable at given path"""
        try:
            subprocess.Popen(path, shell=True)
            return True
        except Exception as e:
            logger.error(f"Error launching {path}: {e}")
            return False


# Global instance
_app_launcher: Optional[AppLauncher] = None


def get_app_launcher() -> AppLauncher:
    """Get or create global app launcher"""
    global _app_launcher
    if _app_launcher is None:
        _app_launcher = AppLauncher()
    return _app_launcher



