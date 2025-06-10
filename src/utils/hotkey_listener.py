"""
Hotkey Listener for Aiden
Handles global hotkey detection for activating the AI assistant
"""
import logging
import threading
from typing import Callable, List, Dict, Any, Optional

# Try to import optional dependencies
try:
    from pynput import keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    logging.error("pynput package not available. Hotkey detection will not work.")

class HotkeyListener:
    """Handles global hotkey detection"""
    
    def __init__(self, config_manager, activation_callback: Callable[[], None]):
        """Initialize the hotkey listener
        
        Args:
            config_manager: Configuration manager instance
            activation_callback: Function to call when hotkey is detected
        """
        self.config_manager = config_manager
        self.activation_callback = activation_callback
        self.hotkey_config = config_manager.get_config("hotkey")
        
        if not PYNPUT_AVAILABLE:
            logging.error("Hotkey detection dependencies not installed")
            return
            
        # Get hotkey configuration
        self.key = self.hotkey_config["activation"]["key"]
        self.modifiers = self.hotkey_config["activation"]["modifiers"]
        
        # Convert modifiers to pynput keyboard Keys
        self.modifier_keys = []
        for mod in self.modifiers:
            if mod.lower() == "ctrl":
                self.modifier_keys.append(keyboard.Key.ctrl)
            elif mod.lower() == "alt":
                self.modifier_keys.append(keyboard.Key.alt)
            elif mod.lower() == "shift":
                self.modifier_keys.append(keyboard.Key.shift)
            elif mod.lower() == "cmd" or mod.lower() == "win":
                self.modifier_keys.append(keyboard.Key.cmd)
                
        # Convert main key to pynput format
        if self.key.lower() == "space":
            self.main_key = keyboard.Key.space
        elif len(self.key) == 1:  # Single character key
            # For letters, we need to check for both KeyCode and Key
            # because some keyboard layouts might report them differently
            self.main_key = keyboard.KeyCode.from_char(self.key.lower())
            
            # Store the letter for special comparison
            self.key_char = self.key.lower()
            logging.info(f"Using character key: {self.key_char}")
            print(f"Using character key: {self.key_char}")
        else:
            # Try to convert to special key
            try:
                self.main_key = getattr(keyboard.Key, self.key.lower())
            except AttributeError:
                self.main_key = keyboard.KeyCode.from_char(self.key.lower()[0])
                self.key_char = self.key.lower()[0]
                logging.warning(f"Unknown key '{self.key}', using first character")
        
        # Track currently pressed keys
        self.current_keys = set()
        
        # Create the listener
        self.listener = None
        self.is_listening = False
        
        logging.info(f"Hotkey listener initialized with key: {self.key}, modifiers: {self.modifiers}")
    
    def on_press(self, key):
        """Handle key press events
        
        Args:
            key: The key that was pressed
        """
        try:
            # Log key press for debugging (only in log file)
            logging.debug(f"Key pressed: {key}")
            
            # Add key to currently pressed keys
            self.current_keys.add(key)
            
            # For simple asterisk key detection
            asterisk_pressed = False
            
            # Check for asterisk key in two different formats
            if hasattr(key, 'char') and key.char == '*':
                asterisk_pressed = True
                logging.info("Asterisk (*) key pressed")
                
                # Call the activation callback in a separate thread to avoid blocking
                threading.Thread(target=self.activation_callback).start()
                return
            
            # If we have modifiers configured, check for the full hotkey combination
            if self.modifiers:
                # Check if all modifier keys are pressed
                all_modifiers_pressed = True
                for mod in self.modifier_keys:
                    # Handle left/right variants of modifier keys
                    if mod == keyboard.Key.ctrl:
                        if not (keyboard.Key.ctrl_l in self.current_keys or keyboard.Key.ctrl_r in self.current_keys):
                            all_modifiers_pressed = False
                    elif mod == keyboard.Key.shift:
                        if not (keyboard.Key.shift in self.current_keys or 
                               keyboard.Key.shift_l in self.current_keys or 
                               keyboard.Key.shift_r in self.current_keys):
                            all_modifiers_pressed = False
                    elif mod == keyboard.Key.alt:
                        if not (keyboard.Key.alt in self.current_keys or 
                               keyboard.Key.alt_l in self.current_keys or 
                               keyboard.Key.alt_r in self.current_keys):
                            all_modifiers_pressed = False
                    elif mod not in self.current_keys:
                        all_modifiers_pressed = False
                
                # Check if main key is pressed
                main_key_pressed = False
                for k in self.current_keys:
                    if hasattr(k, 'char') and hasattr(self, 'key_char') and k.char == self.key_char:
                        main_key_pressed = True
                    elif k == self.main_key:
                        main_key_pressed = True
                
                # Debug output (only in log file)
                logging.debug(f"Main key pressed: {main_key_pressed}")
                logging.debug(f"All modifiers pressed: {all_modifiers_pressed}")
                
                # Full hotkey combination
                if main_key_pressed and all_modifiers_pressed:
                    hotkey_str = '+'.join([m.capitalize() for m in self.modifiers] + [self.key.capitalize()])
                    logging.info(f"Hotkey detected: {hotkey_str}")
                    print(f"\n**** HOTKEY DETECTED: {hotkey_str} ****\n")
                    
                    # Clear current keys to prevent repeated triggers
                    self.current_keys.clear()
                    
                    # Call the activation callback in a separate thread to avoid blocking
                    threading.Thread(target=self.activation_callback).start()
        except Exception as e:
            logging.error(f"Error in on_press: {e}")
            print(f"Error in key press handler: {e}")
    
    def on_release(self, key):
        """Handle key release events
        
        Args:
            key: The key that was released
        """
        try:
            # Log key release for debugging
            logging.debug(f"Key released: {key}")
            
            # Remove key from currently pressed keys if it's there
            self.current_keys.discard(key)
        except Exception as e:
            logging.error(f"Error in on_release: {e}")
    
    def start_listening(self):
        """Start listening for hotkey presses"""
        if not PYNPUT_AVAILABLE:
            logging.error("Cannot start hotkey listener - pynput not available")
            print("ERROR: pynput library not available. Hotkey detection will not work.")
            return False
            
        if self.is_listening:
            logging.warning("Hotkey listener already running")
            return True
            
        try:
            # Create and start keyboard listener
            self.listener = keyboard.Listener(
                on_press=self.on_press,
                on_release=self.on_release
            )
            self.listener.start()
            self.is_listening = True
            
            # Print confirmation to console
            hotkey_str = '+'.join([m.capitalize() for m in self.modifiers] + [self.key.capitalize()])
            logging.info(f"Hotkey listener started - Listening for: {hotkey_str}")
            print(f"Hotkey listener started - Listening for: {hotkey_str}")
            
            # Verify listener is running
            if not self.listener.is_alive():
                logging.error("Listener thread is not alive!")
                print("ERROR: Hotkey listener thread is not running!")
                return False
                
            return True
        except Exception as e:
            logging.error(f"Error starting hotkey listener: {e}")
            return False
    
    def stop_listening(self):
        """Stop listening for hotkey presses"""
        if not self.is_listening or not self.listener:
            return
            
        try:
            self.listener.stop()
            self.is_listening = False
            logging.info("Hotkey listener stopped")
        except Exception as e:
            logging.error(f"Error stopping hotkey listener: {e}")
    
    def change_hotkey(self, key: str, modifiers: List[str]) -> bool:
        """Change the current hotkey
        
        Args:
            key: New main key
            modifiers: List of modifier keys
            
        Returns:
            True if hotkey was changed successfully, False otherwise
        """
        # Stop current listener
        was_listening = self.is_listening
        if was_listening:
            self.stop_listening()
        
        try:
            # Update configuration
            self.key = key
            self.modifiers = modifiers
            
            # Update hotkey config
            updated_hotkey_config = self.hotkey_config.copy()
            updated_hotkey_config["activation"] = {
                "key": key,
                "modifiers": modifiers
            }
            
            # Re-initialize the listener
            self.__init__(self.config_manager, self.activation_callback)
            
            # Restart if it was running
            if was_listening:
                self.start_listening()
                
            logging.info(f"Hotkey changed to: {'+'.join(modifiers + [key])}")
            return True
        except Exception as e:
            logging.error(f"Error changing hotkey: {e}")
            return False
