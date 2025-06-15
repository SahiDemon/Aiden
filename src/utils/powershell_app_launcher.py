"""
PowerShell App Launcher for Aiden AI Assistant
Enhanced app finding and launching using PowerShell with fallback capabilities
"""
import os
import subprocess
import time
import logging
from typing import Dict, Any, Optional, List

class PowerShellAppLauncher:
    """PowerShell-based app launcher for Aiden with 15-second timeout and fallback"""
    
    def __init__(self, config_manager=None):
        """Initialize the PowerShell app launcher
        
        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager
        self.script_path = os.path.join(os.path.dirname(__file__), "..", "app_finder.ps1")
        self.timeout = 30  # 30 second timeout for primary search (some apps take longer)
        self.top_common_apps = [
            {"name": "Chrome", "command": "chrome", "description": "Google Chrome Browser"},
            {"name": "VS Code", "command": "code", "description": "Visual Studio Code Editor"},
            {"name": "Cursor", "command": "cursor", "description": "Cursor AI Code Editor"},
            {"name": "Steam", "command": "steam", "description": "Steam Gaming Platform"},
            {"name": "Discord", "command": "discord", "description": "Discord Chat Application"},
            {"name": "Spotify", "command": "spotify", "description": "Spotify Music Player"},
            {"name": "Notepad", "command": "notepad", "description": "Windows Notepad"},
            {"name": "Calculator", "command": "calculator", "description": "Windows Calculator"},
            {"name": "Explorer", "command": "explorer", "description": "Windows File Explorer"},
            {"name": "Firefox", "command": "firefox", "description": "Mozilla Firefox Browser"}
        ]
        
        # Enhanced app name mappings for better recognition
        self.app_name_mappings = {
            # Common variations and misspellings
            "speed gate": "splitgate",
            "speedgate": "splitgate", 
            "split gate": "splitgate",
            "google chrome": "chrome",
            "visual studio code": "code",
            "vs code": "code",
            "vscode": "code",
            "cursor editor": "cursor",
            "cursor ai": "cursor",
            "file explorer": "explorer",
            "windows explorer": "explorer",
            "calc": "calculator",
            "discord app": "discord",
            "spotify music": "spotify",
            "steam client": "steam",
            "steam app": "steam",
            # Add more as needed
        }
        
        # Hardcoded paths for apps that are hard to find or should launch instantly
        self.hardcoded_paths = {
            "steam": r"G:\Softwares\Steam\steam.exe",
            "cursor": r"C:\Users\gsahi\AppData\Local\Programs\cursor\Cursor.exe",
            # Note: Discord, Chrome, etc. will use PowerShell search for better reliability
        }
        
        logging.info("PowerShell app launcher initialized with hardcoded paths")
    
    def _get_hardcoded_path(self, app_name: str) -> Optional[str]:
        """Get hardcoded path for an app if available"""
        normalized_name = self._normalize_app_name(app_name)
        
        if normalized_name in self.hardcoded_paths:
            path = self.hardcoded_paths[normalized_name]
            # Check if the path exists
            if os.path.exists(path):
                logging.info(f"Found hardcoded path for {app_name}: {path}")
                return path
            else:
                logging.warning(f"Hardcoded path for {app_name} doesn't exist: {path}")
        
        return None
    
    def _normalize_app_name(self, app_name: str) -> str:
        """Normalize app name for better matching"""
        if not app_name:
            return ""
        
        # Convert to lowercase and strip
        normalized = app_name.lower().strip()
        
        # Check mappings first
        if normalized in self.app_name_mappings:
            mapped_name = self.app_name_mappings[normalized]
            logging.info(f"Mapped '{app_name}' → '{mapped_name}'")
            return mapped_name
        
        # Remove common words that might interfere
        words_to_remove = ["app", "application", "program", "launcher", "the", "open", "launch", "start", "run"]
        words = normalized.split()
        filtered_words = [word for word in words if word not in words_to_remove]
        
        if filtered_words:
            result = " ".join(filtered_words)
            
            # Check if the filtered result matches any mappings
            if result in self.app_name_mappings:
                mapped_name = self.app_name_mappings[result]
                logging.info(f"Mapped filtered result '{result}' → '{mapped_name}'")
                return mapped_name
            
            if result != normalized:
                logging.info(f"Normalized '{app_name}' → '{result}'")
            return result
        
        return normalized

    def _run_powershell_command(self, command: str, args: List[str] = None) -> Dict[str, Any]:
        """Run a PowerShell command and return result
        
        Args:
            command: PowerShell command to run
            args: Additional arguments
            
        Returns:
            Dictionary with execution results
        """
        if args is None:
            args = []
        
        # Check if the PowerShell script exists
        if not os.path.exists(self.script_path):
            return {
                "success": False,
                "stdout": "",
                "stderr": "PowerShell app finder script not found",
                "execution_time": 0,
                "method": "error"
            }
        
        cmd = [
            "powershell",
            "-ExecutionPolicy", "Bypass",
            "-File", self.script_path,
            command
        ] + args
        
        try:
            start_time = time.time()
            # Use a longer timeout for app searches, shorter for launches
            actual_timeout = self.timeout + 10 if command == "search" else self.timeout + 5
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=actual_timeout,
                encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            execution_time = time.time() - start_time
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "execution_time": execution_time,
                "return_code": result.returncode,
                "method": "powershell"
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": "PowerShell command timed out",
                "execution_time": self.timeout + 5,
                "return_code": -1,
                "method": "timeout"
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "execution_time": 0,
                "return_code": -1,
                "method": "error"
            }
    
    def search_app(self, app_name: str) -> Dict[str, Any]:
        """Search for an application using PowerShell with fallback
        
        Args:
            app_name: Name of the application to search for
            
        Returns:
            Dictionary with search results
        """
        normalized_name = self._normalize_app_name(app_name)
        logging.info(f"Searching for app: '{app_name}' (normalized: '{normalized_name}')")
        
        # Try PowerShell search first
        result = self._run_powershell_command("search", [normalized_name])
        
        if result["success"] and "found" in result["stdout"].lower():
            # Extract path from PowerShell output
            app_info = self._parse_powershell_output(result["stdout"])
            return {
                "success": True,
                "app_name": app_name,
                "actual_name": app_info.get("name", app_name),
                "path": app_info.get("path", ""),
                "method": "powershell_search",
                "execution_time": result["execution_time"],
                "message": f"Found {app_info.get('name', app_name)}",
                "app_info": app_info
            }
        
        # If PowerShell fails or times out, try simple fallback
        if not result["success"] or result["execution_time"] > self.timeout:
            logging.info(f"PowerShell search failed/timed out, trying fallback for: {normalized_name}")
            return self._fallback_search(app_name)
        
        return {
            "success": False,
            "app_name": app_name,
            "path": None,
            "method": "powershell_failed",
            "execution_time": result["execution_time"],
            "message": f"Could not find {app_name}"
        }
    
    def launch_app(self, app_name: str) -> Dict[str, Any]:
        """Launch an application using PowerShell with fallback
        
        Args:
            app_name: Name of the application to launch
            
        Returns:
            Dictionary with launch results
        """
        # Normalize the app name for better matching
        original_name = app_name
        normalized_name = self._normalize_app_name(app_name)
        
        logging.info(f"Launching app: '{original_name}' (normalized: '{normalized_name}')")
        
        # Try PowerShell launch first for most apps (more reliable and finds current paths)
        # Only use hardcoded paths for specific apps that need instant launch
        result = self._run_powershell_command("launch", [normalized_name])
        
        if result["success"]:
            # Parse the PowerShell output for better information
            stdout = result["stdout"]
            app_info = self._parse_powershell_output(stdout)
            
            # Determine the actual method used
            method = "powershell_primary"
            if "FALLBACK" in stdout:
                method = "powershell_fallback"
            elif "Steam game" in stdout or "steam://" in stdout:
                method = "steam_protocol"
            elif "UWP app" in stdout:
                method = "uwp_app"
            elif "Common app" in stdout:
                method = "common_app"
            
            return {
                "success": True,
                "app_name": original_name,
                "actual_name": app_info.get("name", original_name),
                "method": method,
                "execution_time": result["execution_time"],
                "message": self._create_success_message(app_info, method),
                "app_info": app_info,
                "is_steam_game": "steam://" in stdout,
                "launch_url": app_info.get("launch_url", "")
            }
        
        # If PowerShell fails or times out, try hardcoded path, then fallback
        if not result["success"] or result["execution_time"] > self.timeout:
            logging.info(f"PowerShell launch failed/timed out, trying alternatives for: {normalized_name}")
            
            # Try hardcoded path as backup
            hardcoded_path = self._get_hardcoded_path(original_name)
            if hardcoded_path:
                try:
                    subprocess.Popen([hardcoded_path], shell=True)
                    return {
                        "success": True,
                        "app_name": original_name,
                        "actual_name": original_name,
                        "method": "hardcoded_backup",
                        "execution_time": 0.1,
                        "message": f"Successfully launched {original_name} using backup path",
                        "app_info": {"name": original_name, "path": hardcoded_path},
                        "is_steam_game": False,
                        "launch_url": ""
                    }
                except Exception as e:
                    logging.warning(f"Failed to launch {original_name} with hardcoded backup path: {e}")
            
            # Final fallback
            return self._fallback_launch(original_name, normalized_name)
        
        return {
            "success": False,
            "app_name": original_name,
            "method": "powershell_failed",
            "execution_time": result["execution_time"],
            "message": f"Could not launch {original_name}",
            "error": result["stderr"]
        }
    
    def _parse_powershell_output(self, stdout: str) -> Dict[str, Any]:
        """Parse PowerShell output to extract app information"""
        app_info = {}
        lines = stdout.split('\n')
        
        for line in lines:
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()
                
                if key == "name" or key == "app name":
                    app_info["name"] = value
                elif key == "path" or key == "command":
                    app_info["path"] = value
                elif key == "launch url" or key == "steam url":
                    app_info["launch_url"] = value
                elif key == "app id" or key == "steam id":
                    app_info["app_id"] = value
                elif key == "type":
                    app_info["type"] = value
                elif key == "method":
                    app_info["method"] = value
        
        return app_info

    def _create_success_message(self, app_info: Dict[str, Any], method: str) -> str:
        """Create a user-friendly success message"""
        app_name = app_info.get("name", "the application")
        
        if method == "steam_protocol":
            return f"Successfully launched {app_name} through Steam"
        elif method == "uwp_app":
            return f"Successfully launched {app_name}"
        elif method == "common_app":
            return f"Successfully launched {app_name}"
        else:
            return f"Successfully launched {app_name}"
    
    def _fallback_search(self, app_name: str) -> Dict[str, Any]:
        """Simple fallback search using Windows commands
        
        Args:
            app_name: Name of the application to search for
            
        Returns:
            Dictionary with search results
        """
        start_time = time.time()
        
        # Try simple command lookup
        try:
            cmd_result = subprocess.run(
                ["where", f"{app_name}.exe"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if cmd_result.returncode == 0 and cmd_result.stdout.strip():
                path = cmd_result.stdout.strip().split('\n')[0]
                return {
                    "success": True,
                    "app_name": app_name,
                    "path": path,
                    "method": "fallback_where",
                    "execution_time": time.time() - start_time,
                    "message": f"Found {app_name} using fallback search"
                }
        except:
            pass
        
        # Try PowerShell Get-Command
        try:
            ps_result = subprocess.run(
                ["powershell", "-Command", f"Get-Command {app_name}.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if ps_result.returncode == 0 and ps_result.stdout.strip():
                path = ps_result.stdout.strip()
                return {
                    "success": True,
                    "app_name": app_name,
                    "path": path,
                    "method": "fallback_powershell",
                    "execution_time": time.time() - start_time,
                    "message": f"Found {app_name} using PowerShell fallback"
                }
        except:
            pass
        
        return {
            "success": False,
            "app_name": app_name,
            "path": None,
            "method": "fallback_failed",
            "execution_time": time.time() - start_time,
            "message": f"Fallback search failed for {app_name}"
        }
    
    def _fallback_launch(self, original_name: str, normalized_name: str) -> Dict[str, Any]:
        """Simple fallback launch using Windows commands
        
        Args:
            original_name: Original name of the application
            normalized_name: Normalized name of the application
            
        Returns:
            Dictionary with launch results
        """
        start_time = time.time()
        
        try:
            # Try simple command lookup first
            cmd_result = subprocess.run(
                ["where", f"{normalized_name}.exe"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if cmd_result.returncode == 0 and cmd_result.stdout.strip():
                path = cmd_result.stdout.strip().split('\n')[0]
                subprocess.Popen([path], shell=True)
                
                return {
                    "success": True,
                    "app_name": original_name,
                    "method": "simple_fallback",
                    "execution_time": time.time() - start_time,
                    "message": f"Successfully launched {original_name}"
                }
        except Exception as e:
            logging.warning(f"Fallback launch failed: {e}")
        
        return {
            "success": False,
            "app_name": original_name,
            "method": "fallback_failed",
            "execution_time": time.time() - start_time,
            "message": f"Could not find or launch {original_name}"
        }
    
    def get_common_apps(self) -> List[Dict[str, Any]]:
        """Get list of top common applications
        
        Returns:
            List of common applications
        """
        return self.top_common_apps.copy()
    
    def show_dashboard(self) -> Dict[str, Any]:
        """Show the interactive app selector dashboard
        
        Returns:
            Dictionary with dashboard result
        """
        logging.info("Opening PowerShell app launcher dashboard")
        
        result = self._run_powershell_command("dashboard")
        
        return {
            "success": result["success"],
            "method": "dashboard",
            "execution_time": result["execution_time"],
            "message": "Dashboard opened" if result["success"] else "Failed to open dashboard"
        }
    
    def list_apps(self, filter_term: str = "", top_common_only: bool = False) -> Dict[str, Any]:
        """List available applications
        
        Args:
            filter_term: Optional filter term
            top_common_only: Whether to show only top common apps
            
        Returns:
            Dictionary with app list results
        """
        if top_common_only:
            return {
                "success": True,
                "apps": self.get_common_apps(),
                "method": "common_apps",
                "execution_time": 0,
                "message": f"Top {len(self.top_common_apps)} common applications"
            }
        
        # Try to get full app list via PowerShell
        command = "list"
        args = []
        if filter_term:
            args.append(filter_term)
        
        result = self._run_powershell_command(command, args)
        
        if result["success"]:
            # Parse the output to extract app names
            apps = []
            lines = result["stdout"].split('\n')
            for line in lines:
                if '. ' in line and 'Command:' not in line and 'Description:' not in line:
                    try:
                        app_name = line.split('. ', 1)[1].strip()
                        if app_name:
                            apps.append({"name": app_name, "command": app_name.lower().replace(' ', '')})
                    except:
                        continue
            
            return {
                "success": True,
                "apps": apps,
                "method": "powershell_list",
                "execution_time": result["execution_time"],
                "message": f"Found {len(apps)} applications"
            }
        
        # Fallback to common apps if listing fails
        return {
            "success": True,
            "apps": self.get_common_apps(),
            "method": "fallback_common",
            "execution_time": result["execution_time"],
            "message": "PowerShell listing failed, showing common apps"
        }

