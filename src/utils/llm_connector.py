"""
LLM Connector for Aiden
Handles interactions with language models for processing commands
"""
import os
import json
import logging
import subprocess
from typing import Dict, Any, Optional, List, Tuple
import tempfile
import platform

class LLMConnector:
    """Handles interactions with language models"""
    
    def __init__(self, config_manager):
        """Initialize the LLM connector
        
        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager
        self.llm_config = config_manager.get_config("llm")
        self.user_profile = config_manager.get_user_profile()
        
        # Get LLM engine configuration
        self.engine = self.llm_config.get("engine", "tgpt")
        self.system_prompt = self.llm_config.get("system_prompt", "")
        
        # tgpt specific configuration
        if self.engine == "tgpt":
            self.tgpt_path = self.llm_config.get("tgpt_path", "tgpt")
        
        # Store the last command for context
        self.last_command = ""
            
        logging.info(f"LLM connector initialized with engine: {self.engine}")
    
    def process_command(self, command_text: str) -> Dict[str, Any]:
        """Process a command with the LLM
        
        Args:
            command_text: The command text to process
            
        Returns:
            Dictionary containing the parsed command information
        """
        # Store the command for context
        self.last_command = command_text
        
        # Get context for the prompt
        context = self._build_context()
        
        # Get user's preferred address
        form_of_address = self.user_profile["personal"]["form_of_address"]
        
        # Build the full prompt
        full_prompt = f"{context}\n\nThe user said: \"{command_text}\"\n\n"
        full_prompt += f"""You are Aiden, an AI assistant. Be helpful and direct. Use "Boss" in your responses, not "Boss" or any other title.

Respond ONLY in JSON format with the following structure:
{{
    "action": "action_name",
    "parameters": {{
        "param1": "value1",
        "original_query": "exact user input",
        ...
    }},
    "response": "Your response to the user"
}}

IMPORTANT: Always address the user as "{form_of_address}" in your responses.

Valid actions include:
- "provide_information": For answering questions, getting system info, listing projects
- "file_operation": For file/folder operations
- "app_control": For launching or controlling applications
- "web_search": For web searches and opening URLs
- "system_command": For system commands
- "change_settings": For changing assistant settings
- "fan_control": For controlling the fan connected to ESP32
- "unknown": If you cannot determine the action

IMPORTANT COMMAND PATTERNS:
1. App launching: "open [app]", "launch [app]", "start [app]" = app_control
2. System commands: "lock computer", "shutdown", "restart", "sleep" = system_command
3. Fan control: "turn on fan", "turn off fan", "fan status", "set fan speed" = fan_control
4. Project access: "open project", "show projects", "list projects" = provide_information with query="list my projects"
5. Web search: "search for [query]", "google [query]" = web_search
6. Information: "what time", "what date", "who created you" = provide_information

CRITICAL - COMMAND CLASSIFICATION RULES:
- ANY command mentioning "fan" = fan_control action (NOT system_command)
- "lock computer/screen" = system_command with operation="lock"
- "shutdown/power off/turn off computer" = system_command with operation="shutdown"  
- "restart/reboot" = system_command with operation="restart"
- "sleep/hibernate" = system_command with operation="sleep"
- "open/launch/start [app]" = app_control with app_name and operation="launch"

SCHEDULING PATTERNS:
- "shutdown in 10 minutes" = system_command with operation="shutdown" 
- "restart in 5 minutes" = system_command with operation="restart"
- "sleep in 30 minutes" = system_command with operation="sleep"

For app control commands, use parameters like:
- app_name: Extract the EXACT app name the user mentioned, don't modify it
- operation: "launch", "open", "start", "close"

RESPONSE GUIDELINES:
- For system commands: Give brief confirmation like "Shutting down now, Boss" or "I'll restart in 10 minutes, Boss"
- For app launching: Say "Let me find and open that for you, Boss"
- For time-based commands: Give simple confirmation without asking for verification
- NEVER ask "You can say 'yes' to confirm" or similar verification prompts
- Be direct and execute commands as requested

