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
    
    def __init__(self, on_exit_callback: Optional[callable] = None):
        """
        Initialize tray app
        
        Args:
            on_exit_callback: Function to call when exiting
        """
        self.settings = get_settings()
        self.on_exit_callback = on_exit_callback
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
            # Create menu
            menu = pystray.Menu(
                pystray.MenuItem("Open Dashboard", self.open_dashboard),
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


def run_tray_app(on_exit_callback: Optional[callable] = None):
    """
    Run the tray app
    This function blocks until the app exits
    """
    app = AidenTrayApp(on_exit_callback)
    app.run()





