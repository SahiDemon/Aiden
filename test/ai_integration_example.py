"""
AI Assistant App Launcher Integration Example
This shows how to integrate the PowerShell app launcher with your AI assistant
"""

import subprocess
import json
import time
from typing import Dict, Any, Optional

class AIAppLauncher:
    def __init__(self, script_path: str = "ai_app_launcher.ps1"):
        self.script_path = script_path
        self.timeout = 15  # 15 second timeout for primary search
        
    def _run_powershell(self, command: str, args: list = None) -> Dict[str, Any]:
        """Run PowerShell command and return result"""
        if args is None:
            args = []
            
        cmd = [
            "powershell", 
            "-ExecutionPolicy", "Bypass", 
            "-File", self.script_path,
            command
        ] + args
        
        try:
            start_time = time.time()
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=self.timeout + 5,  # Add buffer to PowerShell timeout
                encoding='utf-8'
            )
            
            execution_time = time.time() - start_time
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "execution_time": execution_time,
                "return_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": "Command timed out",
                "execution_time": self.timeout + 5,
                "return_code": -1
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "execution_time": 0,
                "return_code": -1
            }
    
    def launch_app(self, app_name: str, interactive: bool = False) -> Dict[str, Any]:
        """Launch an application using AI app launcher"""
        print(f"🚀 AI Assistant: Launching {app_name}...")
        
        args = [app_name]
        if interactive:
            args.append("-Interactive")
            
        result = self._run_powershell("launch", args)
        
        # Parse result for AI assistant
        if result["success"]:
            if "launched successfully" in result["stdout"].lower():
                return {
                    "success": True,
                    "message": f"Successfully launched {app_name}",
                    "app_name": app_name,
                    "method": "primary" if "PRIMARY" in result["stdout"] else "fallback",
                    "execution_time": result["execution_time"]
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to launch {app_name}",
                    "app_name": app_name,
                    "error": "Launch failed",
                    "execution_time": result["execution_time"]
                }
        else:
            return {
                "success": False,
                "message": f"Could not find or launch {app_name}",
                "app_name": app_name,
                "error": result["stderr"] or "Application not found",
                "execution_time": result["execution_time"]
            }
    
    def search_app(self, app_name: str) -> Dict[str, Any]:
        """Search for an application"""
        print(f"🔍 AI Assistant: Searching for {app_name}...")
        
        result = self._run_powershell("search", [app_name])
        
        if result["success"] and "found" in result["stdout"].lower():
            return {
                "success": True,
                "message": f"Found {app_name}",
                "app_name": app_name,
                "found": True,
                "execution_time": result["execution_time"]
            }
        else:
            return {
                "success": False,
                "message": f"Could not find {app_name}",
                "app_name": app_name,
                "found": False,
                "execution_time": result["execution_time"]
            }
    
    def get_common_apps(self) -> Dict[str, Any]:
        """Get list of top 10 common applications"""
        print("📋 AI Assistant: Getting common applications...")
        
        result = self._run_powershell("common")
        
        if result["success"]:
            # Parse the output to extract app names
            apps = []
            lines = result["stdout"].split('\n')
            for line in lines:
                if '. ' in line and 'Command:' not in line and 'Description:' not in line:
                    try:
                        app_name = line.split('. ', 1)[1].strip()
                        if app_name:
                            apps.append(app_name)
                    except:
                        continue
            
            return {
                "success": True,
                "message": f"Found {len(apps)} common applications",
                "apps": apps[:10],  # Top 10
                "execution_time": result["execution_time"]
            }
        else:
            return {
                "success": False,
                "message": "Failed to get common applications",
                "apps": [],
                "execution_time": result["execution_time"]
            }
    
    def show_dashboard(self) -> Dict[str, Any]:
        """Show interactive dashboard (for hotkey usage)"""
        print("🎛️ AI Assistant: Opening app launcher dashboard...")
        
        result = self._run_powershell("dashboard")
        
        return {
            "success": result["success"],
            "message": "Dashboard opened" if result["success"] else "Failed to open dashboard",
            "execution_time": result["execution_time"]
        }

# AI Assistant Integration Functions
def handle_app_launch_request(user_input: str, launcher: AIAppLauncher) -> str:
    """
    Handle app launch requests from AI assistant
    This is what your AI assistant would call
    """
    
    # Extract app name from user input
    app_name = extract_app_name(user_input)
    
    if not app_name:
        # If AI doesn't know the app, show common apps
        common_apps = launcher.get_common_apps()
        if common_apps["success"]:
            apps_list = ", ".join(common_apps["apps"])
            return f"I'm not sure which app you want to launch. Here are some common applications I can launch: {apps_list}. Which one would you like?"
        else:
            return "I'm not sure which app you want to launch. Could you be more specific?"
    
    # Try to launch the app
    result = launcher.launch_app(app_name)
    
    if result["success"]:
        method = result.get("method", "unknown")
        time_taken = result.get("execution_time", 0)
        return f"✅ Successfully launched {app_name} using {method} search in {time_taken:.1f} seconds!"
    else:
        # If primary search fails, offer alternatives
        common_apps = launcher.get_common_apps()
        if common_apps["success"]:
            apps_list = ", ".join(common_apps["apps"])
            return f"❌ I couldn't find '{app_name}'. Here are some apps I can definitely launch: {apps_list}. Would you like to try one of these instead?"
        else:
            return f"❌ I couldn't find or launch '{app_name}'. Please check if the application is installed."

def extract_app_name(user_input: str) -> Optional[str]:
    """Extract app name from user input"""
    user_input = user_input.lower()
    
    # Common app mappings
    app_mappings = {
        "chrome": "chrome",
        "google chrome": "chrome",
        "browser": "chrome",
        "vs code": "code",
        "visual studio code": "code",
        "code editor": "code",
        "steam": "steam",
        "discord": "discord",
        "spotify": "spotify",
        "music": "spotify",
        "notepad": "notepad",
        "calculator": "calculator",
        "calc": "calculator",
        "file explorer": "explorer",
        "explorer": "explorer",
        "firefox": "firefox",
        "vlc": "vlc",
        "media player": "vlc"
    }
    
    # Check for direct matches
    for phrase, app in app_mappings.items():
        if phrase in user_input:
            return app
    
    # Extract potential app name after trigger words
    trigger_words = ["launch", "open", "start", "run"]
    for trigger in trigger_words:
        if trigger in user_input:
            parts = user_input.split(trigger, 1)
            if len(parts) > 1:
                potential_app = parts[1].strip()
                if potential_app:
                    return potential_app
    
    return None

# Example usage
if __name__ == "__main__":
    # Initialize the launcher
    launcher = AIAppLauncher()
    
    # Example AI assistant interactions
    test_inputs = [
        "launch chrome",
        "open vs code", 
        "start spotify",
        "run calculator",
        "launch some unknown app",
        "open browser"
    ]
    
    print("🤖 AI Assistant App Launcher Integration Demo")
    print("=" * 50)
    
    for user_input in test_inputs:
        print(f"\n👤 User: {user_input}")
        response = handle_app_launch_request(user_input, launcher)
        print(f"🤖 AI Assistant: {response}")
        print("-" * 30)
    
    # Demo dashboard (uncomment to test)
    # print("\n🎛️ Opening dashboard...")
    # launcher.show_dashboard() 