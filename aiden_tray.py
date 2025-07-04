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
from src.utils.vosk_wake_word import VoskWakeWordDetector
from src.dashboard_backend import AidenDashboardBackend

class AidenTrayApp:
    def __init__(self):
        """Initialize the Aiden tray application"""
        print("Initializing Aiden components...")
        
        # Initialize core components first
        self.config_manager = ConfigManager()
        self.voice_system = VoiceSystem(self.config_manager)
        
        # Dashboard and hotkey components (will be initialized when needed)
        self.dashboard_backend = None
        self.hotkey_listener = None
        self.wake_word_detector = None
        self.dashboard_thread = None
        
        # State flags
        self.running = False
        self.wake_word_enabled = False
        self.initialization_complete = True  # Mark as complete immediately for faster startup
        
        # Auto-start timer for wake word detection
        self.auto_start_timer = None
        self.auto_start_delay = 15  # seconds
        
        print("Aiden components initialized successfully")
    
    def create_icon_image(self):
        """Create a system tray icon"""
        # Create a simple blue circle icon
        size = (64, 64)
        image = Image.new('RGBA', size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # Draw a blue circle
        margin = 8
        draw.ellipse([margin, margin, size[0]-margin, size[1]-margin], 
                    fill=(70, 130, 180, 255), outline=(25, 25, 112, 255), width=3)
        
        # Draw "A" in the center
        draw.text((size[0]//2-8, size[1]//2-12), "A", fill=(255, 255, 255, 255))
        
        return image
    
    def start_dashboard(self):
        """Start the Aiden dashboard - optimized for faster startup"""
        if self.dashboard_backend is None:
            try:
                print("Starting Aiden dashboard...")
                self.dashboard_backend = AidenDashboardBackend()
                
                # Pass wake word detector reference to dashboard for pause/resume control
                if hasattr(self, 'wake_word_detector'):
                    self.dashboard_backend.wake_word_detector = self.wake_word_detector
                    
                    # Also pass to dashboard's voice system 
                    if hasattr(self.dashboard_backend, 'voice_system'):
                        self.dashboard_backend.voice_system.wake_word_detector = self.wake_word_detector
                    
                    # Also pass to command dispatcher's voice system
                    if hasattr(self.dashboard_backend, 'command_dispatcher') and hasattr(self.dashboard_backend.command_dispatcher, 'voice_system'):
                        self.dashboard_backend.command_dispatcher.voice_system.wake_word_detector = self.wake_word_detector
                
                def run_dashboard():
                    try:
                        self.dashboard_backend.run(host='localhost', port=5000, debug=False)
                    except Exception as e:
                        print(f"Dashboard error: {e}")
                
                self.dashboard_thread = threading.Thread(target=run_dashboard)
                self.dashboard_thread.daemon = True
                self.dashboard_thread.start()
                
                # Reduced wait time for faster startup
                time.sleep(1)
                print("Dashboard started successfully")
                
                # Start the hotkey listener immediately after dashboard
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
    
    def start_wake_word_detection(self):
        """Start the Vosk wake word detection system"""
        print("🎯 Starting wake word detection...")
        
        # If detector exists but is not enabled, try to restart it
        if self.wake_word_detector is not None:
            if self.wake_word_enabled:
                print("Wake word detection already running and enabled")
                return True
            else:
                print("Detector exists but not enabled, clearing and recreating...")
                self.wake_word_detector = None
        
        try:
            print("Initializing new Vosk wake word detector...")
            self.wake_word_detector = VoskWakeWordDetector(
                self.config_manager,
                self.voice_system,
                self._on_wake_word_detected
            )
            
            success = self.wake_word_detector.start_listening()
            if success:
                self.wake_word_enabled = True
                print("✨ Vosk wake word detection started! Say 'Aiden' to activate...")
                
                # Pass wake word detector reference to dashboard if it exists
                if self.dashboard_backend:
                    self.dashboard_backend.wake_word_detector = self.wake_word_detector
                    
                    # Also pass to dashboard's voice system 
                    if hasattr(self.dashboard_backend, 'voice_system'):
                        self.dashboard_backend.voice_system.wake_word_detector = self.wake_word_detector
                        
                    # Also pass to command dispatcher's voice system
                    if hasattr(self.dashboard_backend, 'command_dispatcher') and hasattr(self.dashboard_backend.command_dispatcher, 'voice_system'):
                        self.dashboard_backend.command_dispatcher.voice_system.wake_word_detector = self.wake_word_detector
                
                # Pass wake word detector reference to voice system to prevent hearing own voice
                if self.voice_system:
                    self.voice_system.wake_word_detector = self.wake_word_detector
                
                self.show_notification("Wake Word Active", "Say 'Aiden' to activate voice assistant (Offline & Trained)")
                return True
            else:
                print("❌ Failed to start Vosk wake word detection")
                self.wake_word_detector = None
                return False
                
        except Exception as e:
            print(f"❌ Error starting wake word detection: {e}")
            self.wake_word_detector = None
            self.show_notification("Wake Word Error", f"Failed to start: {str(e)}")
            return False
    
    def stop_wake_word_detection(self):
        """Stop the wake word detection system"""
        try:
            if self.wake_word_detector and self.wake_word_enabled:
                print("Stopping wake word detection...")
                self.wake_word_detector.stop_listening()
                self.wake_word_enabled = False
                # Clear the detector object so it can be recreated on restart
                self.wake_word_detector = None
                print("✅ Wake word detection stopped successfully")
                self.show_notification("Wake Word Stopped", "Voice activation disabled")
                return True
            elif self.wake_word_detector and not self.wake_word_enabled:
                print("Wake word detector exists but was already disabled")
                # Clear the detector object for clean restart
                self.wake_word_detector = None
                return True
            else:
                print("No wake word detector to stop")
                return False
        except Exception as e:
            print(f"❌ Error stopping wake word detection: {e}")
            # Force disable even if there was an error and clear detector
            self.wake_word_enabled = False
            self.wake_word_detector = None
            return False
        
    def auto_start_wake_word_detection(self):
        """Automatically start wake word detection after delay"""
        print(f"Auto-starting wake word detection after {self.auto_start_delay} seconds...")
        success = self.start_wake_word_detection()
        if success:
            print("✅ Auto-start successful - Wake word detection is now active!")
            # Update the menu to reflect the new state if icon exists
            if hasattr(self, '_icon_ref') and self._icon_ref:
                self._icon_ref.menu = self.create_menu()
        else:
            print("❌ Auto-start failed - Wake word detection could not start")
    
    def toggle_wake_word_detection(self, icon, item):
        """Toggle wake word detection on/off from tray menu"""
        try:
            # Cancel auto-start timer if it's still pending
            if self.auto_start_timer and self.auto_start_timer.is_alive():
                self.auto_start_timer.cancel()
                print("Cancelled auto-start timer due to manual toggle")
            
            if self.wake_word_enabled:
                success = self.stop_wake_word_detection()
                if success:
                    print("✅ Wake word detection disabled via tray menu")
            else:
                # Ensure dashboard is running before starting wake word detection
                if self.dashboard_backend is None:
                    print("Starting dashboard for wake word detection...")
                    self.start_dashboard()
                    time.sleep(1)
                
                print("🔄 Attempting to restart wake word detection...")
                success = self.start_wake_word_detection()
                if success:
                    print("✅ Wake word detection enabled via tray menu")
                else:
                    print("❌ Failed to enable wake word detection")
            
            # Update the menu to reflect the new state using stored icon reference
            if hasattr(self, '_icon_ref') and self._icon_ref:
                self._icon_ref.menu = self.create_menu()
                status = "enabled" if self.wake_word_enabled else "disabled"
                print(f"✅ Menu updated successfully - Wake word is now {status}")
            
        except Exception as e:
            print(f"Error toggling wake word detection: {e}")
            self.show_notification("Wake Word Error", f"Toggle failed: {str(e)}")
    
    def _on_wake_word_detected(self):
        """Handle wake word detection - this triggers voice command listening"""
        try:
            print("🎯 Wake word 'Aiden' detected by Vosk!")
            
            if not self.initialization_complete:
                self.show_notification("Aiden Error", "Assistant not properly initialized")
                return
            
            # Start dashboard if not already running
            if self.dashboard_backend is None:
                self.start_dashboard()
                time.sleep(1)
            
            # Trigger wake word activation through dashboard (continuous conversation mode)
            if self.dashboard_backend:
                # Use continuous mode for wake word activation (not one-shot like hotkey)
                self.dashboard_backend._on_wake_word_activated()
                print("🎤 Listening for your command after wake word...")
            else:
                self.show_notification("Aiden Error", "Dashboard not available")
                
        except Exception as e:
            print(f"Error in wake word activation: {e}")
            self.show_notification("Aiden Error", f"Wake word activation failed: {str(e)}")
    
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
        
        # Cancel auto-start timer if still running
        if self.auto_start_timer and self.auto_start_timer.is_alive():
            self.auto_start_timer.cancel()
            print("Cancelled auto-start timer")
        
        # Stop hotkey listener
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop_listening()
            except:
                pass
        
        # Stop wake word detector
        if self.wake_word_detector:
            try:
                self.wake_word_detector.stop_listening()
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
        # Dynamic menu text based on wake word status
        wake_word_text = "🔇 Disable Wake Word" if self.wake_word_enabled else "🎯 Enable Wake Word ('Aiden')"
        
        return pystray.Menu(
            item('🎤 Activate Assistant', self.activate_assistant, default=True),
            item('🌐 Open Dashboard', self.open_dashboard),
            item(wake_word_text, self.toggle_wake_word_detection),
            pystray.Menu.SEPARATOR,
            item('❌ Quit', self.quit_app)
        )
    
    def speak_startup_message(self):
        """Speak the startup message with startup sound effect"""
        try:
            if self.voice_system and self.initialization_complete:
                # Play startup sound effect first
                print("🔊 Playing startup sound...")
                if hasattr(self.voice_system, '_play_sound_effect'):
                    self.voice_system._play_sound_effect("startup")
                    # Brief pause to let startup sound play
                    time.sleep(0.5)
                
                # Get user's name from profile
                user_profile = self.config_manager.get_user_profile()
                user_name = user_profile.get("personal", {}).get("name", "")
                
                # Create personalized startup message
                if user_name:
                    startup_message = f"Hello {user_name}! Aiden is active and ready to assist you. Say 'Aiden' or press the star key to call me."
                else:
                    startup_message = "Aiden is active and ready to assist you! Say 'Aiden' or press the star key to call me."
                
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
            
            # Store icon reference for menu updates
            self._icon_ref = icon
            
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
            
            # Schedule auto-start of wake word detection after delay
            self.auto_start_timer = threading.Timer(self.auto_start_delay, self.auto_start_wake_word_detection)
            self.auto_start_timer.daemon = True
            self.auto_start_timer.start()
            print(f"⏰ Wake word detection will auto-start in {self.auto_start_delay} seconds...")
            
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