Examples:
- "shutdown in 10 minutes" → "I'll shut down the computer in 10 minutes, Boss"
- "open chrome" → "Let me find Chrome for you, Boss"

IMPORTANT: For fan status/check commands, do NOT provide the actual fan status in your response. 
Just say you're checking it. The system will get the real status from the hardware.

ALWAYS include the original_query in parameters for context.

Examples:
1. "open chrome" becomes:
{{
    "action": "app_control",
    "parameters": {{
        "app_name": "chrome",
        "operation": "launch",
        "original_query": "open chrome"
    }},
    "response": "Let me find Chrome for you, {form_of_address}."
}}

2. "list my projects" becomes:
{{
    "action": "provide_information",
    "parameters": {{
        "query": "list my projects",
        "original_query": "list my projects"
    }},
    "response": "Let me show you your projects, {form_of_address}."
}}

3. "search for AI tutorials" becomes:
{{
    "action": "web_search",
    "parameters": {{
        "query": "AI tutorials",
        "engine": "google",
        "original_query": "search for AI tutorials"
    }},
    "response": "Searching for AI tutorials on Google, {form_of_address}."
}}

4. "what's the fan status" becomes:
{{
    "action": "fan_control",
    "parameters": {{
        "operation": "status",
        "original_query": "what's the fan status"
    }},
    "response": "Let me check the fan status for you, {form_of_address}."
}}

5. "lock the computer" becomes:
{{
    "action": "system_command",
    "parameters": {{
        "operation": "lock",
        "original_query": "lock the computer"
    }},
    "response": "Locking the screen for you, {form_of_address}."
}}

6. "turn off fan" becomes:
{{
    "action": "fan_control",
    "parameters": {{
        "operation": "off",
        "original_query": "turn off fan"
    }},
    "response": "Turning off the fan for you, {form_of_address}."
}}

7. "shutdown computer" becomes:
{{
    "action": "system_command",
    "parameters": {{
        "operation": "shutdown",
        "original_query": "shutdown computer"
    }},
    "response": "Shutting down the computer, {form_of_address}."
}}

8. "shutdown in 10 minutes" becomes:
{{
    "action": "system_command",
    "parameters": {{
        "operation": "shutdown",
        "original_query": "shutdown in 10 minutes"
    }},
    "response": "I'll shut down the computer in 10 minutes, {form_of_address}."
}}

9. "change to 20 minutes" becomes:
{{
    "action": "system_command",
    "parameters": {{
        "operation": "modify",
        "original_query": "change to 20 minutes"
    }},
    "response": "I'll update the time for you, {form_of_address}."
}}

10. "cancel shutdown" becomes:
{{
    "action": "system_command",
    "parameters": {{
        "operation": "abort",
        "original_query": "cancel shutdown"
    }},
    "response": "I'll cancel that for you, {form_of_address}."
}}

