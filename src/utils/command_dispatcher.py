"""
Command Dispatcher for Aiden
Handles routing of commands to appropriate handlers
"""
import os
import logging
import subprocess
import webbrowser
import threading
from typing import Dict, Any, Callable, Optional

# Import ESP32 controller and App Manager
from src.utils.esp32_controller import ESP32Controller
from src.utils.app_manager import AppManager
from src.utils.powershell_app_launcher import PowerShellAppLauncher

class CommandDispatcher:
    """Dispatches commands to appropriate handlers"""
    
    def __init__(self, config_manager, voice_system, dashboard_backend=None):
        """Initialize the command dispatcher
        
        Args:
            config_manager: Configuration manager instance
            voice_system: Voice system instance for providing feedback
            dashboard_backend: Optional dashboard backend for UI updates
        """
        self.config_manager = config_manager
        self.voice_system = voice_system
        self.dashboard_backend = dashboard_backend
        self.security_config = config_manager.get_config("security")
        
        # Initialize ESP32 controller if enabled
        general_config = config_manager.get_config("general")
        esp32_config = general_config.get("esp32", {})
        esp32_enabled = esp32_config.get("enabled", False)
        
        logging.info(f"ESP32 configuration: {esp32_config}")
        logging.info(f"ESP32 enabled: {esp32_enabled}")
        
        if esp32_enabled:
            try:
                self.esp32_controller = ESP32Controller(config_manager)
                logging.info("ESP32 controller initialized successfully")
            except Exception as e:
                logging.error(f"Failed to initialize ESP32 controller: {e}")
                self.esp32_controller = None
        else:
            self.esp32_controller = None
            logging.info("ESP32 controller not enabled in config")
        
        # Initialize PowerShell App Launcher as PRIMARY app launcher
        self.powershell_launcher = PowerShellAppLauncher(config_manager)
        
        # Initialize App Manager for fallback app discovery and launching
        self.app_manager = AppManager(config_manager)
        
        # Command handlers dictionary
        self.handlers = {
            "provide_information": self._handle_information,
            "file_operation": self._handle_file_operation,
            "app_control": self._handle_app_control,
            "web_search": self._handle_web_search,
            "system_command": self._handle_system_command,
            "change_settings": self._handle_settings,
            "fan_control": self._handle_fan_control,
            "end_conversation": self._handle_end_conversation,
            "stop_current_task": self._handle_stop_task,
            "unknown": self._handle_unknown
        }
        
        logging.info("Command dispatcher initialized with PowerShell app launcher")
    
    def dispatch(self, command: Dict[str, Any]) -> bool:
        """Dispatch a command based on its action
        
        Args:
            command: Dictionary containing action, parameters, and response
            
        Returns:
            True if command was executed successfully, False otherwise
        """
        action = command.get("action", "unknown")
        parameters = command.get("parameters", {})
        response = command.get("response", "")
        
        logging.info(f"Dispatching command: {action}")
        
        # Check if response has already been spoken (to prevent duplicate speech)
        already_spoken = command.get("_already_spoken", False)
        
        # Special handling for end conversation
        if action == "end_conversation":
            if response and not already_spoken:
                self.voice_system.speak(response)
            
            if action in self.handlers:
                return self.handlers[action](parameters)
            return True
        
        # Create a flag to track handler success
        handler_success = [False]
        
        # Define a function to execute the handler
        def execute_handler():
            if action in self.handlers:
                handler_success[0] = self.handlers[action](parameters)
            else:
                logging.warning(f"Unknown action: {action}")
        
        # Special handling for project listing queries - don't speak the response first
        is_project_listing = (
            action == "provide_information" and
            parameters.get("query", "") and
            any(phrase in parameters.get("query", "").lower() 
                for phrase in ["list my projects", "show my projects", "my projects", "project list", "show projects", "what projects"])
        )
        
        # For app_control, speak immediately then execute (the handler will provide specific feedback)
        if action == "app_control":
            # Speak the initial response (like "Let me find that for you")
            if response and not already_spoken:
                self.voice_system.speak(response)
            
            # Execute the handler which will provide the real result
            if action in self.handlers:
                return self.handlers[action](parameters)
            else:
                logging.warning(f"Unknown action: {action}")
                return False
        
        # Start a thread for command execution for other threaded actions
        elif action in ["fan_control", "web_search"] or is_project_listing:
            # For these actions, we start executing immediately while speaking
            handler_thread = threading.Thread(target=execute_handler)
            handler_thread.daemon = True
            handler_thread.start()
            
            # For project listing, let the handler manage speech
            # For other actions, speak only if not already spoken
            if not is_project_listing and response and not already_spoken:
                self.voice_system.speak(response)
                
            # Wait for the handler to complete
            handler_thread.join()
            return handler_success[0]
        else:
            # For other actions, we speak first, then execute (original behavior)
            # But only speak if not already spoken
            if response and not already_spoken:
                self.voice_system.speak(response)
            
            # Call the appropriate handler directly
            if action in self.handlers:
                return self.handlers[action](parameters)
            else:
                logging.warning(f"Unknown action: {action}")
                return False
    
    def _handle_information(self, parameters: Dict[str, Any]) -> bool:
        """Handle information provision commands
        
        Args:
            parameters: Command parameters
            
        Returns:
            True if handled successfully, False otherwise
        """
        query = parameters.get("query", "").lower() if parameters.get("query") else ""
        
        # Check if speech should be prevented (already spoken by dashboard)
        prevent_speech = parameters.get("_prevent_speech", False)
        
        # Check for time-related queries
        if any(word in query for word in ["time", "clock", "hour"]):
            import datetime
            now = datetime.datetime.now()
            time_str = now.strftime("%I:%M %p")
            response_text = f"The current time is {time_str}."
            logging.info(f"Providing current time: {time_str}")
            
            # Emit to dashboard if available
            if self.dashboard_backend:
                self.dashboard_backend._emit_ai_message(response_text, "response")
            
            if not prevent_speech:
                self.voice_system.speak(response_text)
            return True
            
        # Check for date-related queries
        elif any(word in query for word in ["date", "day", "today", "month", "year"]):
            import datetime
            now = datetime.datetime.now()
            date_str = now.strftime("%A, %B %d, %Y")
            response_text = f"Today is {date_str}."
            
            # Emit to dashboard if available
            if self.dashboard_backend:
                self.dashboard_backend._emit_ai_message(response_text, "response")
            
            if not prevent_speech:
                self.voice_system.speak(response_text)
            return True
            
        # Check for app listing queries
        elif any(phrase in query for phrase in ["list apps", "show apps", "available apps", "installed applications", "list applications", "show applications", "app list", "show app list", "what apps", "which apps", "available applications"]):
            # Use the enhanced app listing functionality
            return self._show_available_apps_enhanced()
            
        # Check for project listing queries
        elif any(phrase in query for phrase in ["list my projects", "show my projects", "my projects", "project list", "show projects", "what projects"]):
            # Use the project listing functionality
            github_path = "G:\\GitHub"
            return self._show_projects(github_path)
            
        # Check for weather-related queries
        elif any(word in query for word in ["weather", "temperature", "forecast"]):
            response_text = "I don't have access to real-time weather data yet. You can check your local weather service or ask me to open a weather website."
            
            # Emit to dashboard if available
            if self.dashboard_backend:
                self.dashboard_backend._emit_ai_message(response_text, "response")
            
            if not prevent_speech:
                self.voice_system.speak(response_text)
            return True
            
        # Check for owner/creator queries
        elif any(phrase in query for phrase in ["who is your owner", "who created you", "who made you", "who is your creator", "who built you", "who developed you"]):
            # Open GitHub profile
            import webbrowser
            github_url = "https://github.com/SahiDemon"
            
            try:
                webbrowser.open(github_url)
                logging.info(f"Opened GitHub profile: {github_url}")
            except Exception as e:
                logging.error(f"Error opening GitHub profile: {e}")
            
            response_text = "My owner is Sahindu Gayanuka, a brilliant Sri Lankan full-stack developer!. Sahindu is the mastermind founder who created Aiden, AKA me. You can check out his awesome work on GitHub - I just opened his profile for you!"
            
            # Emit to dashboard if available
            if self.dashboard_backend:
                self.dashboard_backend._emit_ai_message(response_text, "response")
            
            if not prevent_speech:
                self.voice_system.speak(response_text)
            return True
        
        # Check for project listing queries
        elif any(phrase in query for phrase in ["list my projects", "show my projects", "my projects", "project list", "show projects", "what projects", "project"]):
            logging.info(f"Project listing query detected: {query}")
            try:
                result = self._show_projects("G:\\GitHub")
                logging.info(f"Project listing result: {result}")
                return result
            except Exception as e:
                logging.error(f"Error in project listing: {e}")
                error_msg = f"I had trouble accessing your projects. Error: {str(e)}"
                if self.dashboard_backend:
                    self.dashboard_backend._emit_ai_message(error_msg, "error")
                if not prevent_speech:
                    self.voice_system.speak("I had trouble accessing your projects.")
                return False
        
        # Check for project/coding help queries
        elif any(phrase in query for phrase in ["project ideas", "what should i build", "what should i code", "suggest a project", "coding project", "development ideas", "programming ideas", "what to work on"]):
            
            project_suggestions = self._get_coding_project_suggestions()
            
            response_text = f"""Great question! I love helping with project ideas! Here are some exciting suggestions based on your experience:

{project_suggestions}

I can help you get started with any of these! Just ask me to:
• Create project folders and files
• Open development tools like VSCode
• Find tutorials and documentation
• Search for similar projects for inspiration
• Set up development environments

Which type of project interests you most? I'm here to help you bring your ideas to life!"""
            
            # Emit to dashboard if available
            if self.dashboard_backend:
                self.dashboard_backend._emit_ai_message(response_text, "response")
            
            # Shorter spoken response
            spoken_response = "I'd love to help with project ideas! I've got some exciting suggestions ranging from web apps to AI projects. I can help you create folders, open tools, find tutorials, and get everything set up. What type of project sounds interesting to you?"
            
            if not prevent_speech:
                self.voice_system.speak(spoken_response)
            return True
            
        # Check for capabilities/what can you do queries
        elif any(phrase in query for phrase in ["what can you do", "what are you capable of", "what are your capabilities", "help", "what can you help me with", "what do you do", "tell me about yourself", "what are your features"]):
            
            # Get personalized suggestions based on user history
            personalized_suggestions = self._get_personalized_suggestions()
            
            capabilities_text = f"""I'm Aiden, your AI-powered voice assistant! Here's what I can help you with:

🚀 **APPLICATION CONTROL**
• Open any app - "Open Chrome", "Launch VSCode", "Start Word"
• Close applications and manage windows

📁 **FILE OPERATIONS** 
• Create, read, and modify files
• Open folders and navigate directories
• Organize your documents

🌐 **WEB & SEARCH**
• Search the internet for anything
• Open websites and browse content
• Get real-time information

⏰ **SYSTEM INFO**
• Check current time and date
• Get system status and details
• Monitor device performance

🌀 **SMART HOME (ESP32 FAN)**
• Turn fan on/off with voice commands
• Change fan modes and speeds
• Complete IoT device control

🧠 **INTELLIGENT ASSISTANCE**
• Answer questions on any topic
• Help with calculations and conversions
• Provide explanations and tutorials

🎯 **VOICE INTERACTION**
• Natural conversation flow
• Smart follow-up questions
• Hands-free operation with hotkey activation

{personalized_suggestions}

Just say "Hey Aiden" or press the asterisk (*) key and ask me anything! I'm here to make your life easier."""

            # Create a more conversational spoken response
            spoken_response = self._create_conversational_response()
            
            # Emit to dashboard if available
            if self.dashboard_backend:
                self.dashboard_backend._emit_ai_message(capabilities_text, "response")
            
            if not prevent_speech:
                self.voice_system.speak(spoken_response)
            return True
            
        # Handle any other general information queries
        else:
            original_query = parameters.get('original_query', '')
            query = parameters.get('query', '')
            
            # For simple greetings and conversational responses, don't duplicate speech
            # The dashboard backend should handle these
            if any(word in original_query.lower() for word in ["hello", "hi", "hey", "good morning", "good afternoon"]) or \
               any(phrase in original_query.lower() for phrase in ["how are you", "how r u"]):
                # Don't speak here - let dashboard backend handle simple conversational responses
                return True
            
            # Check if it's a specific type of query we can answer
            if any(word in original_query.lower() for word in ["fastest", "car", "speed", "vehicle"]):
                response_text = "The fastest production car in the world is currently the Bugatti Chiron Super Sport 300+, which has achieved a top speed of 304.773 mph (490.484 km/h). However, there are also experimental and prototype vehicles that have reached even higher speeds. Would you like me to tell you more about fast cars or search for the latest speed records?"
                
                if not prevent_speech:
                    self.voice_system.speak(response_text)
            else:
                response_text = f"I heard you say '{original_query}'. Let me help you with that! What would you like me to do?"
                
                if not prevent_speech:
                    self.voice_system.speak(response_text)
        return True
    
    def _get_personalized_suggestions(self) -> str:
        """Generate personalized suggestions based on user history"""
        try:
            user_profile = self.config_manager.get_user_profile()
            interactions = user_profile.get("history", {}).get("interactions", [])
            
            # Analyze recent interactions (last 10)
            recent_interactions = interactions[-10:] if len(interactions) > 10 else interactions
            
            suggestions = []
            
            # Check for coding-related activities
            coding_apps = ["vscode", "visual studio", "sublime", "atom", "notepad++", "pycharm", "intellij"]
            coding_files = [".py", ".js", ".html", ".css", ".cpp", ".java", ".cs"]
            
            has_coding_activity = any(
                any(app in interaction.get("text", "").lower() for app in coding_apps) or
                any(ext in interaction.get("text", "").lower() for ext in coding_files)
                for interaction in recent_interactions
            )
            
            if has_coding_activity:
                suggestions.append("💻 **CODING PROJECTS** - I noticed you've been coding! Want me to help create a new project, open your IDE, or search for coding tutorials?")
            
            # Check for fan usage patterns
            fan_usage = [i for i in recent_interactions if i.get("type") == "fan_control"]
            if len(fan_usage) > 2:
                suggestions.append("🌀 **SMART SETUP** - I see you use the fan frequently! Want me to set up automated schedules or create voice shortcuts?")
            
            # Check for web searches
            web_searches = [i for i in recent_interactions if "search" in i.get("text", "").lower()]
            if web_searches:
                last_search = web_searches[-1].get("text", "") if web_searches else ""
                if last_search:
                    suggestions.append(f"🔍 **RESEARCH HELP** - Continuing your research? I can help dive deeper into topics or find related resources!")
            
            # Check session count for experience level
            total_sessions = user_profile.get("history", {}).get("total_sessions", 0)
            if total_sessions < 5:
                suggestions.append("🎯 **NEW USER TIPS** - Try saying 'open VSCode', 'what's the time', or 'turn on the fan' to see what I can do!")
            
            # Default suggestions if no specific patterns
            if not suggestions:
                import random
                default_suggestions = [
                    "💡 **PROJECT IDEAS** - Need help brainstorming? I can suggest coding projects, help with development, or find learning resources!",
                    "🚀 **PRODUCTIVITY** - Want to boost your workflow? I can automate tasks, organize files, or set up development environments!",
                    "🧠 **LEARNING** - Curious about something? Ask me to explain concepts, find tutorials, or help with problem-solving!"
                ]
                suggestions.append(random.choice(default_suggestions))
            
            if suggestions:
                return f"\n\n💫 **PERSONALIZED FOR YOU:**\n" + "\n".join(f"• {s}" for s in suggestions)
            
            return ""
            
        except Exception as e:
            logging.error(f"Error generating personalized suggestions: {e}")
            return ""
    
    def _create_conversational_response(self) -> str:
        """Create a conversational spoken response based on user history"""
        try:
            user_profile = self.config_manager.get_user_profile()
            user_name = user_profile.get("personal", {}).get("name", "")
            interactions = user_profile.get("history", {}).get("interactions", [])
            total_sessions = user_profile.get("history", {}).get("total_sessions", 0)
            
            # Get recent activity insights
            recent_interactions = interactions[-5:] if len(interactions) > 5 else interactions
            
            # Check what user has been doing recently
            has_coding = any("vscode" in i.get("text", "").lower() or "code" in i.get("text", "").lower() for i in recent_interactions)
            has_fan_control = any(i.get("type") == "fan_control" for i in recent_interactions)
            
            base_response = "I'm Aiden, your AI-powered voice assistant! I can help with applications, files, web searches, system info, your ESP32 fan, and intelligent assistance."
            
            # Add personalized touch based on activity
            if total_sessions < 3:
                additional = " Since you're new here, try asking me to open an app, check the time, or control your fan!"
            elif has_coding:
                additional = " I noticed you've been coding - want me to help with your next project, open development tools, or find coding resources?"
            elif has_fan_control:
                additional = " I see you use the fan controls often - need help setting up automation or creating custom commands?"
            else:
                import random
                suggestions = [
                    " What do you have in mind today? Any coding projects, research, or tasks I can help with?",
                    " I'm ready to help! Got any interesting projects brewing or questions you'd like to explore?",
                    " What brings you here today? Whether it's coding, research, or just curious conversation, I'm here to help!"
                ]
                additional = random.choice(suggestions)
            
            return base_response + additional
            
        except Exception as e:
            logging.error(f"Error creating conversational response: {e}")
            return "I'm Aiden, your AI assistant! I can help with apps, files, searches, system info, your ESP32 fan, and much more. What can I help you with today?"
    
    def _get_coding_project_suggestions(self) -> str:
        """Generate coding project suggestions based on user history and experience"""
        try:
            user_profile = self.config_manager.get_user_profile()
            interactions = user_profile.get("history", {}).get("interactions", [])
            total_sessions = user_profile.get("history", {}).get("total_sessions", 0)
            
            # Analyze user's coding background from interactions
            recent_interactions = interactions[-20:] if len(interactions) > 20 else interactions
            
            # Check for technology mentions
            has_python = any("python" in i.get("text", "").lower() for i in recent_interactions)
            has_javascript = any(any(tech in i.get("text", "").lower() for tech in ["javascript", "js", "react", "node"]) for i in recent_interactions)
            has_web_dev = any(any(tech in i.get("text", "").lower() for tech in ["html", "css", "web", "website"]) for i in recent_interactions)
            has_iot = any(any(tech in i.get("text", "").lower() for tech in ["esp32", "iot", "arduino"]) for i in recent_interactions)
            
            suggestions = []
            
            # Beginner projects
            if total_sessions < 10:
                suggestions.extend([
                    "🎯 **Todo List App** - Build a simple task manager with HTML, CSS, and JavaScript",
                    "🎮 **Tic-Tac-Toe Game** - Create an interactive game to practice programming logic",
                    "📊 **Personal Expense Tracker** - Simple Python script to track your spending",
                    "🌐 **Personal Portfolio Website** - Showcase your projects with a clean, responsive design"
                ])
            
            # Python projects
            if has_python:
                suggestions.extend([
                    "🤖 **ChatBot Assistant** - Build a smart chatbot using Python and AI libraries",
                    "📈 **Stock Price Tracker** - Create a tool to monitor and analyze stock prices",
                    "🔍 **Web Scraper** - Extract data from websites for analysis",
                    "📱 **Discord Bot** - Build a fun bot for your Discord server"
                ])
            
            # Web development projects
            if has_javascript or has_web_dev:
                suggestions.extend([
                    "⚡ **React Dashboard** - Create a modern admin panel with React",
                    "🛒 **E-commerce Site** - Build a complete online store with cart functionality",
                    "📝 **Blog Platform** - Create a full-stack blogging system",
                    "🎵 **Music Streaming App** - Build a Spotify-like interface"
                ])
            
            # IoT/Hardware projects
            if has_iot:
                suggestions.extend([
                    "🏠 **Smart Home Hub** - Expand your ESP32 fan control to a full home automation system",
                    "🌡️ **Weather Station** - Build an IoT weather monitoring system",
                    "💡 **Smart Lighting** - Create voice-controlled LED lighting system",
                    "🔒 **Security System** - Build a smart door lock with facial recognition"
                ])
            
            # Advanced projects for experienced users
            if total_sessions > 20:
                suggestions.extend([
                    "🧠 **AI Voice Assistant** - Create your own Aiden-like assistant",
                    "🐋 **Docker Automation Tool** - Build deployment automation with Docker",
                    "📊 **Real-time Analytics Dashboard** - Process and visualize live data streams",
                    "🚀 **Microservices Architecture** - Design a scalable backend system"
                ])
            
            # If no specific technologies detected, provide general suggestions
            if not any([has_python, has_javascript, has_web_dev, has_iot]):
                suggestions.extend([
                    "🌟 **Choose Your Adventure:**",
                    "• 🐍 **Python Path** - Data analysis, automation, AI/ML projects",
                    "• 🌐 **Web Development** - Responsive websites, React apps, full-stack projects",
                    "• 🤖 **IoT & Hardware** - Arduino/ESP32 projects, smart devices",
                    "• 📱 **Mobile Apps** - Cross-platform apps with React Native or Flutter"
                ])
            
            # Limit to 6 suggestions and format
            displayed_suggestions = suggestions[:6]
            
            formatted_suggestions = "\n".join(displayed_suggestions)
            
            return formatted_suggestions
            
        except Exception as e:
            logging.error(f"Error generating project suggestions: {e}")
            return """🚀 **PROJECT IDEAS FOR YOU:**

🎯 **Todo List App** - Build a simple task manager to practice fundamentals
🌐 **Personal Portfolio** - Showcase your work with a professional website  
🎮 **Simple Game** - Create a fun project like Tic-Tac-Toe or Snake
📊 **Data Tracker** - Monitor something you care about (expenses, habits, etc.)
🤖 **Chatbot** - Build an AI assistant for specific topics
🔧 **Automation Tool** - Create something to simplify your daily tasks"""
    
    def _handle_file_operation(self, parameters: Dict[str, Any]) -> bool:
        """Handle file operation commands
        
        Args:
            parameters: Command parameters including operation, path, etc.
            
        Returns:
            True if handled successfully, False otherwise
        """
        operation = parameters.get("operation", "")
        file_path = parameters.get("path", "")
        
        if not operation or not file_path:
            self.voice_system.speak("I need more information about the file operation.")
            return False
        
        # Security check for restricted paths
        if self._is_path_restricted(file_path):
            self.voice_system.speak("I'm sorry, that path is restricted for security reasons.")
            return False
        
        # Check if operation requires confirmation
        if self.security_config.get("confirm_file_operations", True):
            # In a full implementation, this would ask for confirmation
            # For MVP, we'll just proceed with a warning
            logging.warning(f"File operation without confirmation: {operation} on {file_path}")
        
        try:
            if operation == "open":
                # Open file with default application
                if os.path.exists(file_path):
                    os.startfile(file_path) if os.name == 'nt' else subprocess.call(('xdg-open', file_path))
                    return True
                else:
                    self.voice_system.speak(f"I couldn't find the file at {file_path}.")
                    return False
                    
            elif operation == "create":
                content = parameters.get("content", "")
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
                with open(file_path, 'w') as f:
                    f.write(content)
                return True
                
            elif operation == "delete":
                if os.path.exists(file_path):
                    if os.path.isdir(file_path):
                        os.rmdir(file_path)  # Will only remove if empty
                    else:
                        os.remove(file_path)
                    return True
                else:
                    self.voice_system.speak(f"The file at {file_path} doesn't exist.")
                    return False
                    
            elif operation == "list":
                if os.path.isdir(file_path):
                    files = os.listdir(file_path)
                    if files:
                        self.voice_system.speak(f"I found {len(files)} items in {file_path}.")
                        # In a full implementation, we might want to display these or speak them
                    else:
                        self.voice_system.speak(f"The directory {file_path} is empty.")
                    return True
                else:
                    self.voice_system.speak(f"{file_path} is not a directory.")
                    return False
            else:
                self.voice_system.speak(f"I don't know how to {operation} files.")
                return False
                
        except Exception as e:
            logging.error(f"Error in file operation: {e}")
            self.voice_system.speak("I had trouble with that file operation.")
            return False
    
    def _handle_app_control(self, parameters: Dict[str, Any]) -> bool:
        """Handle app control commands (launch, close, etc.) - simple and fast
        
        Args:
            parameters: Command parameters including app_name and operation
            
        Returns:
            True if handled successfully, False otherwise
        """
        app_name = parameters.get("app_name", "")
        operation = parameters.get("operation", "launch")
        
        if not app_name:
            self.voice_system.speak("I need to know which application you want me to work with.")
            return False
        
        # Check if operation requires confirmation
        if operation == "launch" and self.security_config.get("confirm_app_launch", True):
            logging.warning(f"App launch without confirmation: {app_name}")
        
        try:
            if operation == "launch":
                # Direct app launch - no suggestions, just try to launch
                return self._launch_app_with_powershell_primary(app_name)
                
            elif operation == "close":
                return self._close_app_intelligent(app_name)
                
            elif operation == "list":
                # Show available apps using PowerShell launcher
                return self._show_available_apps_powershell()
                
            else:
                self.voice_system.speak(f"I don't know how to {operation} applications.")
                return False
                
        except Exception as e:
            logging.error(f"Error in app control: {e}")
            self.voice_system.speak(f"I had trouble controlling {app_name}.")
            return False



    def _launch_app_with_powershell_primary(self, app_name: str) -> bool:
        """Launch an app using PowerShell launcher as primary method
        
        Args:
            app_name: Name of the app to launch
            
        Returns:
            True if launched successfully, False otherwise
        """
        try:
            # Use PowerShell launcher
            logging.info(f"PRIMARY: Launching {app_name} with PowerShell launcher")
            ps_result = self.powershell_launcher.launch_app(app_name)
            
            if ps_result["success"]:
                # Success with PowerShell launcher
                method = ps_result.get("method", "powershell")
                exec_time = ps_result.get("execution_time", 0)
                actual_name = ps_result.get("actual_name", app_name)
                app_info = ps_result.get("app_info", {})
                is_steam_game = ps_result.get("is_steam_game", False)
                
                # Create appropriate success message based on launch method
                if method == "steam_protocol":
                    voice_message = f"I've launched {actual_name} through Steam for you."
                    detail_message = f"Launched {actual_name} via Steam protocol"
                elif method == "uwp_app":
                    voice_message = f"I've opened {actual_name} for you."
                    detail_message = f"Launched {actual_name} (Windows Store app)"
                elif method == "common_app":
                    voice_message = f"I've opened {actual_name} for you."
                    detail_message = f"Launched {actual_name} (quick launch)"
                elif method == "hardcoded_path":
                    voice_message = f"I've opened {actual_name} for you."
                    detail_message = f"Launched {actual_name} (direct path)"
                else:
                    voice_message = f"I've launched {actual_name} for you."
                    detail_message = f"Successfully launched {actual_name}"
                
                # Show enhanced action card
                if self.dashboard_backend:
                    action_card = {
                        "type": "action_success",
                        "title": f"Opened {actual_name}",
                        "message": detail_message,
                        "app_info": {
                            "name": actual_name,
                            "original_request": app_name,
                            "launch_method": method,
                            "execution_time": f"{exec_time:.1f}s",
                            "is_steam_game": is_steam_game
                        },
                        "performance": {
                            "search_time": f"{exec_time:.1f}s",
                            "method": "PowerShell Launcher"
                        },
                        "status": "Success"
                    }
                    self.dashboard_backend._emit_ai_message(action_card, "action_card")
                
                # Provide clean voice feedback
                self.voice_system.speak(voice_message)
                
                return True
            
            # PowerShell failed - try fallback with AppManager
            logging.info(f"FALLBACK: PowerShell launcher failed, trying AppManager for {app_name}")
            
            # Search for the app using AppManager
            search_results = self.app_manager.search_apps(app_name, limit=5)
            
            if not search_results:
                # No apps found anywhere
                self.voice_system.speak(f"I couldn't find {app_name}. Please check if it's installed.")
                return False
            
            # Get the best match and launch
            best_match = search_results[0]
            app_display_name = best_match['name']
            
            success = self.app_manager.launch_app(best_match)
            
            if success:
                # Success with fallback
                if self.dashboard_backend:
                    action_card = {
                        "type": "action_success",
                        "title": f"Opened {app_display_name}",
                        "message": f"Successfully launched {app_display_name}",
                        "app_info": {
                            "name": best_match['name'],
                            "publisher": best_match.get('publisher', 'Unknown'),
                            "original_request": app_name
                        },
                        "performance": {
                            "method": "Registry Search"
                        },
                        "status": "Success"
                    }
                    self.dashboard_backend._emit_ai_message(action_card, "action_card")
                
                # Clean voice feedback
                if app_display_name.lower() != app_name.lower():
                    self.voice_system.speak(f"I found {app_display_name} and opened it for you.")
                else:
                    self.voice_system.speak(f"I've opened {app_display_name} for you.")
                return True
            else:
                # Launch failed with AppManager too
                self.voice_system.speak(f"I found {app_display_name} but couldn't launch it. Please check if it's properly installed.")
                return False
                
        except Exception as e:
            logging.error(f"Error in PowerShell primary app launch: {e}")
            self.voice_system.speak(f"I had trouble launching {app_name}.")
            return False



    def _show_available_apps_powershell(self) -> bool:
        """Show available apps using PowerShell launcher with dashboard integration"""
        try:
            # Get common apps
            common_apps = self.powershell_launcher.get_common_apps()
            
            # Show enhanced dashboard
            if self.dashboard_backend:
                action_card = {
                    "type": "app_list",
                    "title": "Available Applications",
                    "message": "Here are the applications I can launch for you:",
                    "apps": common_apps,
                    "quick_actions": [
                        {"text": "Launch", "action": "launch_app"},
                        {"text": "Search More", "action": "search_more_apps"}
                    ],
                    "categories": {
                        "browsers": ["Chrome", "Firefox"],
                        "development": ["VS Code"],
                        "gaming": ["Steam"],
                        "communication": ["Discord"],
                        "media": ["Spotify", "VLC"],
                        "system": ["Calculator", "Notepad", "Explorer"]
                    },
                    "status": "Available"
                }
                self.dashboard_backend._emit_ai_message(action_card, "action_card")
            
            # Enhanced voice response
            app_names = [app['name'] for app in common_apps[:5]]
            self.voice_system.speak(f"I can launch many applications including: {', '.join(app_names)}. You can also ask me to search for specific apps or show the full app launcher.")
            
            return True
            
        except Exception as e:
            logging.error(f"Error showing available apps: {e}")
            self.voice_system.speak("I had trouble getting the list of available applications.")
            return False

    def _close_app_intelligent(self, app_name: str) -> bool:
        """Close an app using intelligent search
        
        Args:
            app_name: Name of the app to close
            
        Returns:
            True if closed successfully, False otherwise
        """
        try:
            # Search for the app to get its executable name
            search_results = self.app_manager.search_apps(app_name, limit=1)
            
            if search_results:
                app_data = search_results[0]
                executable = app_data.get('executable', app_name)
                app_display_name = app_data['name']
            else:
                executable = app_name
                app_display_name = app_name
            
            # Close the app
            if os.name == 'nt':  # Windows
                subprocess.Popen(f"taskkill /im {executable}.exe /f", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:  # Unix-like
                subprocess.Popen(f"pkill {executable}", shell=True)
            
            self.voice_system.speak(f"I've closed {app_display_name} for you.")
            
            # Show action card
            if self.dashboard_backend:
                action_card = {
                    "type": "action_success",
                    "title": f"Closed {app_display_name}",
                    "message": f"Successfully closed {app_display_name}",
                    "status": "Success"
                }
                self.dashboard_backend._emit_ai_message(action_card, "action_card")
            
            return True
                
        except Exception as e:
            logging.error(f"Error closing app: {e}")
            self.voice_system.speak(f"I had trouble closing {app_name}.")
            return False
    
    def _handle_web_search(self, parameters: Dict[str, Any]) -> bool:
        """Handle web search commands
        
        Args:
            parameters: Command parameters including query, engine, etc.
            
        Returns:
            True if handled successfully, False otherwise
        """
        query = parameters.get("query", "")
        engine = parameters.get("engine", "google")
        url = parameters.get("url", "")
        
        try:
            if url:
                # Open specific URL
                webbrowser.open(url)
                return True
                
            elif query:
                # Perform search based on engine
                if engine == "google":
                    search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
                elif engine == "bing":
                    search_url = f"https://www.bing.com/search?q={query.replace(' ', '+')}"
                elif engine == "duckduckgo":
                    search_url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}"
                else:
                    # Default to Google
                    search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
                    
                webbrowser.open(search_url)
                return True
                
            else:
                self.voice_system.speak("I need a search query or URL to continue.")
                return False
                
        except Exception as e:
            logging.error(f"Error in web search: {e}")
            self.voice_system.speak("I had trouble with that web search.")
            return False
    
    def _handle_system_command(self, parameters: Dict[str, Any]) -> bool:
        """Handle system commands
        
        Args:
            parameters: Command parameters including command string
            
        Returns:
            True if handled successfully, False otherwise
        """
        command = parameters.get("command", "")
        operation = parameters.get("operation", "").lower()
        
        if not command and not operation:
            self.voice_system.speak("I need to know what system command to run.")
            return False
        
        try:
            # Handle common system operations
            if operation in ["shutdown", "power off", "turn off computer"] or "shutdown" in command.lower():
                self.voice_system.speak("Shutting down the computer.")
                subprocess.run("shutdown /s /t 0", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                return True
                
            elif operation in ["restart", "reboot"] or "restart" in command.lower():
                self.voice_system.speak("Restarting the computer.")
                subprocess.run("shutdown /r /t 0", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                return True
                
            elif operation in ["sleep", "hibernate"] or "sleep" in command.lower():
                self.voice_system.speak("Putting the computer to sleep.")
                subprocess.run("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                return True
                
            elif operation in ["lock", "lock screen"] or "lock" in command.lower():
                self.voice_system.speak("Locking the screen.")
                subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                return True
                
            elif command and not any(sys_cmd in command.lower() for sys_cmd in ["shutdown", "restart", "sleep", "lock"]):
                # Execute custom command with caution (but not system commands)
                self.voice_system.speak(f"Executing: {command}")
                subprocess.run(command, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                return True
                
            else:
                self.voice_system.speak("I don't recognize that system command.")
                return False
                
        except Exception as e:
            logging.error(f"Error executing system command: {e}")
            self.voice_system.speak("I had trouble executing that system command.")
            return False
    
    def _handle_settings(self, parameters: Dict[str, Any]) -> bool:
        """Handle settings change commands
        
        Args:
            parameters: Command parameters including setting type and value
            
        Returns:
            True if handled successfully, False otherwise
        """
        setting_type = parameters.get("setting_type", "")
        value = parameters.get("value", "")
        
        if not setting_type or value is None:
            self.voice_system.speak("I need to know what setting to change.")
            return False
        
        try:
            if setting_type == "voice":
                # Change voice settings
                if isinstance(value, str):
                    return self.voice_system.change_voice(value)
                return False
                
            elif setting_type == "hotkey":
                # This would be handled by a hotkey manager
                self.voice_system.speak("Hotkey changes are not implemented yet.")
                return False
                
            else:
                self.voice_system.speak(f"I don't know how to change {setting_type} settings.")
                return False
                
        except Exception as e:
            logging.error(f"Error changing settings: {e}")
            self.voice_system.speak("I had trouble changing that setting.")
            return False
    
    def _handle_fan_control(self, parameters: Dict[str, Any]) -> bool:
        """Handle fan control commands with smart status checking
        
        Args:
            parameters: Command parameters including operation, speed, etc.
            
        Returns:
            True if handled successfully, False otherwise
        """
        # Check if ESP32 controller is available
        if not self.esp32_controller:
            logging.warning("Fan control requested but ESP32 controller is not available")
            self.voice_system.speak("I'm sorry, I can't control the fan right now. The ESP32 controller is not available. Please check the network connection and ESP32 device.")
            return False
            
        operation = parameters.get("operation", "").lower()
        speed = parameters.get("speed", "").lower()
        
        try:
            # Handle "status" or "check" commands with smart status reporting
            if "status" in operation or "check" in operation or "state" in operation:
                status_message = self.esp32_controller.get_human_readable_status()
                logging.info(f"Fan status check: {status_message}")
                # Actually speak the status to the user
                self.voice_system.speak(status_message)
                return True
                
            elif operation == "on" or operation == "turn_on" or operation == "start":
                # Turn on the fan
                success = self.esp32_controller.turn_on()
                return success
                
            elif operation == "off" or operation == "turn_off" or operation == "stop":
                # Turn off the fan
                success = self.esp32_controller.turn_off()
                return success
                
            elif "mode" in operation:
                # Change fan mode - more forgiving with command wording
                success = self.esp32_controller.change_mode()
                return success
                
            elif "speed" in operation or "cycle" in operation:
                # More forgiving speed detection
                # If speed not explicitly provided, check if it's part of the operation
                if not speed:
                    # Try to extract speed from operation
                    if "1" in operation or "one" in operation or "low" in operation:
                        speed = "1"
                    elif "2" in operation or "two" in operation or "medium" in operation:
                        speed = "2" 
                    elif "3" in operation or "three" in operation or "high" in operation:
                        speed = "3"
                    elif "cycle" in operation or "change" in operation or "next" in operation:
                        # Use /on endpoint for smart cycling (ESP32 handles speed increment)
                        success = self.esp32_controller.cycle_speed()
                        return success
                
                # Set fan speed based on parameter using the new set_speed method
                if speed == "1" or speed == "one" or speed == "low":
                    success = self.esp32_controller.set_speed(1)
                elif speed == "2" or speed == "two" or speed == "medium":
                    success = self.esp32_controller.set_speed(2)
                elif speed == "3" or speed == "three" or speed == "high":
                    success = self.esp32_controller.set_speed(3)
                else:
                    # If no specific speed, use /on endpoint for cycling
                    success = self.esp32_controller.cycle_speed()
                
                return success
                
            else:
                # Only speak this if there's an actual error understanding the command
                self.voice_system.speak("I'm not sure how to control the fan that way.")
                return False
                
        except Exception as e:
            logging.error(f"Error in fan control: {e}")
            self.voice_system.speak("I encountered an error while trying to control the fan.")
            return False
    
    def _handle_unknown(self, parameters: Dict[str, Any]) -> bool:
        """Handle unknown commands with conversational AI
        
        Args:
            parameters: Command parameters including original query
            
        Returns:
            True if handled successfully, False otherwise
        """
        original_query = parameters.get("original_query", "")
        
        # For unknown commands, check if this is actually a conversational request
        # rather than a failed command recognition
        conversational_keywords = [
            "how are you", "tell me", "what do you think", "can you", "do you",
            "have you", "would you", "could you", "should i", "what if",
            "why", "explain", "help me understand", "i want to know",
            "chat", "talk", "conversation", "discuss"
        ]
        
        is_conversational = any(keyword in original_query.lower() for keyword in conversational_keywords)
        
        if is_conversational or len(original_query.strip()) > 20:
            # This seems like a conversation request, not a failed command
            # Use the LLM response directly for natural conversation
            self.voice_system.speak("I'm here to chat with you! Let me think about that...")
            return True
        else:
            # This might be a failed command recognition
            self.voice_system.speak("I'm not sure what you meant. Can you try rephrasing that, or would you like to know what I can help you with?")
            return False
    
    def _is_path_restricted(self, path: str) -> bool:
        """Check if a file path is in a restricted area
        
        Args:
            path: File path to check
            
        Returns:
            True if path is restricted, False otherwise
        """
        path = os.path.abspath(path)
        restricted_paths = self.security_config.get("restricted_paths", [])
        
        for restricted in restricted_paths:
            if path.startswith(restricted):
                logging.warning(f"Attempted access to restricted path: {path}")
                return True
                
        return False
    
    def provide_proactive_suggestions(self, user_query: str) -> None:
        """Provide proactive suggestions based on user input and history"""
        # DISABLED: Proactive suggestions removed per user request
        pass
    
    def _show_available_apps_enhanced(self) -> bool:
        """Show a list of available applications using enhanced app discovery"""
        try:
            # Get installed apps using AppManager - force refresh if too few apps
            apps = self.app_manager.get_installed_apps()
            
            # If we have very few apps, it might be a fallback - force refresh
            if len(apps) < 50:
                logging.info("Too few apps detected, forcing refresh...")
                apps = self.app_manager.get_installed_apps(force_refresh=True)
            
            # Get apps organized by categories
            categories = self.app_manager.get_app_categories()
            
            # Get recently used apps
            recent_apps = self.app_manager.get_recently_used_apps(limit=5)
            
            # Create enhanced action card for dashboard
            if self.dashboard_backend:
                action_card = {
                    "type": "enhanced_app_list",
                    "title": "Available Applications",
                    "subtitle": f"Found {len(apps)} installed applications",
                    "message": "Here are your installed applications organized by category:",
                    "categories": categories,
                    "recent_apps": recent_apps,
                    "total_count": len(apps),
                    "status": "Ready"
                }
                self.dashboard_backend._emit_ai_message(action_card, "action_card")
                
                # Set pending action for app selection
                self.dashboard_backend.set_pending_action("app_selection", {
                    "apps": apps,
                    "categories": categories
                }, "Which app would you like me to open?")
            
            # Spoken response with category breakdown
            category_counts = {cat: len(apps) for cat, apps in categories.items() if apps}
            top_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            
            if top_categories:
                category_summary = ", ".join([f"{count} {cat.lower()}" for cat, count in top_categories])
                self.voice_system.speak(f"I found {len(apps)} applications including {category_summary}. Which app would you like me to open?")
            else:
                self.voice_system.speak(f"I found {len(apps)} applications available. Which app would you like me to open?")
            
            return True
            
        except Exception as e:
            logging.error(f"Error showing available apps: {e}")
            self.voice_system.speak("I had trouble finding available applications.")
            return False
    
    def _show_available_apps(self) -> bool:
        """Legacy method - redirect to enhanced version"""
        return self._show_available_apps_enhanced()
    
    def _get_system_apps(self) -> list:
        """Get list of installed system applications"""
        apps = []
        
        try:
            if os.name == 'nt':  # Windows
                # Common Windows applications
                common_apps = [
                    {"name": "Google Chrome", "path": "chrome.exe"},
                    {"name": "Microsoft Edge", "path": "msedge.exe"},
                    {"name": "Firefox", "path": "firefox.exe"},
                    {"name": "Visual Studio Code", "path": "code.exe"},
                    {"name": "Notepad", "path": "notepad.exe"},
                    {"name": "Calculator", "path": "calc.exe"},
                    {"name": "File Explorer", "path": "explorer.exe"},
                    {"name": "Command Prompt", "path": "cmd.exe"},
                    {"name": "PowerShell", "path": "powershell.exe"},
                    {"name": "Paint", "path": "mspaint.exe"},
                    {"name": "Word", "path": "winword.exe"},
                    {"name": "Excel", "path": "excel.exe"},
                    {"name": "PowerPoint", "path": "powerpnt.exe"},
                    {"name": "Outlook", "path": "outlook.exe"},
                    {"name": "Teams", "path": "ms-teams.exe"},
                    {"name": "Discord", "path": "discord.exe"},
                    {"name": "Slack", "path": "slack.exe"},
                    {"name": "Spotify", "path": "spotify.exe"},
                    {"name": "VLC Media Player", "path": "vlc.exe"},
                    {"name": "OBS Studio", "path": "obs64.exe"}
                ]
                
                # Check which apps actually exist
                for app in common_apps:
                    if self._app_exists(app["path"]):
                        apps.append(app)
                        
            else:  # Unix-like
                # Common Unix applications
                common_apps = [
                    {"name": "Firefox", "path": "firefox"},
                    {"name": "Chrome", "path": "google-chrome"},
                    {"name": "Visual Studio Code", "path": "code"},
                    {"name": "Terminal", "path": "gnome-terminal"},
                    {"name": "File Manager", "path": "nautilus"},
                    {"name": "Text Editor", "path": "gedit"},
                    {"name": "Calculator", "path": "gnome-calculator"}
                ]
                
                for app in common_apps:
                    if self._app_exists(app["path"]):
                        apps.append(app)
            
            return apps[:15]  # Limit to 15 apps
            
        except Exception as e:
            logging.error(f"Error getting system apps: {e}")
            return []
    
    def _app_exists(self, app_path: str) -> bool:
        """Check if an application exists on the system"""
        try:
            # Try to find the executable
            import shutil
            return shutil.which(app_path) is not None
        except:
            return False
    
    def _is_website_request(self, app_name: str) -> bool:
        """Check if the request is for a website rather than an app"""
        websites = [
            "youtube", "google", "github", "stackoverflow", "reddit", 
            "facebook", "twitter", "instagram", "linkedin", "gmail",
            "outlook", "amazon", "netflix", "spotify web", "discord web",
            "whatsapp", "telegram", "slack web", "notion", "figma"
        ]
        return any(site in app_name for site in websites)
    
    def _handle_website_opening(self, website_name: str) -> bool:
        """Handle opening websites intelligently"""
        try:
            # Map common website names to URLs
            website_urls = {
                "youtube": "https://www.youtube.com",
                "google": "https://www.google.com",
                "github": "https://www.github.com",
                "stackoverflow": "https://stackoverflow.com",
                "reddit": "https://www.reddit.com",
                "facebook": "https://www.facebook.com",
                "twitter": "https://www.twitter.com",
                "instagram": "https://www.instagram.com",
                "linkedin": "https://www.linkedin.com",
                "gmail": "https://mail.google.com",
                "outlook": "https://outlook.live.com",
                "amazon": "https://www.amazon.com",
                "netflix": "https://www.netflix.com",
                "spotify web": "https://open.spotify.com",
                "discord web": "https://discord.com/app",
                "whatsapp": "https://web.whatsapp.com",
                "telegram": "https://web.telegram.org",
                "slack web": "https://slack.com",
                "notion": "https://www.notion.so",
                "figma": "https://www.figma.com"
            }
            
            # Find matching URL
            url = None
            for site, site_url in website_urls.items():
                if site in website_name:
                    url = site_url
                    break
            
            if url:
                import webbrowser
                webbrowser.open(url)
                
                # Show action card
                if self.dashboard_backend:
                    action_card = {
                        "type": "url_opened",
                        "title": f"Opened {website_name.title()}",
                        "message": f"Successfully opened {url} in your default browser",
                        "status": "Success"
                    }
                    self.dashboard_backend._emit_ai_message(action_card, "action_card")
                
                self.voice_system.speak(f"Opening {website_name} in your browser.")
                return True
            else:
                self.voice_system.speak(f"I couldn't find the URL for {website_name}.")
                return False
                
        except Exception as e:
            logging.error(f"Error opening website: {e}")
            self.voice_system.speak(f"I had trouble opening {website_name}.")
            return False
    
    def _handle_project_request(self, parameters: Dict[str, Any]) -> bool:
        """Handle project-related requests"""
        try:
            github_path = "G:\\GitHub"
            
            # Check if user wants to create a new project
            original_query = parameters.get("original_query", "").lower()
            if "new project" in original_query or "create project" in original_query:
                return self._create_new_project(github_path)
            
            # Show existing projects
            return self._show_projects(github_path)
            
        except Exception as e:
            logging.error(f"Error handling project request: {e}")
            self.voice_system.speak("I had trouble with your project request.")
            return False
    
    def _show_projects(self, github_path: str) -> bool:
        """Show available projects in the GitHub folder"""
        try:
            logging.info(f"Starting _show_projects with path: {github_path}")
            
            if not os.path.exists(github_path):
                logging.warning(f"GitHub path does not exist: {github_path}")
                response_text = f"The GitHub folder doesn't exist at {github_path}. Would you like me to create it?"
                
                # Emit to dashboard if available
                if self.dashboard_backend:
                    self.dashboard_backend._emit_ai_message(response_text, "response")
                    self.voice_system.speak("The GitHub folder doesn't exist. Would you like me to create it?")
                else:
                    self.voice_system.speak("The GitHub folder doesn't exist. Would you like me to create it?")
                return False
            
            logging.info(f"GitHub path exists, listing contents...")
            
            # Get list of project folders with basic details (avoid slow operations)
            projects = []
            for item in os.listdir(github_path):
                item_path = os.path.join(github_path, item)
                if os.path.isdir(item_path):
                    # Get basic info about the project (avoid slow size calculation)
                    project_info = {
                        "name": item,
                        "path": item_path,
                        "type": self._detect_project_type_fast(item_path),
                        "size": "N/A"  # Skip size calculation for performance
                    }
                    projects.append(project_info)
            
            logging.info(f"Found {len(projects)} projects")
            
            if not projects:
                logging.info("No projects found, showing empty state")
                response_text = f"No projects found in your GitHub folder ({github_path}). Would you like me to create a new project?"
                
                # Show empty state in dashboard
                if self.dashboard_backend:
                    action_card = {
                        "type": "project_list_empty",
                        "title": "No Projects Found",
                        "subtitle": f"Your GitHub folder is empty",
                        "message": "Get started by creating your first project!",
                        "buttons": [
                            {"label": "Create New Project", "action": "create_new"},
                            {"label": "Open GitHub Folder", "action": "open_folder"}
                        ],
                        "status": "Empty"
                    }
                    self.dashboard_backend._emit_ai_message(action_card, "action_card")
                    self.voice_system.speak("No projects found in your GitHub folder. Would you like me to create a new project?")
                else:
                    self.voice_system.speak("No projects found in your GitHub folder. Would you like me to create a new project?")
                return True
            
            logging.info("Sorting projects and preparing display...")
            
            # Sort projects by name
            projects.sort(key=lambda x: x["name"].lower())
            
            # Dashboard display (priority)
            if self.dashboard_backend:
                logging.info("Displaying projects in dashboard...")
                
                # Create response text with project list
                response_text = f"Found {len(projects)} projects in your GitHub folder:\n\n"
                for i, project in enumerate(projects, 1):
                    response_text += f"{i}. **{project['name']}** ({project['type']})\n"
                response_text += f"\nTo open a project, say the project name or click on it below."
                
                # Show projects in dashboard
                action_card = {
                    "type": "project_list",
                    "title": "Your Projects",
                    "subtitle": f"Found {len(projects)} projects in GitHub folder",
                    "message": "Click on any project to open it in VSCode:",
                    "items": projects,
                    "buttons": [
                        {"label": "Create New Project", "action": "create_new"},
                        {"label": "Open GitHub Folder", "action": "open_folder"}
                    ],
                    "status": "Ready"
                }
                
                logging.info("Emitting action card to dashboard...")
                self.dashboard_backend._emit_ai_message(action_card, "action_card")
            
                logging.info("Emitting response text to dashboard...")
                self.dashboard_backend._emit_ai_message(response_text, "response")
                
                logging.info("Setting pending action...")
                # Set pending action for project selection
                self.dashboard_backend.set_pending_action("project_selection", {
                    "projects": projects,
                    "github_path": github_path
                }, "Which project would you like to work on?")
                
                logging.info("Speaking response...")
                # Simpler voice response for dashboard mode
                self.voice_system.speak(f"I found {len(projects)} projects. Which one would you like to work on?")
            else:
                logging.info("Voice-only mode (no dashboard)")
                # Voice-only response (fallback)
                project_names = [p["name"] for p in projects[:5]]  # Limit to first 5 for voice
                if len(projects) <= 5:
                    projects_list = ", ".join(project_names)
                    self.voice_system.speak(f"I found {len(projects)} projects: {projects_list}. Which project would you like to work on?")
                else:
                    self.voice_system.speak(f"I found {len(projects)} projects including {', '.join(project_names[:3])} and others. Which project would you like to work on?")
            
            logging.info("_show_projects completed successfully")
            return True
            
        except Exception as e:
            logging.error(f"Error showing projects: {e}")
            import traceback
            logging.error(f"Full traceback: {traceback.format_exc()}")
            error_msg = "I had trouble accessing your projects folder."
            if self.dashboard_backend:
                self.dashboard_backend._emit_ai_message(error_msg, "error")
            self.voice_system.speak(error_msg)
            return False
    
    def _create_new_project(self, github_path: str) -> bool:
        """Create a new project folder and open it in VSCode"""
        try:
            # Ensure GitHub folder exists
            if not os.path.exists(github_path):
                os.makedirs(github_path)
            
            # Generate project name with timestamp
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            project_name = f"new_project_{timestamp}"
            project_path = os.path.join(github_path, project_name)
            
            # Create project folder
            os.makedirs(project_path)
            
            # Create basic files
            readme_content = f"""# {project_name}

A new project created by Aiden AI Assistant.

## Getting Started

Add your project description here.

## Features

- List your features here

## Usage

Add usage instructions here.

Created on: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
            
            with open(os.path.join(project_path, "README.md"), "w") as f:
                f.write(readme_content)
            
            # Open in VSCode
            if self._app_exists("code") or self._app_exists("code.exe"):
                subprocess.Popen(f'code "{project_path}"', shell=True)
                
                # Show action card
                if self.dashboard_backend:
                    action_card = {
                        "type": "project_created",
                        "title": "New Project Created",
                        "message": f"Successfully created '{project_name}' and opened it in VSCode",
                        "items": [
                            {"name": "Open in File Explorer", "path": project_path},
                            {"name": "View README.md", "path": os.path.join(project_path, "README.md")}
                        ],
                        "status": "Success"
                    }
                    self.dashboard_backend._emit_ai_message(action_card, "action_card")
                
                self.voice_system.speak(f"I've created a new project called {project_name} and opened it in Visual Studio Code. The project is ready for you to start coding!")
                return True
            else:
                self.voice_system.speak(f"I've created the project folder {project_name}, but I couldn't find Visual Studio Code to open it.")
                return True
                
        except Exception as e:
            logging.error(f"Error creating new project: {e}")
            self.voice_system.speak("I had trouble creating the new project.")
            return False
    
    def _detect_project_type_fast(self, project_path: str) -> str:
        """Fast project type detection - only check for key files"""
        try:
            # Only check for a few key files to avoid slow directory scanning
            key_files = ["package.json", "requirements.txt", "setup.py", "pom.xml", "cargo.toml", "go.mod", "index.html"]
            
            for key_file in key_files:
                if os.path.exists(os.path.join(project_path, key_file)):
                    if key_file == "package.json":
                        return "JavaScript/Node.js"
                    elif key_file in ["requirements.txt", "setup.py"]:
                        return "Python"
                    elif key_file == "pom.xml":
                        return "Java"
                    elif key_file == "cargo.toml":
                        return "Rust"
                    elif key_file == "go.mod":
                        return "Go"
                    elif key_file == "index.html":
                        return "Web"
            
            return "Project"
        except Exception:
            return "Unknown"

    def _detect_project_type(self, project_path: str) -> str:
        """Detect the type of project based on files in the directory"""
        try:
            files = os.listdir(project_path)
            file_names = [f.lower() for f in files]
            
            # Check for specific project indicators
            if "package.json" in file_names:
                if "src" in file_names and any("react" in f for f in files):
                    return "React"
                elif "public" in file_names:
                    return "Node.js"
                else:
                    return "JavaScript"
            elif "requirements.txt" in file_names or "setup.py" in file_names:
                return "Python"
            elif "pom.xml" in file_names:
                return "Java"
            elif "cargo.toml" in file_names:
                return "Rust"
            elif "go.mod" in file_names:
                return "Go"
            elif "composer.json" in file_names:
                return "PHP"
            elif any(f.endswith('.sln') for f in file_names):
                return "C#/.NET"
            elif "index.html" in file_names:
                return "Web"
            elif "readme.md" in file_names or "readme.txt" in file_names:
                return "Documentation"
            else:
                return "Mixed"
        except Exception:
            return "Unknown"
    
    def _get_folder_size(self, folder_path: str) -> str:
        """Get human-readable folder size"""
        try:
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(folder_path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(filepath)
                    except (OSError, FileNotFoundError):
                        pass
            
            # Convert to human readable format
            for unit in ['B', 'KB', 'MB', 'GB']:
                if total_size < 1024.0:
                    return f"{total_size:.1f} {unit}"
                total_size /= 1024.0
            return f"{total_size:.1f} TB"
        except Exception:
            return "Unknown"

    def _handle_end_conversation(self, parameters: Dict[str, Any]) -> bool:
        """Handle end conversation commands
        
        Args:
            parameters: Command parameters
            
        Returns:
            True if handled successfully, False otherwise
        """
        # Log the conversation ending
        logging.info("Conversation ended by user request")
        
        # Nothing specific to do here - conversation state is handled by dashboard_backend
        # Returning True indicates successful handling
        return True
    
    def _handle_stop_task(self, parameters: Dict[str, Any]) -> bool:
        """Handle stop current task commands
        
        Args:
            parameters: Command parameters
            
        Returns:
            True if handled successfully, False otherwise
        """
        # Log the stop request
        logging.info("Current task stopped by user request")
        
        # Nothing specific to do here - dashboard_backend handles stopping current tasks
        return True
