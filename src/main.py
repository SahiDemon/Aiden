"""
Aiden - AI Desktop Agent
Main module for AI desktop assistant with voice commands and natural responses
"""
import os
import sys
import time
import logging
import threading
import traceback
from typing import Dict, Any, Optional
import random

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import utility modules
from src.utils.config_manager import ConfigManager
from src.utils.voice_system import VoiceSystem
from src.utils.speech_recognition_system import SpeechRecognitionSystem
from src.utils.hotkey_listener import HotkeyListener
from src.utils.llm_connector import LLMConnector
from src.utils.command_dispatcher import CommandDispatcher

class Aiden:
    """Main class for the Aiden AI desktop agent"""
    
    def __init__(self):
        """Initialize the Aiden agent"""
        # Set logging level to DEBUG for troubleshooting
        logging.getLogger().setLevel(logging.DEBUG)
        
        print("Initializing Aiden AI Desktop Agent...")
        
        # Create configuration manager
        self.config_manager = ConfigManager()
        print("Config manager initialized")
        
        # Create voice system
        self.voice_system = VoiceSystem(self.config_manager)
        print("Voice system initialized")
        
        # Create speech recognition system
        self.stt_system = SpeechRecognitionSystem(self.config_manager)
        print("Speech recognition system initialized")
        
        # Create LLM connector
        self.llm_connector = LLMConnector(self.config_manager)
        print("LLM connector initialized")
        
        # Create command dispatcher
        self.command_dispatcher = CommandDispatcher(self.config_manager, self.voice_system)
        print("Command dispatcher initialized")
        
        # Create hotkey listener with activation callback
        print("Setting up hotkey listener...")
        self.hotkey_listener = HotkeyListener(
            self.config_manager,
            self.on_hotkey_activated
        )
        
        # Flag to indicate if listening is active
        self.is_listening = False
        
        # Flag to control main loop
        self.running = True
        
        logging.info("Aiden initialized successfully")
        print("Aiden initialized successfully")
    
    def on_hotkey_activated(self):
        """Callback for when the hotkey is pressed"""
        print("\n--- HOTKEY ACTIVATED ---")
        
        if self.is_listening:
            logging.info("Already listening, ignoring hotkey")
            print("Already listening, ignoring hotkey")
            return
            
        try:
            self.is_listening = True
            print("Started listening")
            
            self._process_interaction_cycle()
                
        except Exception as e:
            logging.error(f"Error in hotkey callback: {e}")
            logging.error(traceback.format_exc())
            form_of_address = self.config_manager.get_user_profile()["personal"]["form_of_address"]
            self.voice_system.speak(f"I encountered an error, {form_of_address}.")
            
        finally:
            self.is_listening = False
            
    def _process_interaction_cycle(self):
        """Process a full interaction cycle with follow-up"""
        # Play activation sound instead of greeting
        print("Starting voice interaction...")
        # We only want the sound effect, not the greeting
        self.voice_system.play_ready_sound()
        
        # Continue conversation until user wants to stop
        continue_conversation = True
        
        while continue_conversation and self.is_listening:
            # Listen for command
            success, text, error = self.stt_system.listen()
            
            if success and text:
                logging.info(f"Processing command: {text}")
                
                # Process with LLM
                command = self.llm_connector.process_command(text)
                
                # Record the interaction
                self.config_manager.record_interaction(
                    command["action"],
                    text,
                    command["parameters"]
                )
                
                # Dispatch the command
                self.command_dispatcher.dispatch(command)
                
                # Ask if the user wants anything else
                continue_conversation = self._ask_for_follow_up()
                
            elif error:
                # Handle speech recognition error
                self.voice_system.speak(error)
                logging.warning(f"Speech recognition error: {error}")
                # Don't ask for follow-up on error
                continue_conversation = False
    
    def _ask_for_follow_up(self):
        """Ask if the user wants anything else and listen for response
        
        Returns:
            bool: True if the user wants to continue, False otherwise
        """
        # Wait a moment before asking follow-up
        time.sleep(1)
        
        # Ask follow-up question with more natural language
        follow_up_messages = [
            "Anything else I can help you with?",
            "Is there something else you need?",
            "What else can I do for you?",
            "Need help with anything else?",
            "Anything else on your mind?"
        ]
        
        follow_up_msg = random.choice(follow_up_messages)
        self.voice_system.speak(follow_up_msg)
        print("Listening for follow-up response...")
        
        # Listen for response
        success, response, error = self.stt_system.listen()
        
        if success and response:
            # Check if this is actually a new command instead of a yes/no response
            response = response.lower()
            print(f"Follow-up response: {response}")
            
            # If it's a question or command, treat it as a new command
            if any(q in response for q in ["what", "who", "when", "where", "why", "how", "can you", "could you", "please", "tell me", "show me", "open", "create", "find", "search"]):
                print("User asked a new question directly - processing as new command")
                
                # Process the new command directly
                command = self.llm_connector.process_command(response)
                
                # Record the interaction
                self.config_manager.record_interaction(
                    command["action"],
                    response,
                    command["parameters"]
                )
                
                # Dispatch the command
                self.command_dispatcher.dispatch(command)
                
                # Ask for another follow-up
                return self._ask_for_follow_up()
            
            # Positive responses
            elif any(word in response for word in ["yes", "yeah", "yep", "sure", "okay", "yup"]):
                print("User wants to continue conversation")
                continue_messages = [
                    "Great! What else can I help you with?",
                    "Sure thing! What do you need?",
                    "Awesome! What's next?",
                    "Perfect! How can I help?"
                ]
                continue_msg = random.choice(continue_messages)
                self.voice_system.speak(continue_msg)
                return True
                
            # Negative responses    
            elif any(word in response for word in ["no", "nope", "stop", "end", "finish", "that's all", "thats all", "thanks", "thank you"]):
                print("User wants to end conversation")
                goodbye_messages = [
                    "Alright! I'll be here if you need me.",
                    "Got it! Just call me when you need something.",
                    "Perfect! Have a great day!",
                    "Cool! I'm here whenever you need me.",
                    "Sounds good! Take care!"
                ]
                goodbye_msg = random.choice(goodbye_messages)
                self.voice_system.speak(goodbye_msg)
                return False
                
            # Unclear response, assume they want to continue
            else:
                print("Unclear response, treating as new command")
                
                # Process as a new command
                command = self.llm_connector.process_command(response)
                
                # Record the interaction
                self.config_manager.record_interaction(
                    command["action"],
                    response,
                    command["parameters"]
                )
                
                # Dispatch the command
                self.command_dispatcher.dispatch(command)
                
                # Ask for another follow-up
                return self._ask_for_follow_up()
        
        else:
            # No response or error, end conversation
            print("No response received, ending conversation")
            return False
    
    def start(self):
        """Start the Aiden agent"""
        try:
            # Update session information
            self.config_manager.update_session()
            print("Session information updated")
            
            print("\nStarting hotkey listener...")
            # Start hotkey listener
            success = self.hotkey_listener.start_listening()
            
            if not success:
                logging.error("Failed to start hotkey listener")
                print("ERROR: Failed to start hotkey listener")
                return False
                
            # Welcome message
            print(f"\n=== Aiden is now running ===")
            hotkey_config = self.config_manager.get_config("hotkey")
            key = hotkey_config["activation"]["key"]
            modifiers = hotkey_config["activation"]["modifiers"]
            hotkey_str = '+'.join([m.capitalize() for m in modifiers] + [key.capitalize()])
            print(f"Press {hotkey_str} key to activate.")
            print("Waiting for asterisk (*) key press...")
            
            # Speak startup notification
            form_of_address = self.config_manager.get_user_profile()["personal"]["form_of_address"]
            startup_message = f"Aiden is now ready. Press the asterisk key and ask me anything, {form_of_address}!"
            self.voice_system.speak(startup_message)
            
            # Keep the main thread alive
            while self.running:
                time.sleep(1)
                
            return True
            
        except KeyboardInterrupt:
            print("\nShutting down Aiden...")
            return self.stop()
            
        except Exception as e:
            logging.error(f"Error starting Aiden: {e}")
            logging.error(traceback.format_exc())
            return False
    
    def stop(self):
        """Stop the Aiden agent"""
        try:
            self.running = False
            
            # Stop hotkey listener
            self.hotkey_listener.stop_listening()
            
            # Goodbye message
            form_of_address = self.config_manager.get_user_profile()["personal"]["form_of_address"]
            self.voice_system.speak(f"Goodbye {form_of_address}.")
            
            logging.info("Aiden stopped")
            return True
            
        except Exception as e:
            logging.error(f"Error stopping Aiden: {e}")
            return False

def main():
    """Main entry point for the application"""
    try:
        # Create and start the agent
        agent = Aiden()
        
        # Start the agent
        if not agent.start():
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nExiting...")
        
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