If the user wants natural conversation without a specific command, use:
{{
    "action": "provide_information", 
    "parameters": {{
        "query": "conversation",
        "original_query": "user's exact words"
    }},
    "response": "Your conversational response (remember to address them as {form_of_address})"
}}
"""
        # Process with the appropriate LLM engine
        if self.engine == "tgpt":
            print(f"Connecting to AI with tgpt...")
            result = self._process_with_tgpt(full_prompt)
            print(f"AI response received")
            
            # Ensure original_query is in parameters
            if "parameters" not in result:
                result["parameters"] = {}
            if "original_query" not in result["parameters"]:
                result["parameters"]["original_query"] = command_text
                
            return result
        else:
            logging.error(f"Unsupported LLM engine: {self.engine}")
            print(f"ERROR: Unsupported AI engine: {self.engine}")
            print(f"Please make sure tgpt is installed and available in your PATH")
            print(f"You can install it from: https://github.com/aandrew-me/tgpt")
            return {
                "action": "unknown",
                "parameters": {"original_query": command_text},
                "response": f"I'm sorry, {form_of_address}. I'm having trouble connecting to my AI."
            }
    
    def _build_context(self) -> str:
        """Build context information for the prompt
        
        Returns:
            String containing context information
        """
        user_name = self.user_profile["personal"]["name"]
        form_of_address = self.user_profile["personal"]["form_of_address"]
        
        # Get recent commands (up to 5)
        recent_commands = self.user_profile["history"]["last_commands"][-5:] if self.user_profile["history"]["last_commands"] else []
        
        context = self.system_prompt + "\n\n"
        context += f"User information:\n"
        context += f"- Name: {user_name}\n"
        context += f"- Preferred address: {form_of_address}\n"
        
        if recent_commands:
            context += f"\nRecent commands:\n"
            for cmd in recent_commands:
                context += f"- {cmd}\n"
        
        return context
    
    def _process_with_tgpt(self, prompt: str) -> Dict[str, Any]:
        """Process a prompt with tgpt
        
        Args:
            prompt: The prompt to process
            
        Returns:
            Dictionary containing the parsed response
        """
        try:
            # Write prompt to temporary file with UTF-8 encoding
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as temp:
                temp_file_path = temp.name
                # Clean the prompt to remove problematic Unicode characters
                cleaned_prompt = prompt.encode('ascii', errors='replace').decode('ascii')
                temp.write(cleaned_prompt)
            
            # Build command based on OS
            if platform.system() == "Windows":
                cmd = f'type "{temp_file_path}" | {self.tgpt_path}'
            else:  # Unix-like
                cmd = f'cat "{temp_file_path}" | {self.tgpt_path}'
            
            # Print information about what's happening
            print(f"Executing command: {cmd}")
            
            # Execute command
            process = subprocess.Popen(
                cmd, 
                shell=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            print(f"Waiting for AI response...")
            stdout, stderr = process.communicate()
            
            # Clean up temp file
            os.unlink(temp_file_path)
            
            if process.returncode != 0:
                logging.error(f"tgpt error: {stderr}")
                print(f"ERROR connecting to AI: {stderr}")
                print("Please make sure tgpt is installed and configured correctly")
                return self._default_error_response()
            
            # Clean the output from tgpt (remove loading spinners, etc.)
            clean_output = self._clean_tgpt_output(stdout)
            print(f"AI response cleaned and ready for processing")
            
            # Parse the response
            return self._parse_llm_response(clean_output)
            
        except Exception as e:
            logging.error(f"Error processing with tgpt: {e}")
            return self._default_error_response()
    
    def _clean_tgpt_output(self, output: str) -> str:
        """Clean the tgpt output by removing loading indicators and spinner characters
        
        Args:
            output: Raw output from tgpt
            
        Returns:
            Cleaned output string
        """
        # Get user's preferred address for fallback responses
        form_of_address = self.user_profile["personal"]["form_of_address"]
        
        # Remove loading indicators and spinner characters
        lines = output.split('\n')
        cleaned_lines = []
        
        # Common spinner characters and loading patterns
        spinner_chars = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷', '|', '/', '-', '\\']
        loading_patterns = [
            'Loading', 'loading', 'LOADING',
            'Processing', 'processing', 'PROCESSING'
        ]
        
        for line in lines:
            # Skip if line contains any spinner character
            if any(spinner in line for spinner in spinner_chars):
                continue
                
            # Skip lines that contain loading text
            skip_line = False
            for pattern in loading_patterns:
                if pattern in line:
                    skip_line = True
                    break
                    
            if skip_line:
                continue
                
            # Skip lines with just dots (like "...")
            if line.strip() and all(c == '.' for c in line.strip()):
                continue
                
            cleaned_lines.append(line)
        
        cleaned_output = '\n'.join(cleaned_lines)
    
        # Check if we have a proper response
        if not cleaned_output.strip() or len(cleaned_output.strip()) < 20:
            # Improved hard-coded responses for common commands
            command_lower = self.last_command.lower().strip()
            
            # App launching commands
            if any(phrase in command_lower for phrase in ["open chrome", "launch chrome", "start chrome", "chrome"]):
                return f"""{{\"action\": \"app_control\", \"parameters\": {{\"app_name\": \"chrome\", \"operation\": \"launch\", \"original_query\": \"{self.last_command}\"}}, \"response\": \"Opening Chrome for you, {form_of_address}.\"}}"""
            elif any(phrase in command_lower for phrase in ["open vscode", "launch vscode", "start vscode", "visual studio code", "vs code"]):
                return f"""{{\"action\": \"app_control\", \"parameters\": {{\"app_name\": \"vscode\", \"operation\": \"launch\", \"original_query\": \"{self.last_command}\"}}, \"response\": \"Opening Visual Studio Code for you, {form_of_address}.\"}}"""
            elif any(phrase in command_lower for phrase in ["open edge", "launch edge", "start edge", "microsoft edge"]):
                return f"""{{\"action\": \"app_control\", \"parameters\": {{\"app_name\": \"edge\", \"operation\": \"launch\", \"original_query\": \"{self.last_command}\"}}, \"response\": \"Opening Microsoft Edge for you, {form_of_address}.\"}}"""
            elif any(phrase in command_lower for phrase in ["open firefox", "launch firefox", "start firefox"]):
                return f"""{{\"action\": \"app_control\", \"parameters\": {{\"app_name\": \"firefox\", \"operation\": \"launch\", \"original_query\": \"{self.last_command}\"}}, \"response\": \"Opening Firefox for you, {form_of_address}.\"}}"""
            elif any(phrase in command_lower for phrase in ["open notepad", "launch notepad", "start notepad"]):
                return f"""{{\"action\": \"app_control\", \"parameters\": {{\"app_name\": \"notepad\", \"operation\": \"launch\", \"original_query\": \"{self.last_command}\"}}, \"response\": \"Opening Notepad for you, {form_of_address}.\"}}"""
            elif any(phrase in command_lower for phrase in ["open calculator", "launch calculator", "start calculator", "calc"]):
                return f"""{{\"action\": \"app_control\", \"parameters\": {{\"app_name\": \"calculator\", \"operation\": \"launch\", \"original_query\": \"{self.last_command}\"}}, \"response\": \"Opening Calculator for you, {form_of_address}.\"}}"""
            elif any(phrase in command_lower for phrase in ["open explorer", "launch explorer", "start explorer", "file explorer"]):
                return f"""{{\"action\": \"app_control\", \"parameters\": {{\"app_name\": \"explorer\", \"operation\": \"launch\", \"original_query\": \"{self.last_command}\"}}, \"response\": \"Opening File Explorer for you, {form_of_address}.\"}}"""
            elif any(phrase in command_lower for phrase in ["open terminal", "launch terminal", "start terminal", "command prompt", "cmd"]):
                return f"""{{\"action\": \"app_control\", \"parameters\": {{\"app_name\": \"terminal\", \"operation\": \"launch\", \"original_query\": \"{self.last_command}\"}}, \"response\": \"Opening Terminal for you, {form_of_address}.\"}}"""
            
            # Project commands
            elif any(phrase in command_lower for phrase in ["open project", "show project", "project", "open folder", "show folder"]):
                return f"""{{\"action\": \"provide_information\", \"parameters\": {{\"query\": \"list my projects\", \"original_query\": \"{self.last_command}\"}}, \"response\": \"I'll show you your available projects, {form_of_address}.\"}}"""
            elif any(phrase in command_lower for phrase in ["list my projects", "show my projects", "my projects", "project list", "show projects", "what projects"]):
                return f"""{{\"action\": \"provide_information\", \"parameters\": {{\"query\": \"list my projects\", \"original_query\": \"{self.last_command}\"}}, \"response\": \"Let me show you your projects, {form_of_address}.\"}}"""
            
            # Web search commands
            elif any(phrase in command_lower for phrase in ["search for", "google", "search google", "look up"]):
                search_query = command_lower.replace("search for", "").replace("google", "").replace("search", "").replace("look up", "").strip()
                if search_query:
                    return f"""{{\"action\": \"web_search\", \"parameters\": {{\"query\": \"{search_query}\", \"engine\": \"google\", \"original_query\": \"{self.last_command}\"}}, \"response\": \"Searching for {search_query} on Google, {form_of_address}.\"}}"""
                else:
                    return f"""{{\"action\": \"web_search\", \"parameters\": {{\"query\": \"general search\", \"engine\": \"google\", \"original_query\": \"{self.last_command}\"}}, \"response\": \"Opening Google search for you, {form_of_address}.\"}}"""
            
            # Stop/termination commands - handle gracefully with proper conversation ending
            elif any(phrase in command_lower for phrase in ["stop conversation", "end conversation", "stop talking", "end this", "that's enough", "finish conversation"]):
                return f"""{{\"action\": \"end_conversation\", \"parameters\": {{\"original_query\": \"{self.last_command}\"}}, \"response\": \"Conversation ended, {form_of_address}. I'll be here when you need me.\"}}"""
            elif command_lower.strip() == "stop" or command_lower.strip() == "exit" or command_lower.strip() == "quit":
                return f"""{{\"action\": \"end_conversation\", \"parameters\": {{\"original_query\": \"{self.last_command}\"}}, \"response\": \"Stopping, {form_of_address}. I'll be here when you need me.\"}}"""
            elif command_lower.startswith("stop ") or "stop the" in command_lower:
                return f"""{{\"action\": \"end_conversation\", \"parameters\": {{\"original_query\": \"{self.last_command}\"}}, \"response\": \"Stopping, {form_of_address}. I'll be here when you need me.\"}}"""
            elif any(phrase in command_lower for phrase in ["stop it", "cancel", "nevermind", "never mind"]):
                return f"""{{\"action\": \"stop_current_task\", \"parameters\": {{\"original_query\": \"{self.last_command}\"}}, \"response\": \"Stopped, {form_of_address}. What would you like to do instead?\"}}"""
            
            # Polite responses
            elif any(phrase in command_lower for phrase in ["no thank you", "no thanks", "that's all", "nothing else", "i'm good", "im good"]):
                return f"""{{\"action\": \"provide_information\", \"parameters\": {{\"original_query\": \"{self.last_command}\"}}, \"response\": \"Understood, {form_of_address}. I'm here whenever you need me. Have a great day!\"}}"""
            
            # Conversational responses
            elif "how" in command_lower and ("r u" in command_lower or "are you" in command_lower):
                return f"""{{\"action\": \"provide_information\", \"parameters\": {{\"original_query\": \"{self.last_command}\"}}, \"response\": \"I'm doing well, {form_of_address}. Thank you for asking! How can I help you today?\"}}"""
            elif "hello" in command_lower or "hi" in command_lower:
                return f"""{{\"action\": \"provide_information\", \"parameters\": {{\"original_query\": \"{self.last_command}\"}}, \"response\": \"Hello, {form_of_address}! It's good to hear from you. How can I assist you today?\"}}"""
            
            # Information queries
            elif any(word in command_lower for word in ["time", "clock", "hour"]):
                return f"""{{\"action\": \"provide_information\", \"parameters\": {{\"query\": \"time\", \"original_query\": \"{self.last_command}\"}}, \"response\": \"Let me get the current time for you.\"}}"""
            elif any(word in command_lower for word in ["weather", "temperature", "forecast"]):
                return f"""{{\"action\": \"provide_information\", \"parameters\": {{\"query\": \"weather\", \"original_query\": \"{self.last_command}\"}}, \"response\": \"Let me check the weather for you.\"}}"""
            elif any(word in command_lower for word in ["date", "day", "today"]):
                return f"""{{\"action\": \"provide_information\", \"parameters\": {{\"query\": \"date\", \"original_query\": \"{self.last_command}\"}}, \"response\": \"Let me get today's date for you.\"}}"""
            elif any(phrase in command_lower for phrase in ["who is your owner", "who created you", "who made you", "who is your creator", "who built you", "who developed you"]):
                return f"""{{\"action\": \"provide_information\", \"parameters\": {{\"query\": \"owner\", \"original_query\": \"{self.last_command}\"}}, \"response\": \"Let me tell you about my amazing creator!\"}}"""
            elif any(phrase in command_lower for phrase in ["what can you do", "what are you capable of", "what are your capabilities", "help", "what can you help me with", "what do you do", "tell me about yourself", "what are your features"]):
                return f"""{{\"action\": \"provide_information\", \"parameters\": {{\"query\": \"capabilities\", \"original_query\": \"{self.last_command}\"}}, \"response\": \"Let me show you all the amazing things I can help you with!\"}}"""
            
            # Default fallback
            else:
                return f"""{{\"action\": \"provide_information\", \"parameters\": {{\"original_query\": \"{self.last_command}\"}}, \"response\": \"I'm sorry, {form_of_address}. I couldn't process that request properly. Can I help you with something else?\"}}"""
        
        # Print the cleaned output for debugging
        print(f"Cleaned AI response: {cleaned_output[:100]}...")
        
        return cleaned_output
    
    def _parse_llm_response(self, response_text: str) -> Dict[str, Any]:
        """Parse the LLM response text
        
        Args:
            response_text: Raw response text from the LLM
            
        Returns:
            Dictionary containing the parsed response
        """
        try:
            # Get user's preferred address for fallback responses
            form_of_address = self.user_profile["personal"]["form_of_address"]
            
            # Try to find JSON in the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                
                # Fix common JSON issues
                json_str = self._fix_json_formatting(json_str)
                
                result = json.loads(json_str)
                
                # Ensure required fields exist
                if "action" not in result:
                    result["action"] = "provide_information"
                if "parameters" not in result:
                    result["parameters"] = {}
                if "response" not in result:
                    result["response"] = f"I'll take care of that, {form_of_address}."
                
                # Ensure original_query is in parameters
                if "original_query" not in result["parameters"]:
                    result["parameters"]["original_query"] = self.last_command
                    
                return result
            else:
                # No JSON found, try to extract action from text
                return self._extract_action_from_text(response_text)
                
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse JSON from response: {response_text}")
            logging.error(f"JSON error: {e}")
            return self._extract_action_from_text(response_text)
        except Exception as e:
            logging.error(f"Error parsing LLM response: {e}")
            return self._default_error_response()

    def _fix_json_formatting(self, json_str: str) -> str:
        """Fix common JSON formatting issues
        
        Args:
            json_str: Raw JSON string
            
        Returns:
            Fixed JSON string
        """
        # Remove trailing commas (common issue)
        import re
        
        # Remove trailing comma before closing brace or bracket
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        
        # Remove trailing comma at end of string
        json_str = json_str.rstrip().rstrip(',')
        
        return json_str
    
    def _extract_action_from_text(self, text: str) -> Dict[str, Any]:
        """Attempt to extract action from plain text response
        
        Args:
            text: Plain text response from the LLM
            
        Returns:
            Dictionary with best-guess action and parameters
        """
        # Default to providing information with conversational response
        return {
            "action": "provide_information",
            "parameters": {"original_query": self.last_command},
            "response": text.strip()
        }
    
    def _default_error_response(self) -> Dict[str, Any]:
        """Generate a default error response
        
        Returns:
            Dictionary with error response
        """
        form_of_address = self.user_profile["personal"]["form_of_address"]
        return {
            "action": "unknown",
            "parameters": {"original_query": self.last_command},
            "response": f"I'm sorry, {form_of_address}. I encountered an error processing your request."
        }
