"""
Global Hotkey Listener
Migrated from utils/hotkey_listener.py with improvements
"""
import asyncio
import logging
import threading
from typing import Callable, Optional
from pynput import keyboard

from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

_SHIFTED_CHAR_ALIASES = {
    "/": {"/", "?"},
    "?": {"/", "?"},
    ".": {".", ">"},
    ">": {".", ">"},
    ",": {",", "<"},
    "<": {",", "<"},
    ";": {";", ":"},
    ":": {";", ":"},
    "'": {"'", '"'},
    '"': {"'", '"'},
    "[": {"[", "{"},
    "{": {"[", "{"},
    "]": {"]", "}"},
    "}": {"]", "}"},
    "\\": {"\\", "|"},
    "|": {"\\", "|"},
    "-": {"-", "_"},
    "_": {"-", "_"},
    "=": {"=", "+"},
    "+": {"=", "+"},
    "1": {"1", "!"},
    "!": {"1", "!"},
    "2": {"2", "@"},
    "@": {"2", "@"},
    "3": {"3", "#"},
    "#": {"3", "#"},
    "4": {"4", "$"},
    "$": {"4", "$"},
    "5": {"5", "%"},
    "%": {"5", "%"},
    "6": {"6", "^"},
    "^": {"6", "^"},
    "7": {"7", "&"},
    "&": {"7", "&"},
    "8": {"8", "*"},
    "*": {"8", "*"},
    "9": {"9", "("},
    "(": {"9", "("},
    "0": {"0", ")"},
    ")": {"0", ")"},
}


class HotkeyListener:
    """
    Global hotkey listener for voice activation
    """
    
    def __init__(self, on_activation: Optional[Callable] = None, hotkey_override: Optional[str] = None):
        """
        Initialize hotkey listener
        
        Args:
            on_activation: Callback when hotkey is pressed
        """
        self.settings = get_settings()
        self.on_activation = on_activation
        self.hotkey_override = hotkey_override
        
        # Parse hotkey combination
        self.hotkey_combo = self._parse_hotkey()
        
        # Listener
        self.listener = None
        self.is_running = False
        
        logger.info(f"Hotkey listener initialized: {self.hotkey_combo}")
    
    def _parse_hotkey(self) -> dict:
        """Parse hotkey string into key dict"""
        hotkey_str = self.hotkey_override or self.settings.app.hotkey
        result = {
            'modifiers': set(),
            'key': None,
            'accepted_chars': set(),
            'str': hotkey_str
        }
        
        # Parse key combination (e.g., "ctrl+shift+space")
        parts = hotkey_str.lower().split('+')
        
        for part in parts:
            part = part.strip()
            
            if part in ['ctrl', 'control']:
                result['modifiers'].add('ctrl')
            elif part == 'shift':
                result['modifiers'].add('shift')
            elif part == 'alt':
                result['modifiers'].add('alt')
            elif part == 'space':
                result['key'] = keyboard.Key.space
            elif part == 'enter' or part == 'return':
                result['key'] = keyboard.Key.enter
            elif part == 'tab':
                result['key'] = keyboard.Key.tab
            elif part == 'esc' or part == 'escape':
                result['key'] = keyboard.Key.esc
            elif len(part) == 1:
                # Single character key (including * asterisk)
                try:
                    result['key'] = keyboard.KeyCode.from_char(part)
                    result['accepted_chars'] = _SHIFTED_CHAR_ALIASES.get(part, {part})
                except Exception as e:
                    logger.warning(f"Failed to parse hotkey character '{part}': {e}")
            else:
                logger.warning(f"Unknown hotkey part: '{part}'")
        
        # Validate we have at least a key
        if result['key'] is None:
            logger.error(f"Invalid hotkey configuration: '{hotkey_str}' - no valid key found, using default space")
            result['key'] = keyboard.Key.space
        
        return result

    def _key_matches(self, pressed_key, required_key, accepted_chars: set[str]) -> bool:
        """Match keys more robustly for shifted punctuation on Windows layouts."""
        if pressed_key == required_key:
            return True

        if isinstance(pressed_key, keyboard.KeyCode):
            pressed_char = pressed_key.char
            if pressed_char and pressed_char in accepted_chars:
                return True

        return False
    
    def start(self):
        """Start listening for hotkey"""
        if self.is_running:
            logger.warning("Hotkey listener already running")
            return
        
        logger.info("Starting hotkey listener...")
        self.is_running = True
        
        # Track pressed modifiers
        self.pressed_modifiers = set()
        
        def on_press(key):
            """Key press handler"""
            if not self.is_running:
                return
            
            # Track modifier keys
            if key in [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.ctrl]:
                self.pressed_modifiers.add('ctrl')
            elif key in [keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r]:
                self.pressed_modifiers.add('shift')
            elif key in [keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt]:
                self.pressed_modifiers.add('alt')
            
            # Check if hotkey combo is pressed
            required_mods = self.hotkey_combo['modifiers']
            required_key = self.hotkey_combo['key']
            accepted_chars = self.hotkey_combo.get('accepted_chars', set())
            
            # Check both modifiers and key
            if required_mods == self.pressed_modifiers and self._key_matches(key, required_key, accepted_chars):
                logger.info("Hotkey activated!")
                self._trigger_activation()
        
        def on_release(key):
            """Key release handler"""
            # Track modifier releases
            if key in [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.ctrl]:
                self.pressed_modifiers.discard('ctrl')
            elif key in [keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r]:
                self.pressed_modifiers.discard('shift')
            elif key in [keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt]:
                self.pressed_modifiers.discard('alt')
        
        # Start listener in background thread
        self.listener = keyboard.Listener(
            on_press=on_press,
            on_release=on_release
        )
        self.listener.start()
        
        logger.info("Hotkey listener started")
    
    def stop(self):
        """Stop listening"""
        logger.info("Stopping hotkey listener...")
        self.is_running = False
        
        if self.listener:
            self.listener.stop()
        
        logger.info("Hotkey listener stopped")
    
    def _trigger_activation(self):
        """Trigger activation callback"""
        if self.on_activation:
            # Run callback in thread to avoid blocking
            threading.Thread(target=self.on_activation, daemon=True).start()


# Global instance
_hotkey_listener: Optional[HotkeyListener] = None


def get_hotkey_listener(
    on_activation: Optional[Callable] = None,
    hotkey_override: Optional[str] = None
) -> HotkeyListener:
    """Get or create global hotkey listener"""
    global _hotkey_listener
    if _hotkey_listener is None:
        _hotkey_listener = HotkeyListener(on_activation, hotkey_override=hotkey_override)
    return _hotkey_listener
