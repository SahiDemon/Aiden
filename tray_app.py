#!/usr/bin/env python3
"""
Aiden System Tray Application
Provides a hidden system tray icon to control Aiden AI Assistant
"""
import sys
import os
import threading
import time
import logging
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item
import subprocess

# Add the project root to the path
sys.path.insert(0, os.path.abspath('.'))

# Import Aiden components
from src.utils.config_manager import ConfigManager
from src.utils.voice_system import VoiceSystem
from src.utils.llm_connector import LLMConnector
from src.utils.command_dispatcher import CommandDispatcher
from src.utils.stt_system import STTSystem
from src.utils.hotkey_listener import HotkeyListener
from src.dashboard_backend import AidenDashboardBackend

class AidenTrayApp:
    """System tray application for Aiden"""
    
    def __init__(self):
        """Initialize the tray application"""
        self.running = False
        self.aiden_active = False
        self.dashboard_backend = None
        self.dashboard_thread = None
        
        # Initialize Aiden components
        try:
            self.config_manager = ConfigManager()
            self.voice_system = VoiceSystem(self.config_manager)
            self.llm_connector = LLMConnector(self.config_manager)
            self.stt_system = STTSystem(self.config_manager)
            self.command_dispatcher = CommandDispatcher(
                self.config_manager, 
                self.voice_system
            )
            
            # Setup logging to be less verbose for tray app
            logging.getLogger().setLevel(logging.WARNING)
            
            print("Aiden components initialized successfully")
            
        except Exception as e:
            print(f"Error initializing Aiden components: {e}")
            self.show_error("Failed to initialize Aiden components")
    
    def create_icon_image(self):
        """Create a simple icon for the tray"""
        # Create a simple circular icon
        width = 64
        height = 64
        
        # Create image with transparent background
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # Draw a circle for the icon
        margin = 4
        draw.ellipse(
            [margin, margin, width-margin, height-margin], 
            fill=(0, 120, 255, 255),  # Blue circle
            outline=(255, 255, 255, 255),  # White outline
            width=2
        )
        
        # Add "AI" text in the center
        text = "AI"
        # Calculate text position to center it
        bbox = draw.textbbox((0, 0), text)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = (width - text_width) // 2
        text_y = (height - text_height) // 2 - 2
        
        draw.text((text_x, text_y), text, fill=(255, 255, 255, 255))
        
        return image
    
    def start_dashboard(self):
        """Start the Aiden dashboard in a separate thread"""
        if self.dashboard_backend is None:
            try:
                print("Starting Aiden dashboard...")
                self.dashboard_backend = AidenDashboardBackend()
                
                def run_dashboard():
                    try:
                        self.dashboard_backend.run(host='localhost', port=5000, debug=False)
                    except Exception as e:
                        print(f"Dashboard error: {e}")
                
                self.dashboard_thread = threading.Thread(target=run_dashboard)
                self.dashboard_thread.daemon = True
                self.dashboard_thread.start()
                
                # Give it time to start
                time.sleep(2)
                
                # Open dashboard in browser
                import webbrowser
                webbrowser.open('http://localhost:5000')
                
                print("Aiden dashboard started successfully")
                
            except Exception as e:
                print(f"Error starting dashboard: {e}")
                self.show_error(f"Failed to start dashboard: {str(e)}")
    
    def activate_assistant(self, icon, item):
        """Activate the voice assistant"""
        try:
            print("Activating Aiden assistant...")
            
            if not self.aiden_active:
                self.aiden_active = True
                
                # Start dashboard if not already running
                if self.dashboard_backend is None:
                    self.start_dashboard()
                
                # Trigger hotkey activation through dashboard
                if self.dashboard_backend:
                    self.dashboard_backend._on_hotkey_activated()
                
                self.show_notification("Aiden activated", "Voice assistant is now listening...")
                
            else:
                self.show_notification("Aiden", "Assistant is already active")
                
        except Exception as e:
            print(f"Error activating assistant: {e}")
            self.show_error(f"Failed to activate assistant: {str(e)}")
    
    def open_dashboard(self, icon, item):
        """Open the Aiden dashboard"""
        try:
            if self.dashboard_backend is None:
                self.start_dashboard()
            else:
                # Just open the browser to the dashboard
                import webbrowser
                webbrowser.open('http://localhost:5000')
            
        except Exception as e:
            print(f"Error opening dashboard: {e}")
            self.show_error(f"Failed to open dashboard: {str(e)}")
    
    def show_about(self, icon, item):
        """Show about dialog"""
        try:
            import tkinter as tk
            from tkinter import messagebox
            
            # Create a temporary root window (hidden)
            root = tk.Tk()
            root.withdraw()
            
            # Show about message
            messagebox.showinfo(
                "About Aiden",
                "Aiden AI Assistant v1.0\n\n"
                "Your intelligent voice-activated assistant\n"
                "Created by Sahindu Gayanuka\n\n"
                "Features:\n"
                "• Voice activation with hotkeys\n"
                "• App control and file management\n"
                "• Web dashboard interface\n"
                "• Fan control (ESP32)\n"
                "• Conversation memory\n\n"
                "Press * key or use this tray menu to activate!"
            )
            
            root.destroy()
            
        except Exception as e:
            print(f"Error showing about: {e}")
    
    def quit_app(self, icon, item):
        """Quit the application"""
        try:
            print("Shutting down Aiden...")
            
            # Stop dashboard if running
            if self.dashboard_backend:
                try:
                    # Gracefully shutdown flask
                    pass  # Flask will shutdown when the thread ends
                except:
                    pass
            
            self.running = False
            self.aiden_active = False
            
            # Stop the tray icon
            icon.stop()
            
        except Exception as e:
            print(f"Error during shutdown: {e}")
        finally:
            # Force exit if needed
            import os
            os._exit(0)
    
    def show_notification(self, title, message):
        """Show a system notification"""
        try:
            # Use Windows toast notification
            if sys.platform == "win32":
                import win10toast
                toaster = win10toast.ToastNotifier()
                toaster.show_toast(title, message, duration=3, threaded=True)
            else:
                print(f"{title}: {message}")
        except:
            print(f"{title}: {message}")
    
    def show_error(self, message):
        """Show an error message"""
        try:
            import tkinter as tk
            from tkinter import messagebox
            
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Aiden Error", message)
            root.destroy()
        except:
            print(f"ERROR: {message}")
    
    def create_menu(self):
        """Create the context menu for the tray icon"""
        return pystray.Menu(
            item('Activate Assistant', self.activate_assistant, default=True),
            item('Open Dashboard', self.open_dashboard),
            pystray.Menu.SEPARATOR,
            item('About Aiden', self.show_about),
            pystray.Menu.SEPARATOR,
            item('Quit', self.quit_app)
        )
    
    def run(self):
        """Run the tray application"""
        try:
            self.running = True
            
            # Create the tray icon
            icon_image = self.create_icon_image()
            menu = self.create_menu()
            
            # Create and run the tray icon
            icon = pystray.Icon(
                "aiden_assistant",
                icon_image,
                "Aiden AI Assistant",
                menu
            )
            
            print("Starting Aiden system tray application...")
            print("Right-click the tray icon to access options")
            
            # Show startup notification
            self.show_notification(
                "Aiden Started", 
                "AI Assistant is ready! Right-click tray icon for options."
            )
            
            # Run the icon (this blocks until quit)
            icon.run()
            
        except Exception as e:
            print(f"Error running tray app: {e}")
            self.show_error(f"Failed to start tray application: {str(e)}")

def main():
    """Main entry point"""
    print("=== Aiden AI Assistant ===")
    print("Starting system tray application...")
    
    try:
        app = AidenTrayApp()
        app.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 