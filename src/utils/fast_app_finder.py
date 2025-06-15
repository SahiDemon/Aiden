"""
Fast Python-based app finder to replace the hanging PowerShell script
Optimized for speed and reliability when called from Aiden
"""

import os
import subprocess
import logging
from typing import Dict, Optional, Any
import time

class FastAppFinder:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Known app paths for instant lookup
        self.known_paths = {
            "discord": r"C:\Users\gsahi\AppData\Local\Discord\app-1.0.9195\Discord.exe",
            "steam": r"G:\Softwares\Steam\steam.exe", 
            "cursor": r"C:\Users\gsahi\AppData\Local\Programs\cursor\Cursor.exe",
            "chrome": self._find_chrome(),
            "firefox": self._find_firefox(),
            "code": self._find_vscode(),
            "spotify": self._find_spotify(),
        }
        
        # Common app locations to check
        self.common_locations = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
            os.path.expandvars(r"%ProgramFiles%"),
            os.path.expandvars(r"%ProgramFiles(x86)%"), 
            os.path.expandvars(r"%APPDATA%"),
            os.path.expandvars(r"%LOCALAPPDATA%"),
        ]
    
    def _find_chrome(self) -> Optional[str]:
        """Find Google Chrome installation"""
        possible_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None
    
    def _find_firefox(self) -> Optional[str]:
        """Find Firefox installation"""
        possible_paths = [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None
    
    def _find_vscode(self) -> Optional[str]:
        """Find Visual Studio Code installation"""
        possible_paths = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
            r"C:\Program Files\Microsoft VS Code\Code.exe",
            r"C:\Program Files (x86)\Microsoft VS Code\Code.exe",
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None
    
    def _find_spotify(self) -> Optional[str]:
        """Find Spotify installation"""
        possible_paths = [
            os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None
    
    def find_app(self, app_name: str) -> Dict[str, Any]:
        """Find an application quickly"""
        start_time = time.time()
        app_name_lower = app_name.lower().strip()
        
        # Check known paths first (fastest)
        if app_name_lower in self.known_paths:
            path = self.known_paths[app_name_lower]
            if path and os.path.exists(path):
                return {
                    "success": True,
                    "app_name": app_name,
                    "path": path,
                    "method": "known_path",
                    "execution_time": time.time() - start_time,
                }
        
        # Try PATH lookup
        try:
            result = subprocess.run(
                ["where", f"{app_name_lower}.exe"],
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode == 0 and result.stdout.strip():
                path = result.stdout.strip().split('\n')[0]
                return {
                    "success": True,
                    "app_name": app_name,
                    "path": path,
                    "method": "path_search",
                    "execution_time": time.time() - start_time,
                }
        except:
            pass
        
        return {
            "success": False,
            "app_name": app_name,
            "path": None,
            "method": "not_found",
            "execution_time": time.time() - start_time,
        }
    
    def launch_app(self, app_name: str) -> Dict[str, Any]:
        """Find and launch an application"""
        # Find the app first
        find_result = self.find_app(app_name)
        
        if not find_result["success"]:
            return {
                "success": False,
                "app_name": app_name,
                "method": "not_found",
                "execution_time": find_result["execution_time"],
                "message": f"Could not find {app_name}",
                "error": "Application not found"
            }
        
        # Try to launch it
        app_path = find_result["path"]
        
        try:
            subprocess.Popen([app_path], shell=True)
            return {
                "success": True,
                "app_name": app_name,
                "actual_name": os.path.basename(app_path),
                "method": f"fast_{find_result['method']}",
                "execution_time": find_result["execution_time"],
                "message": f"Successfully launched {app_name}",
                "app_info": {"name": app_name, "path": app_path},
                "is_steam_game": False,
                "launch_url": ""
            }
        except Exception as e:
            return {
                "success": False,
                "app_name": app_name,
                "method": "launch_failed",
                "execution_time": find_result["execution_time"],
                "message": f"Found {app_name} but failed to launch",
                "error": str(e)
            }
