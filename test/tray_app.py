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
        self.hotkey_listener = None
        self.initialization_complete = False
        
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
            self.initialization_complete = True
            
        except Exception as e:
            print(f"Error initializing Aiden components: {e}")
            self.show_error("Failed to initialize Aiden components")
            self.initialization_complete = False
    
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
        text_x = width // 2 - 10
        text_y = height // 2 - 8
        
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
                
                print("Aiden dashboard started successfully")
                
                # Start the hotkey listener after dashboard is ready
                self.start_hotkey_listener()
                
            except Exception as e:
                print(f"Error starting dashboard: {e}")
                self.show_error(f"Failed to start dashboard: {str(e)}")
    
    def start_hotkey_listener(self):
        """Start the global hotkey listener"""
        if self.hotkey_listener is None and self.dashboard_backend:
            try:
                print("Starting hotkey listener...")
                self.hotkey_listener = HotkeyListener(
                    self.config_manager,
                    self._on_hotkey_activated
                )
                success = self.hotkey_listener.start_listening()
                if success:
                    print("Hotkey listener started successfully")
                    print("Press * key to activate Aiden!")
                else:
                    print("Failed to start hotkey listener")
            except Exception as e:
                print(f"Error starting hotkey listener: {e}")
    
    def _on_hotkey_activated(self):
        """Handle hotkey activation - this is for ONE-SHOT mode"""
        try:
            print("Hotkey activated - ONE-SHOT mode")
            
            if not self.initialization_complete:
                self.show_notification("Aiden Error", "Assistant not properly initialized")
                return
            
            # Start dashboard if not already running
            if self.dashboard_backend is None:
                self.start_dashboard()
                time.sleep(1)  # Give it time to start
            
            # Trigger ONE-SHOT hotkey activation through dashboard
            if self.dashboard_backend:
                self.dashboard_backend._on_hotkey_activated_oneshot()
                self.show_notification("Aiden Activated", "I'm listening! Give me one command...")
            else:
                self.show_notification("Aiden Error", "Dashboard not available")
                
        except Exception as e:
            print(f"Error in hotkey activation: {e}")
            self.show_notification("Aiden Error", f"Hotkey activation failed: {str(e)}")
    
    def activate_assistant(self, icon, item):
        """Activate the voice assistant from tray menu - continuous conversation"""
        try:
            print("Activating Aiden assistant from tray menu...")
            
            if not self.initialization_complete:
                self.show_notification("Aiden Error", "Assistant not properly initialized")
                return
            
            # Start dashboard if not already running
            if self.dashboard_backend is None:
                self.start_dashboard()
                time.sleep(1)  # Give it time to start
            
            # Trigger regular activation through dashboard (continuous conversation)
            if self.dashboard_backend:
                self.dashboard_backend._on_hotkey_activated()
                self.show_notification("Aiden Activated", "I'm listening! Start a conversation...")
            else:
                self.show_notification("Aiden Error", "Dashboard not available")
                
        except Exception as e:
            print(f"Error activating assistant: {e}")
            self.show_error(f"Failed to activate assistant: {str(e)}")
    
    def open_dashboard(self, icon, item):
        """Open the Aiden dashboard"""
        try:
            if self.dashboard_backend is None:
                self.start_dashboard()
                time.sleep(3)  # Give more time for dashboard to start
            
            # Open dashboard in browser
            import webbrowser
            webbrowser.open('http://localhost:5000')
            self.show_notification("Dashboard", "Opening Aiden dashboard in browser...")
            
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
                "• Voice activation with hotkeys (Press * key)\n"
                "• App control and file management\n"
                "• Web dashboard interface\n"
                "• Fan control (ESP32)\n"
                "• Conversation memory\n\n"
                "Press * key for one command or use tray menu for conversation!"
            )
            
            root.destroy()
            
        except Exception as e:
            print(f"Error showing about: {e}")
    
    def quit_app(self, icon, item):
        """Quit the application"""
        try:
            print("Shutting down Aiden...")
            
            # Stop hotkey listener
            if self.hotkey_listener:
                try:
                    self.hotkey_listener.stop_listening()
                except:
                    pass
            
            # Stop dashboard if running
            if self.dashboard_backend:
                try:
                    # Set flags to stop dashboard
                    self.dashboard_backend.running = False
                    self.dashboard_backend.is_listening = False
                    self.dashboard_backend.conversation_active = False
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
            time.sleep(0.5)  # Give time for cleanup
            os._exit(0)
    
    def show_notification(self, title, message):
        """Show a system notification"""
        try:
            print(f"NOTIFICATION: {title} - {message}")
            # Use Windows toast notification
            if sys.platform == "win32":
                try:
                    import win10toast
                    toaster = win10toast.ToastNotifier()
                    toaster.show_toast(title, message, duration=3, threaded=True)
                except ImportError:
                    print("win10toast not available")
        except Exception as e:
            print(f"Notification error: {e}")
    
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
            item('🎤 Start Conversation', self.activate_assistant, default=True),
            item('🌐 Open Dashboard', self.open_dashboard),
            pystray.Menu.SEPARATOR,
            item('ℹ️ About Aiden', self.show_about),
            pystray.Menu.SEPARATOR,
            item('❌ Quit', self.quit_app)
        )
    
    def speak_startup_message(self):
        """Speak the startup message"""
        try:
            if self.voice_system and self.initialization_complete:
                startup_message = "Aiden is active! Press star key for one command or use tray menu for conversation."
                print(f"Speaking: {startup_message}")
                self.voice_system.speak(startup_message)
        except Exception as e:
            print(f"Error speaking startup message: {e}")
    
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
            
            # Start dashboard early to enable hotkey functionality
            if self.initialization_complete:
                self.start_dashboard()
            
            # Show startup notification
            self.show_notification(
                "Aiden Started", 
                "AI Assistant is ready! Press * key for one command or right-click tray for conversation."
            )
            
            # Speak startup message in a separate thread so it doesn't block the tray
            if self.initialization_complete:
                startup_thread = threading.Thread(target=self.speak_startup_message)
                startup_thread.daemon = True
                startup_thread.start()
            
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