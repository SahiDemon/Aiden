"""
System Tray Application
Unified tray app that runs hidden in background
"""
import asyncio
import logging
import sys
import threading
import webbrowser
from typing import Optional
import pystray
from PIL import Image, ImageDraw

from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AidenTrayApp:
    """
    System tray application for Aiden
    Provides menu access to dashboard, settings, and exit
    """
    
    def __init__(self, on_exit_callback: Optional[callable] = None, wake_word_manager=None, event_loop=None):
        """
        Initialize tray app
        
        Args:
            on_exit_callback: Function to call when exiting
            wake_word_manager: Wake word manager for toggle functionality
            event_loop: Main asyncio event loop for running coroutines
        """
        self.settings = get_settings()
        self.on_exit_callback = on_exit_callback
        self.wake_word_manager = wake_word_manager
        self.event_loop = event_loop
        self.icon = None
        
        logger.info("Tray app initialized")
    
    def create_icon(self) -> Image.Image:
        """Create a simple icon for the tray"""
        # Create a simple icon (you can replace with actual icon file)
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), color=(52, 152, 219))  # Blue
        
        # Draw a simple "A" for Aiden
        draw = ImageDraw.Draw(image)
        draw.text((20, 15), "A", fill=(255, 255, 255))
        
        return image
    
    def open_dashboard(self, icon, item):
        """Open the dashboard in browser"""
        try:
            url = f"http://{self.settings.api.host}:{self.settings.api.port}"
            logger.info(f"Opening dashboard: {url}")
            webbrowser.open(url)
        except Exception as e:
            logger.error(f"Error opening dashboard: {e}")
    
    def open_settings(self, icon, item):
        """Open settings (future implementation)"""
        logger.info("Settings clicked (not implemented yet)")
    
    def toggle_wake_word(self, icon, item):
        """Toggle wake word listening on/off"""
        try:
            if not self.wake_word_manager:
                logger.error("Wake word manager not available")
                return
            
            if not self.event_loop:
                logger.error("Event loop not available")
                return
            
            # Run toggle in the main event loop
            import asyncio
            future = asyncio.run_coroutine_threadsafe(
                self.wake_word_manager.toggle(),
                self.event_loop
            )
            
            # Wait for completion
            try:
                new_state = future.result(timeout=10)
                logger.info(f"Wake word toggled: {'ENABLED' if new_state else 'DISABLED'}")
                
                # Update menu to reflect new state
                self.update_menu(icon)
            except TimeoutError:
                logger.error("Wake word toggle timed out")
            except Exception as e:
                logger.error(f"Error waiting for toggle result: {e}", exc_info=True)
                
        except Exception as e:
            logger.error(f"Error toggling wake word from tray: {e}", exc_info=True)
    
    def get_wake_word_state(self) -> bool:
        """Get current wake word state"""
        if self.wake_word_manager:
            return self.wake_word_manager.get_state()
        return True  # Default to enabled
    
    def update_menu(self, icon=None):
        """Update the tray menu"""
        if icon is None:
            icon = self.icon
        
        if icon is None:
            logger.warning("Cannot update menu: icon not initialized")
            return
        
        wake_word_enabled = self.get_wake_word_state()
        status_text = "Disable Wake Word" if wake_word_enabled else "Enable Wake Word"
        
        menu = pystray.Menu(
            pystray.MenuItem("Open Dashboard", self.open_dashboard),
            pystray.MenuItem(status_text, self.toggle_wake_word),
            pystray.MenuItem("Settings", self.open_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit Aiden", self.exit_app)
        )
        
        icon.menu = menu
        logger.debug(f"Menu updated: {status_text}")
    
    def exit_app(self, icon, item):
        """Exit the application"""
        logger.info("Exit requested from tray")
        
        # Stop the icon
        icon.stop()
        
        # Call exit callback
        if self.on_exit_callback:
            self.on_exit_callback()
    
    def run(self):
        """Run the tray app (blocks until exit)"""
        try:
            # Create initial menu
            wake_word_enabled = self.get_wake_word_state()
            status_text = "Disable Wake Word" if wake_word_enabled else "Enable Wake Word"
            
            menu = pystray.Menu(
                pystray.MenuItem("Open Dashboard", self.open_dashboard),
                pystray.MenuItem(status_text, self.toggle_wake_word),
                pystray.MenuItem("Settings", self.open_settings),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit Aiden", self.exit_app)
            )
            
            # Create icon
            self.icon = pystray.Icon(
                "aiden",
                self.create_icon(),
                "Aiden AI Assistant",
                menu
            )
            
            logger.info("Starting tray icon...")
            
            # Run (blocks)
            self.icon.run()
            
        except Exception as e:
            logger.error(f"Tray app error: {e}", exc_info=True)
            raise


def run_tray_app(on_exit_callback: Optional[callable] = None, wake_word_manager=None, event_loop=None):
    """
    Run the tray app
    This function blocks until the app exits
    
    Args:
        on_exit_callback: Function to call when exiting
        wake_word_manager: Wake word manager for toggle functionality
        event_loop: Main asyncio event loop for running coroutines
    """
    app = AidenTrayApp(on_exit_callback, wake_word_manager, event_loop)
    app.run()









