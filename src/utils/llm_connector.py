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
        
        # DIRECT FAN CONTROL BYPASS - Skip LLM for fan commands entirely
        command_lower = command_text.lower().strip()
        form_of_address = self.user_profile["personal"]["form_of_address"]
        
        # Check for fan control patterns directly
        fan_patterns = {
            # Turn off patterns
            ("turn off", "fan"): "off",
            ("fan", "off"): "off", 
            ("stop", "fan"): "off",
            ("fan", "stop"): "off",
            # Turn on patterns  
            ("turn on", "fan"): "on",
            ("fan", "on"): "on",
            ("start", "fan"): "on", 
            ("fan", "start"): "on",
            # Mode patterns
            ("fan", "mode"): "mode",
            ("change", "fan"): "mode"
        }
        
        for (word1, word2), operation in fan_patterns.items():
            if word1 in command_lower and word2 in command_lower:
                print(f"🎯 DIRECT FAN CONTROL: '{command_text}' -> operation '{operation}'")
                return {
                    "action": "fan_control",
                    "parameters": {
                        "operation": operation,
                        "original_query": command_text
                    },
                    "response": f"{'Turning off' if operation == 'off' else 'Turning on' if operation == 'on' else 'Changing mode of'} the fan for you, {form_of_address}."
                }
        
        # Get context for the prompt
        context = self._build_context()
        
        # Get user's preferred address
        form_of_address = self.user_profile["personal"]["form_of_address"]
        
        # Build the full prompt
        full_prompt = f"""
{context}

User command: "{command_text}"

⚠️ CRITICAL INSTRUCTION: If the user mentions ANY variation of fan control (turn on fan, turn off fan, fan on, fan off, start fan, stop fan, etc.), you MUST use fan_control action. This is for ESP32 smart home control.

IMPORTANT INSTRUCTIONS FOR RESPONSE:

1. FAN CONTROL (HIGHEST PRIORITY): For ANY fan operations, use fan_control action:
   - "turn off fan" → {{"action": "fan_control", "parameters": {{"operation": "off"}}}}
   - "turn on fan" → {{"action": "fan_control", "parameters": {{"operation": "on"}}}}
   - "fan off" → {{"action": "fan_control", "parameters": {{"operation": "off"}}}}
   - "fan on" → {{"action": "fan_control", "parameters": {{"operation": "on"}}}}
   - "start fan" → {{"action": "fan_control", "parameters": {{"operation": "on"}}}}
   - "stop fan" → {{"action": "fan_control", "parameters": {{"operation": "off"}}}}
   - "change fan speed" → {{"action": "fan_control", "parameters": {{"operation": "on"}}}}
   - "fan mode" → {{"action": "fan_control", "parameters": {{"operation": "mode"}}}}

2. SIMPLE APP COMMANDS: For commands like "open chrome", "launch notepad", "start spotify", ALWAYS respond with app_control action:
   - "open chrome" → {{"action": "app_control", "parameters": {{"app_name": "chrome", "operation": "launch"}}}}
   - "open notepad" → {{"action": "app_control", "parameters": {{"app_name": "notepad", "operation": "launch"}}}}
   - "launch spotify" → {{"action": "app_control", "parameters": {{"app_name": "spotify", "operation": "launch"}}}}

3. SYSTEM COMMANDS: For system operations, use system_command action:
   - "lock computer" → {{"action": "system_command", "parameters": {{"operation": "lock"}}}}
   - "restart computer" → {{"action": "system_command", "parameters": {{"operation": "restart"}}}}

4. COMPOUND COMMANDS: For multiple actions, create compound command structure:
   - "open chrome and open notepad" → {{"compound_command": true, "actions": [...]}}

REMEMBER: FAN CONTROL has highest priority!

Respond ONLY with valid JSON. Use provide_information ONLY when you truly cannot understand the request.

Examples of CORRECT responses:
- User: "open chrome" → {{"action": "app_control", "parameters": {{"app_name": "chrome", "operation": "launch", "original_query": "open chrome"}}, "response": "Opening Chrome for you, {self.user_profile['personal']['form_of_address']}."}}
- User: "lock my computer" → {{"action": "system_command", "parameters": {{"operation": "lock", "original_query": "lock my computer"}}, "response": "Locking the computer for you, {self.user_profile['personal']['form_of_address']}."}}
- User: "turn off the fan" → {{"action": "fan_control", "parameters": {{"operation": "off", "original_query": "turn off the fan"}}, "response": "Turning off the fan for you, {self.user_profile['personal']['form_of_address']}."}}
- User: "turn on fan" → {{"action": "fan_control", "parameters": {{"operation": "on", "original_query": "turn on fan"}}, "response": "Turning on the fan for you, {self.user_profile['personal']['form_of_address']}."}}
"""
        
        # Process with the appropriate LLM engine
        if self.engine == "tgpt":
            print(f"Connecting to AI with tgpt...")
            print(f"🔍 DEBUG: Command being processed: '{command_text}'")
            if "fan" in command_text.lower():
                print(f"🔍 DEBUG: FAN COMMAND DETECTED! Sending enhanced prompt...")
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
        """Process command using tgpt with smart mode selection
        
        Args:
            prompt: The prompt to send to tgpt
            
        Returns:
            Dictionary containing the parsed response
        """
        try:
            # Smart detection for shell mode vs built-in handlers
            command_lower = self.last_command.lower()
            
            # NEVER use shell mode for scheduling or timed commands
            scheduling_keywords = [
                "in ", " in ", "after ", "later", "schedule", "timer", "delay",
                "minute", "minutes", "hour", "hours", "second", "seconds",
                "tomorrow", "tonight", "morning", "afternoon", "evening"
            ]
            has_scheduling = any(keyword in command_lower for keyword in scheduling_keywords)
            
            # Only use shell mode for simple, immediate app launching commands that tgpt handles well
            simple_app_commands = [
                "open notepad", "launch notepad", "start notepad",
                "open calculator", "launch calculator", "start calculator", "calc",
                "open chrome", "launch chrome", "start chrome",
                "open firefox", "launch firefox", "start firefox", 
                "open edge", "launch edge", "start edge",
                "open explorer", "launch explorer", "file explorer", "start explorer"
            ]
            
            # Check for compound command indicators
            compound_indicators = [" and ", " then ", " also ", " plus ", ","]
            has_compound_indicator = any(indicator in command_lower for indicator in compound_indicators)
            
            # Check if this is a simple app command that tgpt handles well
            is_simple_app_command = any(cmd in command_lower for cmd in simple_app_commands)
            
            # Use shell mode ONLY for simple app commands WITHOUT scheduling AND WITHOUT compound indicators
            is_system_command = is_simple_app_command and not has_scheduling and not has_compound_indicator
            
            # Log the decision for debugging
            if has_scheduling:
                print(f"Detected scheduling keywords - using built-in handlers instead of shell mode")
            elif has_compound_indicator:
                print(f"Detected compound command - using regular LLM mode for multi-action processing")
            elif is_simple_app_command:
                print(f"Detected simple app command - using shell mode")
            else:
                print(f"Using regular LLM mode for complex command processing")
            
            # Create temporary file for the prompt
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as temp:
                temp_file_path = temp.name
                # Clean the prompt to remove problematic Unicode characters
                cleaned_prompt = prompt.encode('ascii', errors='replace').decode('ascii')
                temp.write(cleaned_prompt)
            
            # Build command based on OS and command type
            if is_system_command:
                print(f"Detected simple app command, using shell mode...")
                # Use shell mode (-s) for simple app commands with auto-yes (-y) only
                # Note: -q and -w don't work with shell mode, they give answers instead of commands
                if platform.system() == "Windows":
                    cmd = f'echo "{self.last_command}" | {self.tgpt_path} -s -y'
                else:  # Unix-like
                    cmd = f'echo "{self.last_command}" | {self.tgpt_path} -s -y'
            else:
                # Use regular mode with optimized flags:
                # -q: quiet mode (no loading animations)
                # -w: return whole response as text (faster)
                if platform.system() == "Windows":
                    cmd = f'type "{temp_file_path}" | {self.tgpt_path} -q -w'
                else:  # Unix-like
                    cmd = f'cat "{temp_file_path}" | {self.tgpt_path} -q -w'
            
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
            if not is_system_command:  # Only delete if we used the temp file
                os.unlink(temp_file_path)
            else:
                try:
                    os.unlink(temp_file_path)  # Try to clean up anyway
                except:
                    pass
            
            if process.returncode != 0:
                logging.error(f"tgpt error: {stderr}")
                print(f"ERROR connecting to AI: {stderr}")
                print("Please make sure tgpt is installed and configured correctly")
                return self._default_error_response()
            
            # Handle shell command responses differently
            if is_system_command:
                return self._handle_shell_command_response(stdout, self.last_command)
            else:
                # Clean the output from tgpt (remove loading spinners, etc.)
                clean_output = self._clean_tgpt_output(stdout)
                print(f"AI response cleaned and ready for processing")
                
                # Parse the response
                return self._parse_llm_response(clean_output)
            
        except Exception as e:
            logging.error(f"Error processing with tgpt: {e}")
            return self._default_error_response()
    
    def _clean_tgpt_output(self, output: str) -> str:
        """Clean the tgpt output (minimal cleaning needed with -q flag)
        
        Args:
            output: Raw output from tgpt
            
        Returns:
            Cleaned output string
        """
        # Get user's preferred address for fallback responses
        form_of_address = self.user_profile["personal"]["form_of_address"]
        
        # With -q flag, output should be clean, but still do basic cleaning
        cleaned_output = output.strip()
    
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
            
            # Schedule fallback patterns - detect incomplete schedule requests
            elif any(phrase in command_lower for phrase in ["can you schedule", "schedule a", "schedule the", "i want to schedule", "please schedule"]):
                return f"""{{\"action\": \"system_command\", \"parameters\": {{\"operation\": \"incomplete_schedule\", \"original_query\": \"{self.last_command}\"}}, \"response\": \"I'd be happy to schedule something for you, {form_of_address}. What would you like me to schedule and when?\"}}"""
            
            # Handle incomplete commands like "turn"
            elif command_lower.strip() in ["turn", "turn on", "turn off"]:
                return f"""{{\"action\": \"provide_information\", \"parameters\": {{\"original_query\": \"{self.last_command}\"}}, \"response\": \"Turn what, {form_of_address}? Please be more specific. For example, you can say 'turn off computer', 'turn on fan', or 'turn off the lights'.\"}}"""
            
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
            
            # CRITICAL FIX: Clean malformed JSON with ? prefix
            response_text = response_text.strip()
            
            # Remove leading ? or other non-JSON characters that tgpt sometimes adds
            if response_text.startswith('?'):
                response_text = response_text[1:].strip()
            elif response_text.startswith('```json'):
                response_text = response_text.replace('```json', '').replace('```', '').strip()
            elif response_text.startswith('```'):
                response_text = response_text.replace('```', '').strip()
            
            # Also remove any other common prefixes that break JSON
            prefixes_to_remove = ['Sure!', 'Certainly!', 'Here\'s', 'Here is']
            for prefix in prefixes_to_remove:
                if response_text.startswith(prefix):
                    # Find the first { and take everything from there
                    json_start = response_text.find('{')
                    if json_start > 0:
                        response_text = response_text[json_start:].strip()
                    break
            
            # CRITICAL FIX: Handle escaped quotes in JSON
            # Remove any text before the JSON starts
            json_start_idx = response_text.find('{')
            if json_start_idx > 0:
                response_text = response_text[json_start_idx:]
            
            # Fix escaped quotes - convert {\"action\": to {"action":
            if '\\\"' in response_text:
                print(f"🔧 FIXING ESCAPED QUOTES: Found escaped quotes, converting...")
                response_text = response_text.replace('\\\"', '"')
                print(f"🔧 AFTER UNESCAPE: {response_text[:100]}...")
            
            print(f"🔧 JSON CLEANING: Cleaned response: {response_text[:150]}...")
            
            # Check if response contains multiple JSON objects (compound command failure)
            lines = response_text.strip().split('\n')
            json_objects = []
            
            # Look for multiple JSON objects in the response
            json_blocks = []
            current_block = ""
            in_json = False
            
            for line in lines:
                if line.strip().startswith('{'):
                    if in_json and current_block.strip():
                        # Save previous block
                        json_blocks.append(current_block.strip())
                    current_block = line + '\n'
                    in_json = True
                elif in_json:
                    current_block += line + '\n'
                    if line.strip().endswith('}'):
                        # Check if this completes a JSON object
                        try:
                            json.loads(current_block.strip())
                            json_blocks.append(current_block.strip())
                            current_block = ""
                            in_json = False
                        except:
                            # Not a complete JSON object yet, continue
                            pass
            
            # Add final block if exists
            if in_json and current_block.strip():
                json_blocks.append(current_block.strip())
            
            # Parse each JSON block
            for block in json_blocks:
                try:
                    obj = json.loads(block)
                    if "action" in obj and obj["action"] != "provide_information":
                        json_objects.append(obj)
                except:
                    pass
            
            # If we found multiple JSON objects, convert to compound command
            if len(json_objects) > 1:
                print(f"🔍 MULTI-JSON: Found {len(json_objects)} JSON objects, creating compound command")
                return {
                    "compound_command": True,
                    "actions": json_objects,
                    "response": f"I'll take care of those tasks, {form_of_address}."
                }
            
            # Try to find JSON in the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                
                # Fix common JSON issues
                json_str = self._fix_json_formatting(json_str)
                
                print(f"🔧 PARSING JSON: {json_str[:100]}...")
                result = json.loads(json_str)
                
                # If we got a result, check if it should be compound
                if result:
                    # Check if this is already a compound command
                    if result.get("compound_command", False) and "actions" in result:
                        # Handle compound command
                        actions = result["actions"]
                        response = result.get("response", f"I'll take care of those tasks, {form_of_address}.")
                        
                        # Ensure each action has required fields
                        for action in actions:
                            if "action" not in action:
                                action["action"] = "provide_information"
                            if "parameters" not in action:
                                action["parameters"] = {}
                            if "original_query" not in action["parameters"]:
                                action["parameters"]["original_query"] = self.last_command
                        
                        print(f"🔍 LLM: Returning compound command with {len(actions)} actions")
                        return {
                            "compound_command": True,
                            "actions": actions,
                            "response": response
                        }
                    else:
                        # Check if this should be a compound command but LLM didn't format it correctly
                        original_query = result.get("parameters", {}).get("original_query", self.last_command)
                        if self._should_be_compound_command(original_query):
                            print(f"🔍 COMPOUND PATTERN DETECTED: LLM returned single action for compound query, converting")
                            return self._convert_to_compound_command(result, original_query)
                        
                        # Handle single command (existing logic)
                        if "action" not in result:
                            result["action"] = "provide_information"
                        if "parameters" not in result:
                            result["parameters"] = {}
                        if "response" not in result:
                            result["response"] = f"I'll take care of that, {form_of_address}."
                        
                        # Ensure original_query is in parameters
                        if "original_query" not in result["parameters"]:
                            result["parameters"]["original_query"] = self.last_command
                        
                        print(f"🔍 LLM: Returning single action: {result.get('action')}")
                        return result
            else:
                # No valid JSON found at all - check if this should be compound
                print(f"🔧 NO VALID JSON FOUND in response")
                if self._should_be_compound_command(self.last_command):
                    print(f"🔄 NO JSON BUT COMPOUND DETECTED: Creating fallback compound command")
                    return self._create_fallback_compound_command(self.last_command)
                
                # Fall through to regular text extraction
                print(f"🔧 FALLING BACK to text extraction")
                
        except json.JSONDecodeError as e:
            print(f"🚨 JSON DECODE ERROR: {e}")
            print(f"🚨 FAILED TEXT: {response_text[:200]}...")
            logging.error(f"Failed to parse JSON from response: {response_text}")
            logging.error(f"JSON error: {e}")
            
            # ENHANCED FALLBACK: Check if this should be a compound command even with JSON failure
            if self._should_be_compound_command(self.last_command):
                print(f"🔄 JSON FAILED BUT COMPOUND DETECTED: Creating fallback compound command")
                return self._create_fallback_compound_command(self.last_command)
            
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
        # Get user's preferred address for responses
        form_of_address = self.user_profile["personal"]["form_of_address"]
        
        # Fallback classification based on the original command
        command_lower = self.last_command.lower().strip()
        
        # System command patterns
        if any(phrase in command_lower for phrase in [
            "lock computer", "lock the computer", "lock my computer", "lock screen", "lock the screen",
            "shutdown", "shut down", "power off", "turn off computer", "turn off the computer",
            "restart", "reboot", "restart computer", "restart the computer", 
            "sleep", "hibernate", "put to sleep", "go to sleep"
        ]):
            operation = "lock"
            if any(word in command_lower for word in ["shutdown", "shut down", "power off", "turn off"]):
                operation = "shutdown"
            elif any(word in command_lower for word in ["restart", "reboot"]):
                operation = "restart"
            elif any(word in command_lower for word in ["sleep", "hibernate"]):
                operation = "sleep"
            
            return {
                "action": "system_command",
                "parameters": {
                    "operation": operation,
                    "original_query": self.last_command
                },
                "response": f"I'll {operation} the computer for you, {form_of_address}."
            }
        
        # App control patterns
        elif any(phrase in command_lower for phrase in [
            "open ", "launch ", "start ", "run ", "execute "
        ]):
            # Extract app name
            app_name = "application"
            if "chrome" in command_lower:
                app_name = "chrome"
            elif "spotify" in command_lower:
                app_name = "spotify"
            elif "notepad" in command_lower:
                app_name = "notepad"
            elif "calculator" in command_lower:
                app_name = "calculator"
            elif "firefox" in command_lower:
                app_name = "firefox"
            elif "edge" in command_lower:
                app_name = "edge"
            
            return {
                "action": "app_control",
                "parameters": {
                    "app_name": app_name,
                    "operation": "launch",
                    "original_query": self.last_command
                },
                "response": f"Let me find {app_name} for you, {form_of_address}."
            }
        
        # Fan control patterns
        elif any(phrase in command_lower for phrase in [
            "fan", "turn on fan", "turn off fan", "fan status", "check fan"
        ]):
            operation = "status"
            if "turn on" in command_lower or "start" in command_lower:
                operation = "on"
            elif "turn off" in command_lower or "stop" in command_lower:
                operation = "off"
            
            return {
                "action": "fan_control",
                "parameters": {
                    "operation": operation,
                    "original_query": self.last_command
                },
                "response": f"I'll handle the fan for you, {form_of_address}."
            }
        
        # Check if this should be a compound command
        if self._should_be_compound_command(self.last_command):
            # Try to create a compound command from text analysis
            return self._create_fallback_compound_command(self.last_command)
        
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

    def _handle_shell_command_response(self, tgpt_output: str, original_command: str) -> Dict[str, Any]:
        """Handle responses from tgpt shell mode for app launching
        
        Args:
            tgpt_output: Output from tgpt -s command
            original_command: Original user command
            
        Returns:
            Dictionary containing the app control action
        """
        # Get user's preferred address for responses
        form_of_address = self.user_profile["personal"]["form_of_address"]
        
        # Extract the shell command from tgpt output
        shell_command = tgpt_output.strip()
        
        # Create response based on command type
        command_lower = original_command.lower()
        
        if not shell_command or len(shell_command) < 3:
            return {
                "action": "provide_information",
                "parameters": {"original_query": original_command},
                "response": f"I couldn't generate a command for that, {form_of_address}. Could you be more specific?"
            }
        
        # Extract app name from the original command
        app_name = "application"
        if "notepad" in command_lower:
            app_name = "notepad"
        elif "calculator" in command_lower or "calc" in command_lower:
            app_name = "calculator"
        elif "chrome" in command_lower:
            app_name = "chrome"
        elif "firefox" in command_lower:
            app_name = "firefox"
        elif "edge" in command_lower:
            app_name = "edge"
        elif "explorer" in command_lower:
            app_name = "file explorer"
        
        response_msg = f"Opening {app_name} for you, {form_of_address}."
        
        # For simple commands like "notepad.exe", execute directly
        # For complex commands, let the system command handler decide
        if shell_command.endswith(".exe") and " " not in shell_command:
            # Simple executable - use system command with shell execution
            return {
                "action": "system_command",
                "parameters": {
                    "command": shell_command,
                    "original_query": original_command,
                    "command_type": "shell"
                },
                "response": response_msg
            }
        else:
            # Complex command - fall back to app_control handler which is more robust
            return {
                "action": "app_control",
                "parameters": {
                    "app_name": app_name,
                    "operation": "launch",
                    "original_query": original_command
                },
                "response": response_msg
            }
    
    def _should_be_compound_command(self, query: str) -> bool:
        """Check if a query should be treated as a compound command
        
        Args:
            query: User query to check
            
        Returns:
            True if this should be a compound command
        """
        query_lower = query.lower()
        compound_indicators = [
            " and ", " then ", " also ", " plus ", ",", " & ", " after "
        ]
        
        # Check if query contains compound indicators
        has_indicators = any(indicator in query_lower for indicator in compound_indicators)
        
        if not has_indicators:
            return False
        
        # Special check for repeated request patterns like "can you X and can you Y"
        repeated_patterns = [
            ("can you", "and can you"),
            ("could you", "and could you"),
            ("please", "and please"),
            ("open", "and open"),
            ("close", "and close"),
            ("start", "and start"),
            ("launch", "and launch"),
            ("turn", "and turn")
        ]
        
        for pattern_start, pattern_repeat in repeated_patterns:
            if pattern_start in query_lower and pattern_repeat in query_lower:
                print(f"🔍 COMPOUND PATTERN DETECTED: '{pattern_start}' + '{pattern_repeat}'")
                return True
        
        # Check if it contains multiple distinct commands
        # Look for multiple action verbs
        action_verbs = [
            "open", "launch", "start", "run", "execute", "close", "quit", "exit",
            "turn", "set", "adjust", "change", "lock", "unlock", "shutdown", 
            "restart", "sleep", "hibernate", "play", "pause", "stop", "search",
            "find", "create", "delete", "move", "copy"
        ]
        
        # Count action verbs in the query
        verb_count = sum(1 for verb in action_verbs if verb in query_lower)
        
        if verb_count >= 2:
            print(f"🔍 MULTIPLE VERBS DETECTED: {verb_count} action verbs found")
            return True
        
        return has_indicators
    
    def _convert_to_compound_command(self, single_result: Dict[str, Any], original_query: str) -> Dict[str, Any]:
        """Convert a single action result into a compound command
        
        Args:
            single_result: Single action result from LLM
            original_query: Original user query
            
        Returns:
            Compound command structure
        """
        form_of_address = self.user_profile["personal"]["form_of_address"]
        
        # Split the query into parts based on compound indicators
        query_lower = original_query.lower()
        actions = []
        
        # Try to parse compound commands
        if " and " in query_lower:
            parts = original_query.split(" and ")
        elif " then " in query_lower:
            parts = original_query.split(" then ")
        elif "," in query_lower:
            parts = [part.strip() for part in original_query.split(",")]
        else:
            # Fallback - just duplicate the single action
            parts = [original_query]
        
        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
                
            # Create action based on the part
            action = self._create_action_from_part(part, i == 0, single_result)
            if action:
                actions.append(action)
        
        # If we couldn't parse multiple actions, at least include the original
        if len(actions) <= 1 and single_result:
            actions = [single_result]
        
        return {
            "compound_command": True,
            "actions": actions,
            "response": f"I'll handle those tasks for you, {form_of_address}."
        }
    
    def _create_action_from_part(self, part: str, is_first: bool, reference_action: Dict[str, Any]) -> Dict[str, Any]:
        """Create an action from a part of a compound command
        
        Args:
            part: Part of the command to process
            is_first: True if this is the first part
            reference_action: Reference action from LLM to use as template
            
        Returns:
            Action dictionary
        """
        part_lower = part.lower().strip()
        
        # Clean up the part (remove leading "then", "and", etc.)
        for prefix in ["then ", "and ", "also ", "plus ", "after "]:
            if part_lower.startswith(prefix):
                part_lower = part_lower[len(prefix):].strip()
                part = part[len(prefix):].strip()
        
        # Determine action type based on content
        if any(word in part_lower for word in ["open", "launch", "start", "run"]):
            # App control action
            app_name = "application"
            if "chrome" in part_lower:
                app_name = "chrome"
            elif "spotify" in part_lower:
                app_name = "spotify"
            elif "notepad" in part_lower:
                app_name = "notepad"
            elif "calculator" in part_lower:
                app_name = "calculator"
            elif "firefox" in part_lower:
                app_name = "firefox"
            elif "edge" in part_lower:
                app_name = "edge"
            
            return {
                "action": "app_control",
                "parameters": {
                    "app_name": app_name,
                    "operation": "launch",
                    "original_query": part
                }
            }
        
        elif any(word in part_lower for word in ["lock", "sleep", "hibernate", "shutdown", "restart"]):
            # System command
            operation = "lock"
            if "sleep" in part_lower or "hibernate" in part_lower:
                operation = "sleep"
            elif "shutdown" in part_lower or "turn off" in part_lower:
                operation = "shutdown"
            elif "restart" in part_lower:
                operation = "restart"
            
            return {
                "action": "system_command",
                "parameters": {
                    "operation": operation,
                    "original_query": part
                }
            }
        
        elif any(word in part_lower for word in ["turn off", "turn on", "fan"]):
            # Fan control
            operation = "off" if "off" in part_lower else "on"
            
            return {
                "action": "fan_control",
                "parameters": {
                    "operation": operation,
                    "original_query": part
                }
            }
        
        else:
            # Use the reference action as fallback but update the query
            if reference_action:
                new_action = reference_action.copy()
                new_action["parameters"] = reference_action.get("parameters", {}).copy()
                new_action["parameters"]["original_query"] = part
                return new_action
            
            # Ultimate fallback
            return {
                "action": "provide_information",
                "parameters": {"original_query": part}
            }

    def _create_fallback_compound_command(self, query: str) -> Dict[str, Any]:
        """Create a compound command from text analysis when JSON parsing fails
        
        Args:
            query: Original user query
            
        Returns:
            Compound command structure
        """
        form_of_address = self.user_profile["personal"]["form_of_address"]
        
        # Split the query into parts based on compound indicators
        query_lower = query.lower()
        actions = []
        
        # Try to parse compound commands
        if " and " in query_lower:
            parts = query.split(" and ")
        elif " then " in query_lower:
            parts = query.split(" then ")
        elif "," in query_lower:
            parts = [part.strip() for part in query.split(",")]
        else:
            parts = [query]
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
                
            part_lower = part.lower()
            
            # Clean up the part (remove leading "then", "and", etc.)
            for prefix in ["then ", "and ", "also ", "plus ", "after "]:
                if part_lower.startswith(prefix):
                    part_lower = part_lower[len(prefix):].strip()
                    part = part[len(prefix):].strip()
            
            # Create action based on the part using the same logic as _extract_action_from_text
            action = None
            
            # System command patterns
            if any(phrase in part_lower for phrase in [
                "lock computer", "lock the computer", "lock my computer", "lock screen", "lock the screen",
                "shutdown", "shut down", "power off", "turn off computer", "turn off the computer",
                "restart", "reboot", "restart computer", "restart the computer", 
                "sleep", "hibernate", "put to sleep", "go to sleep"
            ]):
                operation = "lock"
                if any(word in part_lower for word in ["shutdown", "shut down", "power off", "turn off"]):
                    operation = "shutdown"
                elif any(word in part_lower for word in ["restart", "reboot"]):
                    operation = "restart"
                elif any(word in part_lower for word in ["sleep", "hibernate"]):
                    operation = "sleep"
                
                action = {
                    "action": "system_command",
                    "parameters": {
                        "operation": operation,
                        "original_query": part
                    }
                }
            
            # App control patterns
            elif any(phrase in part_lower for phrase in ["open ", "launch ", "start ", "run ", "execute "]):
                app_name = "application"
                if "chrome" in part_lower:
                    app_name = "chrome"
                elif "spotify" in part_lower:
                    app_name = "spotify"
                elif "notepad" in part_lower:
                    app_name = "notepad"
                elif "calculator" in part_lower:
                    app_name = "calculator"
                elif "firefox" in part_lower:
                    app_name = "firefox"
                elif "edge" in part_lower:
                    app_name = "edge"
                
                action = {
                    "action": "app_control",
                    "parameters": {
                        "app_name": app_name,
                        "operation": "launch",
                        "original_query": part
                    }
                }
            
            # Fan control patterns
            elif any(phrase in part_lower for phrase in ["fan", "turn on fan", "turn off fan"]):
                operation = "status"
                if "turn on" in part_lower or "start" in part_lower:
                    operation = "on"
                elif "turn off" in part_lower or "stop" in part_lower:
                    operation = "off"
                
                action = {
                    "action": "fan_control",
                    "parameters": {
                        "operation": operation,
                        "original_query": part
                    }
                }
            
            if action:
                actions.append(action)
        
        if not actions:
            # Fallback to single information request
            return {
                "action": "provide_information",
                "parameters": {"original_query": query},
                "response": f"I couldn't understand that compound command, {form_of_address}. Could you try rephrasing it?"
            }
        
        return {
            "compound_command": True,
            "actions": actions,
            "response": f"I'll handle those tasks for you, {form_of_address}."
        }
