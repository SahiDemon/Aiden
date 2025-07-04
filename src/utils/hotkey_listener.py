"""
Hotkey Listener for Aiden
Handles global hotkey detection for activating the AI assistant
"""
import logging
import threading
import time
import sys
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
        
        # Windows-specific error handling
        self.last_activation_time = 0
        self.activation_cooldown = 0.5  # Prevent rapid re-activation
        
        logging.info(f"Hotkey listener initialized with key: {self.key}, modifiers: {self.modifiers}")
    
    def on_press(self, key):
        """Handle key press events with improved error handling
        
        Args:
            key: The key that was pressed
        """
        try:
            # Add key to currently pressed keys
            self.current_keys.add(key)
            
            # Check for asterisk key in multiple formats with error handling
            asterisk_pressed = False
            
            try:
                if hasattr(key, 'char') and key.char == '*':
                    asterisk_pressed = True
                    logging.info("Asterisk (*) key pressed")
                    
                    # Check cooldown to prevent rapid re-activation
                    current_time = time.time()
                    if current_time - self.last_activation_time < self.activation_cooldown:
                        logging.debug("Activation cooldown active, ignoring")
                        return True  # Explicitly return True for Windows API
                    
                    self.last_activation_time = current_time
                    
                    # Call the activation callback in a separate thread to avoid blocking
                    # Use daemon thread to prevent hanging on exit
                    activation_thread = threading.Thread(target=self._safe_activation_callback)
                    activation_thread.daemon = True
                    activation_thread.start()
                    return True  # Explicitly return True for Windows API
            except Exception as e:
                logging.debug(f"Error checking asterisk key: {e}")
                # Continue with other key checks
            
            # If we have modifiers configured, check for the full hotkey combination
            if self.modifiers:
                try:
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
                    
                    # Full hotkey combination
                    if main_key_pressed and all_modifiers_pressed:
                        # Check cooldown
                        current_time = time.time()
                        if current_time - self.last_activation_time < self.activation_cooldown:
                            logging.debug("Activation cooldown active, ignoring")
                            return True  # Explicitly return True for Windows API
                        
                        self.last_activation_time = current_time
                        
                        hotkey_str = '+'.join([m.capitalize() for m in self.modifiers] + [self.key.capitalize()])
                        logging.info(f"Hotkey detected: {hotkey_str}")
                        print(f"\n**** HOTKEY DETECTED: {hotkey_str} ****\n")
                        
                        # Clear current keys to prevent repeated triggers
                        self.current_keys.clear()
                        
                        # Call the activation callback in a separate thread to avoid blocking
                        activation_thread = threading.Thread(target=self._safe_activation_callback)
                        activation_thread.daemon = True
                        activation_thread.start()
                        return True  # Explicitly return True for Windows API
                except Exception as e:
                    logging.debug(f"Error in hotkey combination check: {e}")
                    
        except Exception as e:
            # Catch all exceptions to prevent Windows WNDPROC errors
            logging.debug(f"Error in on_press (suppressed for stability): {e}")
            # Don't print to console to avoid spam
        
        # Always return True to satisfy Windows API requirements
        return True
    
    def on_release(self, key):
        """Handle key release events with improved error handling
        
        Args:
            key: The key that was released
        """
        try:
            # Remove key from currently pressed keys if it's there
            self.current_keys.discard(key)
        except Exception as e:
            # Suppress errors to prevent Windows WNDPROC issues
            logging.debug(f"Error in on_release (suppressed for stability): {e}")
        
        # Always return True to satisfy Windows API requirements
        return True
    
    def _safe_activation_callback(self):
        """Safely call the activation callback with error handling"""
        try:
            self.activation_callback()
        except Exception as e:
            logging.error(f"Error in activation callback: {e}")
            print(f"Error in activation callback: {e}")
    
    def start_listening(self):
        """Start listening for hotkey presses with improved error handling"""
        if not PYNPUT_AVAILABLE:
            logging.error("Cannot start hotkey listener - pynput not available")
            print("ERROR: pynput library not available. Hotkey detection will not work.")
            return False
            
        if self.is_listening:
            logging.warning("Hotkey listener already running")
            return True
            
        try:
            # Create keyboard listener with Windows-specific error handling
            def safe_on_press(key):
                try:
                    result = self.on_press(key)
                    # Ensure we always return a proper value for Windows API
                    return True if result is None else result
                except Exception as e:
                    logging.debug(f"Error in safe_on_press: {e}")
                    return True  # Always return True to satisfy Windows API
            
            def safe_on_release(key):
                try:
                    result = self.on_release(key)
                    # Ensure we always return a proper value for Windows API
                    return True if result is None else result
                except Exception as e:
                    logging.debug(f"Error in safe_on_release: {e}")
                    return True  # Always return True to satisfy Windows API
            
            # Create and start keyboard listener with Windows-optimized settings
            self.listener = keyboard.Listener(
                on_press=safe_on_press,
                on_release=safe_on_release,
                suppress=False  # Don't suppress keys to avoid Windows issues
            )
            
            # Start in daemon mode to prevent hanging
            self.listener.daemon = True
            self.listener.start()
            self.is_listening = True
            
            # Print confirmation to console
            hotkey_str = '+'.join([m.capitalize() for m in self.modifiers] + [self.key.capitalize()])
            logging.info(f"Hotkey listener started - Listening for: {hotkey_str}")
            print(f"Hotkey listener started - Listening for: {hotkey_str}")
            
            # Give listener time to initialize
            time.sleep(0.1)
            
            # Verify listener is running
            if not self.listener.running:
                logging.error("Listener thread failed to start!")
                print("ERROR: Hotkey listener thread failed to start!")
                return False
                
            return True
        except Exception as e:
            logging.error(f"Error starting hotkey listener: {e}")
            print(f"Error starting hotkey listener: {e}")
            return False
    
    def stop_listening(self):
        """Stop listening for hotkey presses"""
        if not self.is_listening or not self.listener:
            return
            
        try:
            if self.listener.running:
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
