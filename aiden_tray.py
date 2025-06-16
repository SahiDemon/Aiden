#!/usr/bin/env python3
"""
Aiden System Tray Application
"""
import sys
import os
import threading
import time
import logging
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item

# Hide console window on Windows
if sys.platform == "win32":
    try:
        import ctypes
        import ctypes.wintypes
        
        # Get console window handle
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        
        # Get console window
        console_window = kernel32.GetConsoleWindow()
        
        # Hide the console window (but don't close it, so dashboard still works)
        if console_window:
            user32.ShowWindow(console_window, 0)  # 0 = SW_HIDE
    except Exception as e:
        print(f"Could not hide console: {e}")

# Add the project root to the path
sys.path.insert(0, os.path.abspath('.'))

# Import Aiden components
from src.utils.config_manager import ConfigManager
from src.utils.voice_system import VoiceSystem
from src.utils.hotkey_listener import HotkeyListener
from src.dashboard_backend import AidenDashboardBackend

class AidenTrayApp:
    def __init__(self):
        self.running = False
        self.dashboard_backend = None
        self.dashboard_thread = None
        self.hotkey_listener = None
        self.initialization_complete = False
        
        try:
            print("Initializing Aiden components...")
            self.config_manager = ConfigManager()
            self.voice_system = VoiceSystem(self.config_manager)
            logging.getLogger().setLevel(logging.WARNING)
            print("Aiden components initialized successfully")
            self.initialization_complete = True
        except Exception as e:
            print(f"Error initializing: {e}")
            self.initialization_complete = False
    
    def create_icon_image(self):
        width = 64
        height = 64
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        margin = 4
        draw.ellipse(
            [margin, margin, width-margin, height-margin], 
            fill=(0, 120, 255, 255),
            outline=(255, 255, 255, 255),
            width=2
        )
        
        text_x = width // 2 - 10
        text_y = height // 2 - 8
        draw.text((text_x, text_y), "AI", fill=(255, 255, 255, 255))
        
        return image
    
    def start_dashboard(self):
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
                
                time.sleep(2)
                print("Dashboard started successfully")
                
                # Start the hotkey listener after dashboard is ready
                self.start_hotkey_listener()
                
            except Exception as e:
                print(f"Error starting dashboard: {e}")
    
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
            
            # Start dashboard if not already running (but don't open browser yet)
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
    
    def open_dashboard_for_verification(self):
        """Open dashboard in browser for verification (called when needed)"""
        try:
            import webbrowser
            webbrowser.open("http://localhost:5000")
            print("Opened dashboard for verification")
        except Exception as e:
            print(f"Could not open browser for verification: {e}")
    
    def activate_assistant(self, icon, item):
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
            print(f"Error activating: {e}")
            self.show_notification("Aiden Error", f"Activation failed: {str(e)}")
    
    def open_dashboard(self, icon, item):
        try:
            if self.dashboard_backend is None:
                self.start_dashboard()
                time.sleep(3)  # Give more time for dashboard to start
            
            import webbrowser
            webbrowser.open('http://localhost:5000')
            self.show_notification("Dashboard", "Opening Aiden dashboard in browser...")
            
        except Exception as e:
            print(f"Error opening dashboard: {e}")
            self.show_notification("Aiden Error", f"Failed to open dashboard: {str(e)}")
    
    def quit_app(self, icon, item):
        print("Shutting down Aiden...")
        self.show_notification("Aiden", "Shutting down AI Assistant")
        self.running = False
        
        # Stop hotkey listener
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop_listening()
            except:
                pass
        
        # Stop dashboard gracefully
        if self.dashboard_backend:
            try:
                # Set flags to stop dashboard
                self.dashboard_backend.running = False
                self.dashboard_backend.is_listening = False
                self.dashboard_backend.conversation_active = False
            except:
                pass
        
        icon.stop()
        time.sleep(0.5)  # Give time for cleanup
        os._exit(0)
    
    def show_notification(self, title, message):
        try:
            print(f"NOTIFICATION: {title} - {message}")
            if sys.platform == "win32":
                try:
                    import win10toast
                    toaster = win10toast.ToastNotifier()
                    toaster.show_toast(title, message, duration=3, threaded=True)
                except ImportError:
                    print("win10toast not available")
        except Exception as e:
            print(f"Notification error: {e}")
    
    def create_menu(self):
        return pystray.Menu(
            item('🎤 Activate Assistant', self.activate_assistant, default=True),
            item('🌐 Open Dashboard', self.open_dashboard),
            pystray.Menu.SEPARATOR,
            item('❌ Quit', self.quit_app)
        )
    
    def speak_startup_message(self):
        """Speak the startup message"""
        try:
            if self.voice_system and self.initialization_complete:
                startup_message = "Aiden is active! Press star key or use the tray menu to call me."
                print(f"Speaking: {startup_message}")
                self.voice_system.speak(startup_message)
        except Exception as e:
            print(f"Error speaking startup message: {e}")
    
    def run(self):
        try:
            self.running = True
            
            icon_image = self.create_icon_image()
            menu = self.create_menu()
            
            icon = pystray.Icon(
                "aiden_assistant",
                icon_image,
                "Aiden AI Assistant",
                menu
            )
            
            print("Starting Aiden system tray application...")
            
            # Start dashboard early to enable hotkey functionality
            self.start_dashboard()
            
            # Show startup notification
            self.show_notification("Aiden Started", "AI Assistant is ready! Press * key or use tray menu")
            
            # Speak startup message in a separate thread so it doesn't block the tray
            if self.initialization_complete:
                startup_thread = threading.Thread(target=self.speak_startup_message)
                startup_thread.daemon = True
                startup_thread.start()
            
            # Run the icon (this blocks until quit)
            icon.run()
            
        except Exception as e:
            print(f"Error running tray app: {e}")
            self.show_notification("Aiden Error", f"Failed to start: {str(e)}")

def main():
    print("=== Aiden AI Assistant Tray ===")
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