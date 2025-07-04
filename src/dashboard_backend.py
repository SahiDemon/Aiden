"""
Aiden Dashboard Backend
Flask-based web API that connects to the main Aiden system
"""
import os
import sys
import json
import logging
import threading
import time
import subprocess
import random
from datetime import datetime
from typing import Dict, Any, List, Optional

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit, disconnect

# Add parent directory to path to import Aiden modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.config_manager import ConfigManager
from src.utils.voice_system import VoiceSystem
from src.utils.speech_recognition_system import SpeechRecognitionSystem
from src.utils.llm_connector import LLMConnector
from src.utils.command_dispatcher import CommandDispatcher
from src.utils.esp32_controller import ESP32Controller
from src.utils.hotkey_listener import HotkeyListener

class AidenDashboardBackend:
    """Flask backend for Aiden Dashboard"""
    
    def __init__(self):
        """Initialize the dashboard backend"""
        self.app = Flask(__name__, static_folder='../dashboard/build', static_url_path='')
        CORS(self.app)
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")
        
        # Initialize components
        self.config_manager = ConfigManager()
        self.voice_system = VoiceSystem(self.config_manager)
        self.stt_system = SpeechRecognitionSystem(self.config_manager)
        self.llm_connector = LLMConnector(self.config_manager)
        self.command_dispatcher = CommandDispatcher(
            self.config_manager, 
            self.voice_system, 
            dashboard_backend=self
        )
        self.esp32_controller = ESP32Controller(self.config_manager)
        
        # Conversation state
        self.conversation_active = False
        self.current_conversation = []
        self.is_listening = False
        self.connected_clients = set()
        
        # Add conversation context tracking
        self.pending_action = None
        self.conversation_context = {}
        
        # Add mode tracking for hotkey vs dashboard activation
        self.hotkey_mode = False  # True when activated by hotkey (one-shot mode)
        self.dashboard_mode = False  # True when activated by dashboard (continuous mode)
        self.verification_pending = False  # Track if verification is needed
        
        # Wake word detector reference (set by aiden_tray.py)
        self.wake_word_detector = None
        
        # Setup routes and socket handlers
        self._setup_routes()
        self._setup_socket_handlers()
        
        # Start hotkey listener with dashboard integration
        self.hotkey_listener = HotkeyListener(
            self.config_manager,
            self._on_hotkey_activated
        )
        
        print("Aiden Dashboard Backend initialized successfully")
    
    def _setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/')
        def serve_dashboard():
            """Serve the main dashboard"""
            return send_from_directory(self.app.static_folder, 'index.html')
        
        @self.app.route('/api/status')
        def get_status():
            """Get system status"""
            return jsonify({
                'status': 'online',
                'listening': self.is_listening,
                'conversation_active': self.conversation_active,
                'timestamp': datetime.now().isoformat(),
                'components': {
                    'voice_system': True,
                    'stt_system': True,
                    'llm_connector': True,
                    'esp32_controller': True
                }
            })
        
        @self.app.route('/api/config', methods=['GET'])
        def get_config():
            """Get current configuration"""
            try:
                config = self.config_manager.config
                user_profile = self.config_manager.get_user_profile()
                return jsonify({
                    'config': config,
                    'user_profile': user_profile,
                    'success': True
                })
            except Exception as e:
                return jsonify({'error': str(e), 'success': False}), 500
        
        @self.app.route('/api/config', methods=['POST'])
        def update_config():
            """Update configuration"""
            try:
                data = request.get_json()
                
                # Validate input data
                if not data:
                    return jsonify({'error': 'No data provided', 'success': False}), 400
                
                config_updated = False
                profile_updated = False
                
                # Update config if provided
                if 'config' in data:
                    try:
                        self.config_manager.update_config(data['config'])
                        config_updated = True
                        print("Configuration updated successfully")
                    except Exception as e:
                        print(f"Error updating config: {e}")
                        return jsonify({'error': f'Failed to update config: {str(e)}', 'success': False}), 500
                
                # Update user profile if provided
                if 'user_profile' in data:
                    try:
                        self.config_manager.update_user_profile(new_profile=data['user_profile'])
                        profile_updated = True
                        print("User profile updated successfully")
                    except Exception as e:
                        print(f"Error updating user profile: {e}")
                        return jsonify({'error': f'Failed to update user profile: {str(e)}', 'success': False}), 500
                
                # Reload components with new config (non-blocking)
                if config_updated or profile_updated:
                    try:
                        self._reload_components()
                    except Exception as e:
                        print(f"Warning: Component reload had issues: {e}")
                        # Don't fail the request if component reload has issues
                
                message = []
                if config_updated:
                    message.append("configuration")
                if profile_updated:
                    message.append("user profile")
                
                return jsonify({
                    'success': True, 
                    'message': f'Successfully updated {" and ".join(message)}',
                    'config_updated': config_updated,
                    'profile_updated': profile_updated
                })
                
            except Exception as e:
                print(f"Unexpected error in config update: {e}")
                return jsonify({'error': f'Unexpected error: {str(e)}', 'success': False}), 500
        
        @self.app.route('/api/conversation/history')
        def get_conversation_history():
            """Get conversation history"""
            try:
                user_profile = self.config_manager.get_user_profile()
                interactions = user_profile.get('history', {}).get('interactions', [])
                
                # Get recent interactions (last 50)
                recent_interactions = interactions[-50:] if len(interactions) > 50 else interactions
                
                return jsonify({
                    'history': recent_interactions,
                    'current_conversation': self.current_conversation,
                    'success': True
                })
            except Exception as e:
                return jsonify({'error': str(e), 'success': False}), 500
        
        @self.app.route('/api/conversation/suggestions')
        def get_conversation_suggestions():
            """Get personalized conversation suggestions based on user history"""
            try:
                suggestions = self._get_conversation_suggestions()
                return jsonify({
                    'suggestions': suggestions,
                    'timestamp': datetime.now().isoformat(),
                    'success': True
                })
            except Exception as e:
                return jsonify({'error': str(e), 'success': False}), 500
        
        @self.app.route('/api/conversation/send', methods=['POST'])
        def send_message():
            """Send a text message to Aiden"""
            try:
                data = request.get_json()
                message = data.get('message', '').strip()
                
                if not message:
                    return jsonify({'error': 'Empty message', 'success': False}), 400
                
                # Process the message
                self._process_text_message(message)
                
                return jsonify({'success': True, 'message': 'Message sent'})
            except Exception as e:
                return jsonify({'error': str(e), 'success': False}), 500
        
        @self.app.route('/api/voice/start-listening', methods=['POST'])
        def start_voice_listening():
            """Start voice listening - this is dashboard mode"""
            try:
                if self.is_listening:
                    return jsonify({'error': 'Already listening', 'success': False}), 400
                
                # Set dashboard mode when started from API
                self.dashboard_mode = True
                self.hotkey_mode = False
                
                # Start listening in a separate thread
                thread = threading.Thread(target=self._start_voice_interaction)
                thread.daemon = True
                thread.start()
                
                return jsonify({'success': True, 'message': 'Voice listening started'})
            except Exception as e:
                return jsonify({'error': str(e), 'success': False}), 500
        
        @self.app.route('/api/esp32/status')
        def esp32_status():
            """Get ESP32 status"""
            try:
                # Check ESP32 connection using the new method
                is_connected = self.esp32_controller.check_connection()
                return jsonify({
                    'connected': is_connected,
                    'ip_address': self.esp32_controller.ip_address,
                    'success': True
                })
            except Exception as e:
                return jsonify({
                    'connected': False,
                    'ip_address': self.esp32_controller.ip_address,
                    'error': str(e),
                    'success': False
                })
        
        @self.app.route('/api/esp32/detailed-status')
        def esp32_detailed_status():
            """Get detailed ESP32 status with diagnostics"""
            try:
                detailed_status = self.esp32_controller.get_detailed_status()
                return jsonify({
                    'success': True,
                    **detailed_status
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'ip_address': self.esp32_controller.ip_address
                })
        
        @self.app.route('/api/esp32/test', methods=['POST'])
        def esp32_test():
            """Test ESP32 connectivity and endpoints"""
            try:
                data = request.get_json()
                test_type = data.get('test_type', 'connectivity')
                
                if test_type == 'connectivity':
                    # Test basic connectivity
                    is_connected = self.esp32_controller.check_connection()
                    return jsonify({
                        'success': True,
                        'test_type': 'connectivity',
                        'result': is_connected,
                        'message': 'ESP32 is reachable' if is_connected else 'ESP32 is not reachable'
                    })
                
                elif test_type == 'detailed':
                    # Get detailed status
                    detailed_status = self.esp32_controller.get_detailed_status()
                    return jsonify({
                        'success': True,
                        'test_type': 'detailed',
                        'result': detailed_status
                    })
                
                elif test_type == 'ping':
                    # Simulate ping test
                    import subprocess
                    import platform
                    
                    # Use appropriate ping command for the OS
                    if platform.system().lower() == 'windows':
                        cmd = ['ping', '-n', '1', self.esp32_controller.ip_address]
                    else:
                        cmd = ['ping', '-c', '1', self.esp32_controller.ip_address]
                    
                    try:
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                        ping_success = result.returncode == 0
                        return jsonify({
                            'success': True,
                            'test_type': 'ping',
                            'result': ping_success,
                            'output': result.stdout if ping_success else result.stderr,
                            'message': 'Ping successful' if ping_success else 'Ping failed'
                        })
                    except subprocess.TimeoutExpired:
                        return jsonify({
                            'success': True,
                            'test_type': 'ping',
                            'result': False,
                            'message': 'Ping timeout'
                        })
                
                else:
                    return jsonify({'error': 'Invalid test type', 'success': False}), 400
                    
            except Exception as e:
                return jsonify({'error': str(e), 'success': False}), 500
        
        @self.app.route('/api/esp32/smart-status')
        def esp32_smart_status():
            """Get smart fan status with current speed and state"""
            try:
                status_info = self.esp32_controller.get_status()
                human_readable = self.esp32_controller.get_human_readable_status()
                
                return jsonify({
                    'success': status_info['success'],
                    'raw_status': status_info.get('raw_status', ''),
                    'parsed': status_info.get('parsed', {}),
                    'human_readable': human_readable,
                    'error': status_info.get('error'),
                    'ip_address': self.esp32_controller.ip_address
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'ip_address': self.esp32_controller.ip_address
                })
        
        @self.app.route('/api/esp32/control', methods=['POST'])
        def esp32_control():
            """Control ESP32 fan with smart features"""
            try:
                data = request.get_json()
                action = data.get('action')
                speed = data.get('speed')  # Optional speed parameter
                
                result = False
                message = ""
                
                if action == 'turn_on':
                    result = self.esp32_controller.turn_on()
                    message = "The fan has been turned on"
                elif action == 'turn_off':
                    result = self.esp32_controller.turn_off()
                    message = "The fan has been turned off"
                elif action == 'change_mode':
                    result = self.esp32_controller.change_mode()
                    message = "The fan mode has been changed"
                elif action == 'cycle_speed':
                    # Use smart cycling based on current status
                    result = self.esp32_controller.cycle_speed()
                    message = "The fan speed has been cycled intelligently"
                elif action == 'set_speed':
                    # Set specific speed
                    if speed and speed in [1, 2, 3]:
                        result = self.esp32_controller.set_speed(int(speed))
                        speed_names = {1: 'low', 2: 'medium', 3: 'high'}
                        speed_name = speed_names.get(int(speed), str(speed))
                        message = f"The fan has been set to speed level {speed}, which is {speed_name} speed"
                    else:
                        return jsonify({'error': 'Invalid speed. Must be 1, 2, or 3', 'success': False}), 400
                elif action == 'test_connection':
                    # Test connection by trying a simple command
                    result = self.esp32_controller.check_connection()
                    if not result:
                        # Try a ping test using the turn_on command (safe)
                        result = self.esp32_controller.turn_on()
                    message = "Connection test completed" if result else "Connection test failed"
                else:
                    return jsonify({'error': 'Invalid action', 'success': False}), 400
                
                # Emit to all connected clients
                self.socketio.emit('esp32_action', {
                    'action': action,
                    'success': result,
                    'message': message,
                    'timestamp': datetime.now().isoformat()
                })
                
                return jsonify({'success': result, 'message': message})
            except Exception as e:
                return jsonify({'error': str(e), 'success': False}), 500
        
        @self.app.route('/api/system/stats')
        def get_system_stats():
            """Get real system statistics"""
            try:
                import psutil
                import time
                from datetime import datetime, timedelta
                
                # Get system uptime
                boot_time = datetime.fromtimestamp(psutil.boot_time())
                uptime = datetime.now() - boot_time
                uptime_str = f"{uptime.days}d {uptime.seconds//3600}h {(uptime.seconds//60)%60}m"
                
                # Get memory usage
                memory = psutil.virtual_memory()
                
                # Get CPU usage
                cpu_percent = psutil.cpu_percent(interval=1)
                
                # Get process info for Aiden
                current_process = psutil.Process()
                aiden_memory = current_process.memory_info().rss / 1024 / 1024  # MB
                
                # Get interaction stats from user profile
                user_profile = self.config_manager.get_user_profile()
                interactions = user_profile.get("history", {}).get("interactions", [])
                total_sessions = user_profile.get("history", {}).get("total_sessions", 0)
                
                # Count interaction types
                voice_interactions = len([i for i in interactions if i.get("input_type") == "voice"])
                text_interactions = len([i for i in interactions if i.get("input_type") == "text"])
                
                # Get recent interactions (last 24 hours)
                now = datetime.now()
                recent_interactions = []
                for interaction in interactions:
                    try:
                        interaction_time = datetime.fromisoformat(interaction.get("timestamp", "").replace("Z", "+00:00"))
                        if (now - interaction_time.replace(tzinfo=None)).total_seconds() < 86400:  # 24 hours
                            recent_interactions.append(interaction)
                    except:
                        continue
                
                return jsonify({
                    'success': True,
                    'system': {
                        'uptime': uptime_str,
                        'cpu_percent': cpu_percent,
                        'memory_percent': memory.percent,
                        'memory_used_gb': memory.used / 1024 / 1024 / 1024,
                        'memory_total_gb': memory.total / 1024 / 1024 / 1024,
                        'aiden_memory_mb': aiden_memory
                    },
                    'interactions': {
                        'total': len(interactions),
                        'voice': voice_interactions,
                        'text': text_interactions,
                        'recent_24h': len(recent_interactions),
                        'total_sessions': total_sessions
                    },
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                return jsonify({'error': str(e), 'success': False}), 500
        
        @self.app.route('/api/system/components')
        def get_component_status():
            """Get real component status"""
            try:
                components = {}
                
                # Test Voice System
                try:
                    if hasattr(self, 'voice_system') and self.voice_system:
                        # Try to get voice settings to test if it's working
                        voice_config = self.voice_system.config.get("voice", {})
                        components['voice_system'] = True
                    else:
                        components['voice_system'] = False
                except:
                    components['voice_system'] = False
                
                # Test STT System
                try:
                    if hasattr(self, 'stt_system') and self.stt_system:
                        components['stt_system'] = True
                    else:
                        components['stt_system'] = False
                except:
                    components['stt_system'] = False
                
                # Test LLM Connector
                try:
                    if hasattr(self, 'llm_connector') and self.llm_connector:
                        components['llm_connector'] = True
                    else:
                        components['llm_connector'] = False
                except:
                    components['llm_connector'] = False
                
                # Test ESP32 Controller
                try:
                    if hasattr(self, 'esp32_controller') and self.esp32_controller:
                        # Actually test ESP32 connectivity
                        status = self.esp32_controller.get_status()
                        components['esp32_controller'] = status.get('connected', False)
                    else:
                        components['esp32_controller'] = False
                except:
                    components['esp32_controller'] = False
                
                return jsonify({
                    'success': True,
                    'components': components,
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                return jsonify({'error': str(e), 'success': False}), 500
    
    def _setup_socket_handlers(self):
        """Setup SocketIO event handlers"""
        
        @self.socketio.on('connect')
        def handle_connect(auth=None):
            """Handle client connection"""
            self.connected_clients.add(request.sid)
            emit('status', {
                'message': 'Connected to Aiden Dashboard',
                'listening': self.is_listening,
                'conversation_active': self.conversation_active
            })
            print(f"Client connected: {request.sid}")
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            """Handle client disconnection"""
            self.connected_clients.discard(request.sid)
            print(f"Client disconnected: {request.sid}")
        
        @self.socketio.on('start_voice')
        def handle_start_voice():
            """Handle start voice command from client - this is dashboard mode"""
            if not self.is_listening:
                # Set dashboard mode when started from web interface
                self.dashboard_mode = True
                self.hotkey_mode = False
                thread = threading.Thread(target=self._start_voice_interaction)
                thread.daemon = True
                thread.start()
        
        @self.socketio.on('stop_voice')
        def handle_stop_voice():
            """Handle stop voice command from client"""
            self.is_listening = False
            self.conversation_active = False
            emit('voice_status', {'listening': False, 'conversation_active': False})
            
        @self.socketio.on('clear_conversation')
        def handle_clear_conversation():
            """Handle clear conversation request"""
            self.current_conversation = []
            print("Conversation history cleared")
            emit('conversation_cleared', {'success': True})
        
        @self.socketio.on('action_item_clicked')
        def handle_action_item_clicked(data):
            """Handle clicks on action card items"""
            try:
                item = data.get('item')
                action_type = data.get('action_type')
                
                if action_type == 'app_list' or action_type == 'app_selection':
                    # Launch the selected app using the intelligent app manager
                    app_name = item.get('name', item) if isinstance(item, dict) else item
                    
                    # Use the command dispatcher's intelligent app launching
                    parameters = {
                        "app_name": app_name.lower().strip(),
                        "operation": "launch",
                        "original_query": f"open {app_name}"
                    }
                    
                    success = self.command_dispatcher._handle_app_control(parameters)
                    emit('action_result', {'success': success, 'message': f"{'Launched' if success else 'Failed to launch'} {app_name}"})
                
                elif action_type == 'project_list':
                    # Open project in VSCode
                    project_path = item.get('path') if isinstance(item, dict) else item
                    success = self._open_project_in_vscode(project_path)
                    emit('action_result', {'success': success, 'message': f"{'Opened' if success else 'Failed to open'} project in VSCode"})
                
                elif item.get('action') == 'create_new':
                    # Create new project
                    success = self._create_new_project_from_dashboard()
                    emit('action_result', {'success': success, 'message': 'New project created' if success else 'Failed to create project'})
                
                elif item.get('action') == 'open_folder':
                    # Open GitHub folder
                    success = self._open_github_folder()
                    emit('action_result', {'success': success, 'message': 'Opened GitHub folder' if success else 'Failed to open folder'})
                
                # Handle verification button clicks
                elif item.get('action') == 'confirm_schedule':
                    # Confirm scheduled command
                    if hasattr(self.command_dispatcher, '_pending_schedule') and self.command_dispatcher._pending_schedule:
                        result = self.command_dispatcher.scheduled_commands.confirm_schedule(self.command_dispatcher._pending_schedule)
                        self.command_dispatcher._pending_schedule = None
                        
                        # Resume voice input and send response
                        self.verification_pending = False
                        response_msg = result.get('response', 'Schedule confirmed')
                        
                        # Add voice confirmation
                        if self.command_dispatcher and hasattr(self.command_dispatcher, 'voice_system'):
                            self.command_dispatcher.voice_system.speak(response_msg)
                        
                        self._emit_ai_message(response_msg, "response")
                        emit('action_result', {'success': True, 'message': response_msg})
                        
                        # End conversation if in one-shot mode
                        if hasattr(self, 'hotkey_mode') and self.hotkey_mode:
                            self.conversation_active = False
                    else:
                        emit('action_result', {'success': False, 'message': 'No pending schedule to confirm'})
                
                elif item.get('action') == 'cancel_schedule':
                    # Cancel scheduled command
                    if hasattr(self.command_dispatcher, '_pending_schedule') and self.command_dispatcher._pending_schedule:
                        self.command_dispatcher._pending_schedule = None
                        
                        # Resume voice input and send response
                        self.verification_pending = False
                        response_msg = 'Schedule cancelled'
                        
                        # Add voice confirmation
                        if self.command_dispatcher and hasattr(self.command_dispatcher, 'voice_system'):
                            self.command_dispatcher.voice_system.speak(response_msg)
                        
                        self._emit_ai_message(response_msg, "response")
                        emit('action_result', {'success': True, 'message': response_msg})
                        
                        # End conversation if in one-shot mode
                        if hasattr(self, 'hotkey_mode') and self.hotkey_mode:
                            self.conversation_active = False
                    else:
                        emit('action_result', {'success': False, 'message': 'No pending schedule to cancel'})
                
                elif item.get('action') == 'confirm_immediate':
                    # Confirm immediate command
                    if hasattr(self.command_dispatcher, '_pending_immediate') and self.command_dispatcher._pending_immediate:
                        operation = self.command_dispatcher._pending_immediate
                        success = self.command_dispatcher._execute_immediate_system_command(operation)
                        self.command_dispatcher._pending_immediate = None
                        
                        # Resume voice input and send response
                        self.verification_pending = False
                        response_msg = f'{"Executed" if success else "Failed to execute"} {operation} command'
                        self._emit_ai_message(response_msg, "response")
                        emit('action_result', {'success': success, 'message': response_msg})
                        
                        # End conversation if in one-shot mode
                        if hasattr(self, 'hotkey_mode') and self.hotkey_mode:
                            self.conversation_active = False
                    else:
                        emit('action_result', {'success': False, 'message': 'No pending command to confirm'})
                
                elif item.get('action') == 'cancel_immediate':
                    # Cancel immediate command
                    if hasattr(self.command_dispatcher, '_pending_immediate') and self.command_dispatcher._pending_immediate:
                        self.command_dispatcher._pending_immediate = None
                        
                        # Resume voice input and send response
                        self.verification_pending = False
                        response_msg = 'Command cancelled'
                        self._emit_ai_message(response_msg, "response")
                        emit('action_result', {'success': True, 'message': response_msg})
                        
                        # End conversation if in one-shot mode
                        if hasattr(self, 'hotkey_mode') and self.hotkey_mode:
                            self.conversation_active = False
                    else:
                        emit('action_result', {'success': False, 'message': 'No pending command to cancel'})
                
                elif item.get('action') == 'modify_schedule_time':
                    # Handle time modification request
                    if hasattr(self.command_dispatcher, '_pending_schedule') and self.command_dispatcher._pending_schedule:
                        response_msg = "Please specify the new time (e.g., '5 minutes', '1 hour')"
                        self._emit_ai_message(response_msg, "response")
                        
                        # Send time input prompt
                        time_request_card = {
                            "type": "time_specification",
                            "title": "Modify Schedule Time",
                            "message": response_msg,
                            "operation": self.command_dispatcher._pending_schedule.get("operation", "command"),
                            "input_placeholder": "e.g., 10 minutes, 1 hour, 30 seconds",
                            "message_id": "time_modification",
                            "pending_action": "time_input"
                        }
                        self._emit_ai_message(time_request_card, "action_card")
                        emit('action_result', {'success': True, 'message': 'Time modification requested'})
                    else:
                        emit('action_result', {'success': False, 'message': 'No pending schedule to modify'})

                # Handle scheduled commands actions
                elif action_type == 'scheduled_commands' or item.get('action') == 'cancel_all_schedules':
                    # Cancel all schedules
                    result = self.command_dispatcher.scheduled_commands.abort_schedule()
                    emit('action_result', {'success': result.get('success', False), 'message': result.get('response', 'Failed to cancel schedules')})
                
                elif item.get('task_id'):
                    # Cancel specific schedule
                    task_id = item.get('task_id')
                    
                    # Handle 'all' as a special case
                    if task_id == 'all':
                        result = self.command_dispatcher.scheduled_commands.abort_schedule()
                        emit('action_result', {'success': result.get('success', False), 'message': result.get('response', 'Failed to cancel schedules')})
                        return
                        
                    # Handle individual task cancellation
                    with self.command_dispatcher.scheduled_commands.schedule_lock:
                        if task_id in self.command_dispatcher.scheduled_commands.active_schedules:
                            operation = self.command_dispatcher.scheduled_commands.active_schedules[task_id].get('operation', 'unknown')
                            del self.command_dispatcher.scheduled_commands.active_schedules[task_id]
                            self.command_dispatcher.scheduled_commands._update_dashboard_schedules()
                            emit('action_result', {'success': True, 'message': f'Cancelled {operation} schedule'})
                        else:
                            emit('action_result', {'success': False, 'message': 'Schedule not found or already completed'})
                
            except Exception as e:
                logging.error(f"Error handling action item click: {e}")
                emit('action_result', {'success': False, 'message': 'Failed to handle action'})
    
    def _on_hotkey_activated(self):
        """Handle hotkey activation - continuous conversation mode (from tray menu)"""
        print("Hotkey activated - CONTINUOUS CONVERSATION mode")
        
        # Set mode flags
        self.hotkey_mode = False
        self.dashboard_mode = True
        
        # Notify all connected clients
        self.socketio.emit('hotkey_activated', {
            'message': 'Voice conversation started - Continuous mode',
            'timestamp': datetime.now().isoformat()
        })
        
        # Start voice interaction
        if not self.is_listening:
            thread = threading.Thread(target=self._start_voice_interaction)
            thread.daemon = True
            thread.start()
    
    def _on_hotkey_activated_oneshot(self):
        """Handle hotkey activation - one-shot mode (from actual hotkey press)"""
        print("Hotkey activated - ONE-SHOT mode")
        
        # Set mode flags
        self.hotkey_mode = True
        self.dashboard_mode = False
        
        # Notify all connected clients
        self.socketio.emit('hotkey_activated', {
            'message': 'Hotkey activated - One command mode',
            'timestamp': datetime.now().isoformat()
        })
        
        # Start voice interaction in one-shot mode
        if not self.is_listening:
            thread = threading.Thread(target=self._start_voice_interaction_oneshot)
            thread.daemon = True
            thread.start()
    
    def _on_wake_word_activated(self):
        """Handle wake word activation - continuous conversation mode (like voice assistants)"""
        print("Wake word 'Aiden' detected - CONTINUOUS CONVERSATION mode")
        
        # Set mode flags (continuous like tray menu, not one-shot like hotkey)
        self.hotkey_mode = False
        self.dashboard_mode = True
        
        # Notify all connected clients
        self.socketio.emit('wake_word_activated', {
            'message': 'Wake word detected - Voice conversation started',
            'timestamp': datetime.now().isoformat()
        })
        
        # Start voice interaction in continuous mode
        if not self.is_listening:
            thread = threading.Thread(target=self._start_voice_interaction)
            thread.daemon = True
            thread.start()
    
    def _start_voice_interaction(self):
        """Start a voice interaction session"""
        try:
            self.is_listening = True
            self.conversation_active = True
            
            # Ensure we're in dashboard mode (continuous conversation)
            self.dashboard_mode = True
            self.hotkey_mode = False
            
            # Notify clients about conversation start
            self.socketio.emit('voice_status', {
                'listening': True,
                'conversation_active': True,
                'speaking': False,
                'status': 'listening'
            })
            
            # REMOVED: Don't play greeting, just update UI silently
            self._emit_ai_message("Ready to listen...", "system")
            
            # Continue conversation loop
            while self.conversation_active and self.is_listening:
                # Play ready sound and update status to listening
                self.voice_system.play_ready_sound()
                self.socketio.emit('voice_status', {
                    'listening': True,
                    'conversation_active': True,
                    'speaking': False,
                    'status': 'listening'
                })
                
                # Listen for voice input (pass hotkey listener to avoid conflicts)
                success, text, error = self.stt_system.listen(self.hotkey_listener)
                
                if success and text:
                    # Update status to processing
                    self.socketio.emit('voice_status', {
                        'listening': False,
                        'conversation_active': True,
                        'speaking': False,
                        'status': 'processing'
                    })
                    
                    # Pause wake word detection while processing and responding
                    if self.wake_word_detector:
                        self.wake_word_detector.pause_listening()
                    
                    # Process the voice command
                    self._process_voice_message(text)
                    
                    # Exit detection now handled in _process_message_common before processing
                    # If we reach here, the conversation should continue normally
                    
                    # Resume wake word detection after processing
                    if self.wake_word_detector:
                        self.wake_word_detector.resume_listening()
                    
                    # For all other responses, continue the conversation normally
                    # Only ask follow-up for substantial commands that need clarification
                    if self._should_ask_follow_up(text):
                        self._ask_for_follow_up()
                    else:
                        # For simple responses, just continue listening
                        print(f"Simple response received, continuing conversation: {text}")
                        continue
                        
                elif error:
                    # Handle different types of errors
                    if error == "timeout":
                        # Silent timeout - user didn't speak, go to standby
                        print("Silent timeout - going to standby")
                        self.conversation_active = False
                        break
                    else:
                        # Actual speech recognition error - provide feedback
                        self.socketio.emit('voice_status', {
                            'listening': False,
                            'conversation_active': True,
                            'speaking': True,
                            'status': 'speaking'
                        })
                        
                        # Provide user-friendly error messages
                        if "network" in error.lower():
                            friendly_error = "Having trouble with the speech service. Please check your internet connection."
                        elif "microphone" in error.lower():
                            friendly_error = "Having trouble accessing your microphone. Please check your microphone settings."
                        else:
                            friendly_error = "I couldn't understand that. Please try speaking more clearly."
                        
                        self._emit_ai_message(friendly_error, "error")
                        self.voice_system.speak(friendly_error)
                        
                        # Don't end conversation on speech errors, just try again
                        print(f"Speech recognition error (continuing): {error}")
                        continue
                
        except Exception as e:
            print(f"Error in voice interaction: {e}")
            self._emit_ai_message(f"Error in voice interaction: {str(e)}", "error")
        finally:
            # Resume wake word detection if it was paused
            if self.wake_word_detector:
                self.wake_word_detector.resume_listening()
                
            self.is_listening = False
            self.conversation_active = False
            self.dashboard_mode = False  # Reset mode flag
            self.socketio.emit('voice_status', {
                'listening': False,
                'conversation_active': False,
                'speaking': False,
                'status': 'idle'
            })
    
    def _start_voice_interaction_oneshot(self):
        """Start a ONE-SHOT voice interaction session (for hotkey activation)"""
        try:
            self.is_listening = True
            self.conversation_active = True
            
            # Notify clients about conversation start
            self.socketio.emit('voice_status', {
                'listening': True,
                'conversation_active': True,
                'speaking': False,
                'status': 'listening'
            })
            
            # REMOVED: Don't play greeting, just update UI silently for one-shot mode
            self._emit_ai_message("Listening for one command...", "system")
            
            # ONE-SHOT mode: Start with one command, but may continue if needed
            while self.conversation_active and self.is_listening:
                # Play ready sound and update status to listening
                self.voice_system.play_ready_sound()
                self.socketio.emit('voice_status', {
                    'listening': True,
                    'conversation_active': True,
                    'speaking': False,
                    'status': 'listening'
                })
                
                # Listen for voice input (pass hotkey listener to avoid conflicts)
                success, text, error = self.stt_system.listen(self.hotkey_listener)
                
                if success and text:
                    # Update status to processing
                    self.socketio.emit('voice_status', {
                        'listening': False,
                        'conversation_active': True,
                        'speaking': False,
                        'status': 'processing'
                    })
                    
                    # Pause wake word detection while processing and responding
                    if self.wake_word_detector:
                        self.wake_word_detector.pause_listening()
                    
                    # Set a flag to pause listening for verification if needed
                    waiting_for_verification = False
                    
                    # Process the voice command
                    self._process_voice_message(text)
                    
                    # Check if we have any pending verifications
                    if hasattr(self.command_dispatcher, '_pending_schedule') and self.command_dispatcher._pending_schedule:
                        print(f"ONE-SHOT mode: Command '{text}' waiting for schedule verification")
                        waiting_for_verification = True
                        # Pause listening while waiting for verification
                        self.socketio.emit('voice_status', {
                            'listening': False,
                            'conversation_active': True,
                            'speaking': False,
                            'status': 'waiting_for_verification'
                        })
                        # Don't break the loop yet, but don't continue listening either
                        # Wait for button clicks to handle via socket events
                        break
                        
                    elif hasattr(self.command_dispatcher, '_pending_immediate') and self.command_dispatcher._pending_immediate:
                        print(f"ONE-SHOT mode: Command '{text}' waiting for immediate verification")
                        waiting_for_verification = True
                        # Pause listening while waiting for verification
                        self.socketio.emit('voice_status', {
                            'listening': False, 
                            'conversation_active': True,
                            'speaking': False,
                            'status': 'waiting_for_verification'
                        })
                        # Don't break the loop yet, but don't continue listening either
                        # Wait for button clicks to handle via socket events
                        break
                    
                    # If not waiting for verification, apply normal one-shot logic
                    if not waiting_for_verification:
                        if not self.conversation_active:
                            print(f"ONE-SHOT mode: Command '{text}' completed, ending conversation")
                            break
                        else:
                            print(f"ONE-SHOT mode: Command '{text}' needs follow-up, continuing...")
                            # Continue the loop for follow-up
                        
                elif error:
                    # Handle different types of errors
                    if error == "timeout":
                        # Silent timeout - user didn't speak, go to standby
                        print("ONE-SHOT mode: Silent timeout - ending")
                        self.conversation_active = False
                        break
                    else:
                        # Actual speech recognition error - provide feedback but still end
                        self.socketio.emit('voice_status', {
                            'listening': False,
                            'conversation_active': True,
                            'speaking': True,
                            'status': 'speaking'
                        })
                        
                        # Provide user-friendly error messages
                        if "network" in error.lower():
                            friendly_error = "Having trouble with the speech service. Please try again later."
                        elif "microphone" in error.lower():
                            friendly_error = "Having trouble accessing your microphone. Please check your microphone settings."
                        else:
                            friendly_error = "I couldn't understand that. Please try again."
                        
                        self._emit_ai_message(friendly_error, "error")
                        self.voice_system.speak(friendly_error)
                        
                        # End conversation even on error in one-shot mode
                        print(f"ONE-SHOT mode: Speech recognition error, ending: {error}")
                        self.conversation_active = False
                        break
                
        except Exception as e:
            print(f"Error in one-shot voice interaction: {e}")
            self._emit_ai_message(f"Error in voice interaction: {str(e)}", "error")
        finally:
            # Resume wake word detection if it was paused
            if self.wake_word_detector:
                self.wake_word_detector.resume_listening()
                
            self.is_listening = False
            self.conversation_active = False
            self.hotkey_mode = False  # Reset mode flag
            self.socketio.emit('voice_status', {
                'listening': False,
                'conversation_active': False,
                'speaking': False,
                'status': 'idle'
            })
    
    def _process_voice_message(self, text: str):
        """Process a voice message"""
        self._process_message_common(text)
    
    def _process_text_message(self, text: str):
        """Process a text message"""
        self._emit_user_message(text, "text")
        self._process_message_common(text)
    
    def _process_message_common(self, text: str):
        """Common message processing logic for both voice and text"""
        try:
            # FIRST: Check for exit commands before any processing
            text_lower = text.lower().strip()
            
            # End conversation immediately for any thank expression or exit command
            exit_patterns = [
                "bye", "goodbye", "stop", "exit", "quit", 
                "end conversation", "stop conversation"
            ]
            
            # Check for thank expressions first (most common way to end)
            if text_lower in ["thank you", "thanks", "no thank you", "no thanks", "thank"]:
                print(f"Ending conversation immediately due to dismissal: {text}")
                self.conversation_active = False
                # Don't process further, just end
                return
            
            # Check for other exit patterns
            elif any(phrase in text_lower for phrase in exit_patterns):
                print(f"Ending conversation immediately due to exit command: {text}")
                self.conversation_active = False
                # Don't process further, just end
                return
            
            # Store the user message first
            user_message = {
                'type': 'user',
                'text': text,
                'timestamp': datetime.now().isoformat(),
                'input_type': 'voice' if hasattr(self, '_current_input_type') and self._current_input_type == 'voice' else 'text'
            }
            
            self.current_conversation.append(user_message)
            self._emit_user_message(text, user_message['input_type'])
            
            # SPECIAL HANDLING: Check for verification responses FIRST
            # This ensures that "yes", "no", etc. are properly handled in context
            if self._is_verification_response(text):
                print(f"Detected verification response: '{text}'")
                # Process as verification response through command dispatcher
                handled = self.command_dispatcher._handle_pending_verifications(text)
                if handled:
                    print("Verification response successfully handled")
                    # Check if we should end conversation based on mode
                    if hasattr(self, 'hotkey_mode') and self.hotkey_mode:
                        print("HOTKEY MODE: Verification completed, ending conversation")
                        self.conversation_active = False
                    return
                else:
                    print("Verification response not handled, continuing as normal command")
            
            # FIRST: Check for pending actions that need to be continued
            if self.pending_action:
                success = self._handle_pending_action(text)
                if success:
                    # Action was handled successfully
                    if hasattr(self, 'hotkey_mode') and self.hotkey_mode:
                        # In hotkey mode, always end after handling pending action
                        print("HOTKEY MODE: Pending action handled, ending conversation")
                        self.conversation_active = False
                    elif self._should_ask_follow_up(text):
                        self._ask_for_follow_up()
                    else:
                        self.conversation_active = False
                    return
                else:
                    # Failed to handle as pending action, clear it and process as new command
                    self.clear_pending_action()
            
            # Process as new command
            command = self.llm_connector.process_command(text)
            
            # Handle end_conversation action specially
            if command.get("action") == "end_conversation":
                self._emit_ai_message(command.get("response", "Conversation ended. I'll be here when you need me."), "response")
                self.conversation_active = False
                # Execute command to properly close everything
                self.command_dispatcher.dispatch(command)
                return
                
            # Record the interaction
            self.config_manager.record_interaction(
                command["action"],
                text,
                command["parameters"]
            )
            
            # Check if it's a system info query (don't emit AI response for these)
            is_system_info_query = (
                command.get("action") == "provide_information" and
                any(word in command.get("parameters", {}).get("query", "").lower() 
                    for word in ["time", "date", "weather"])
            )
            
            # Also check if it's a project listing query (let the dispatcher handle the response)
            is_project_listing_query = (
                command.get("action") == "provide_information" and
                any(phrase in command.get("parameters", {}).get("query", "").lower() 
                    for phrase in ["list my projects", "show my projects", "my projects", "project list", "show projects", "what projects"])
            )
            
            # Always emit AI response for regular conversations, but let specific handlers manage their own responses
            if not is_system_info_query and not is_project_listing_query:
                # Get AI response and emit it
                ai_response = command.get("response", "Processing your request...")
                self._emit_ai_message(ai_response, "response")
                
                # Update status to speaking for AI response
                self.socketio.emit('voice_status', {
                    'listening': False,
                    'conversation_active': True,
                    'speaking': True,
                    'status': 'speaking'
                })
            
                # For ALL provide_information actions, speak here and prevent dispatcher speech
                # This includes simple greetings, conversational responses, etc.
                # BUT exclude fan_control status checks - let the dispatcher handle those
                if command.get("action") == "provide_information":
                    # Speak the response immediately for all informational responses
                    self.voice_system.speak(ai_response)
                    # Set a flag to prevent dispatcher from speaking again
                    command["_already_spoken"] = True
                    # Also add the flag to parameters for the handler
                    command.get("parameters", {})["_prevent_speech"] = True
                elif command.get("action") == "fan_control":
                    # For fan control, check if it's a status check
                    operation = command.get("parameters", {}).get("operation", "").lower()
                    if "status" in operation or "check" in operation or "state" in operation:
                        # For fan status checks, DON'T speak here - let dispatcher handle everything
                        # This prevents double speaking
                        pass
                    else:
                        # For fan control actions (on/off/speed), speak normally and prevent dispatcher speech
                        self.voice_system.speak(ai_response)
                        command["_already_spoken"] = True
                        command.get("parameters", {})["_prevent_speech"] = True
            
            # Execute the command
            result = self.command_dispatcher.dispatch(command)
            
            # DISABLED: Add proactive suggestions after command execution
            # Only for substantial interactions and if command was successful
            # if result and len(text.strip()) > 15:
            #     self._schedule_proactive_suggestions(text)
            
            # Emit command execution result
            self.socketio.emit('command_executed', {
                'command': command,
                'result': result,
                'timestamp': datetime.now().isoformat()
            })
            
            # For project listing queries, always continue conversation to get project selection
            is_project_or_app_listing = (
                command.get("action") == "provide_information" and
                any(phrase in command.get("parameters", {}).get("query", "").lower() 
                    for phrase in ["list my projects", "show my projects", "my projects", "project list", "show projects", "what projects", "list apps", "show apps", "available apps"])
            )
            
            # Handle follow-up based on command success and type
            if self.hotkey_mode:
                # In hotkey mode, be smart about when to end conversation
                should_end_conversation = self._should_end_hotkey_conversation(text, command)
                if should_end_conversation:
                    print("HOTKEY MODE: Task completed, ending conversation")
                    self.conversation_active = False
                else:
                    print("HOTKEY MODE: Continuing conversation (greeting/needs follow-up)")
                    # Continue conversation for greetings, clarifications, etc.
            elif is_project_or_app_listing:
                # Always continue conversation for project/app listing to get selection
                self.conversation_active = True
                # Don't ask follow-up immediately - let the user respond to the list
            elif command.get("action") == "stop_current_task":
                # When stopping a task, keep conversation active but don't ask follow-ups
                self.conversation_active = True
            else:
                # For other interactions, continue conversation unless it's a goodbye
                text_lower = text.lower().strip()
                is_goodbye = any(phrase in text_lower for phrase in ["bye", "goodbye", "see you"])
                is_stop = any(phrase in text_lower for phrase in ["stop", "exit", "quit", "stop conversation", "end conversation"])
                
                if is_stop:
                    # Handle stop commands specially - emit appropriate message if not already handled
                    if command.get("action") not in ["end_conversation", "stop_current_task"]:
                        self._emit_ai_message("Conversation ended. Let me know if you need anything else!", "response")
                    self.conversation_active = False
                elif not is_goodbye and len(text.strip()) > 5:
                    self.conversation_active = True
                else:
                    self.conversation_active = False
            
        except Exception as e:
            error_msg = f"Error processing command: {str(e)}"
            self._emit_ai_message(error_msg, "error")
            self.voice_system.speak("I encountered an error processing your request.")
            self.conversation_active = False
    
    def _should_ask_follow_up(self, text: str) -> bool:
        """Determine if we should ask a follow-up question based on the user's input"""
        text_lower = text.lower().strip()
        
        # Don't ask follow-ups for simple greetings or responses
        simple_responses = [
            "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
            "how are you", "how r u", "how's it going", "what's up", "thanks", "thank you", 
            "no thanks", "nope", "ok", "okay", "fine", "good", "great", "alright", 
            "sure", "yes", "yeah", "yep", "bye", "goodbye", "stop", "exit", "quit", "thank you", "thanks"
        ]
        
        for simple in simple_responses:
            if simple in text_lower:
                return False
        
        # Don't ask follow-ups for very short responses (likely acknowledgments)
        if len(text.strip()) < 5:
            return False
        
        # Ask follow-ups for longer, more substantial interactions
        return len(text.strip()) > 10
    
    def _should_end_hotkey_conversation(self, text: str, command: dict) -> bool:
        """Determine if hotkey conversation should end based on the command type and user input"""
        text_lower = text.lower().strip()
        action = command.get("action", "")
        
        # CRITICAL: Never end if there's a pending verification waiting for user response!
        if hasattr(self.command_dispatcher, '_pending_schedule') and getattr(self.command_dispatcher, '_pending_schedule', None):
            print("HOTKEY MODE: Pending schedule verification - continuing to wait for user response")
            return False
            
        if hasattr(self.command_dispatcher, '_pending_immediate') and getattr(self.command_dispatcher, '_pending_immediate', None):
            print("HOTKEY MODE: Pending immediate verification - continuing to wait for user response")
            return False
            
        if hasattr(self.command_dispatcher, '_pending_time_request') and getattr(self.command_dispatcher, '_pending_time_request', None):
            print("HOTKEY MODE: Pending time specification - continuing to wait for user response")
            return False
        
        # FIRST: Check for completed actions (highest priority)
        completed_actions = [
            "app_control", "file_operation", "system_command", "web_search",
            "change_settings"
        ]
        
        # For fan_control, only end if it's an actual control action, not status check
        if action == "fan_control":
            operation = command.get("parameters", {}).get("operation", "").lower()
            if "status" in operation or "check" in operation or "state" in operation:
                print(f"HOTKEY MODE: Fan status check - continuing conversation")
                return False
            else:
                print(f"HOTKEY MODE: Fan control action '{operation}' completed - ending")
                return True
        
        if action in completed_actions:
            print(f"HOTKEY MODE: Action '{action}' completed - ending")
            return True
        
        # SECOND: Check for completed information requests
        information_requests = [
            "what time", "current time", "time is", "what date", "current date", "date is",
            "weather", "temperature", "how's the weather"
        ]
        if action == "provide_information":
            for info_request in information_requests:
                if info_request in text_lower:
                    print(f"HOTKEY MODE: Information request '{info_request}' completed - ending")
                    return True
        
        # THIRD: Check for questions that need clarification or project/app selection
        if any(phrase in text_lower for phrase in [
            "list my projects", "show my projects", "my projects", "project list", "show projects", "what projects",
            "list apps", "show apps", "available apps", "open project", "which project"
        ]):
            print("HOTKEY MODE: Detected project/app query - continuing for selection")
            return False
        
        # FOURTH: Check for greetings - these should continue conversation
        # Be more specific with greeting detection to avoid false positives
        greeting_patterns = [
            "^hi$", "^hello$", "^hey$", "^good morning", "^good afternoon", "^good evening",
            "how are you", "how r u", "how's it going", "what's up", "whats up"
        ]
        import re
        for pattern in greeting_patterns:
            if re.search(pattern, text_lower):
                print(f"HOTKEY MODE: Detected greeting pattern '{pattern}' - continuing conversation")
                return False
        
        # For conversational responses that don't fall into completed categories, continue
        if action == "provide_information" and len(text.strip()) > 5:
            # This is a conversational response, not a simple info request
            print("HOTKEY MODE: Conversational response - continuing")
            return False
        
        # Default: if unclear, continue conversation (safer)
        print("HOTKEY MODE: Unclear command type - continuing conversation to be safe")
        return False
    
    def _schedule_proactive_suggestions(self, user_text: str):
        """Schedule proactive suggestions to be delivered after a delay"""
        import threading
        import time
        
        def delayed_suggestions():
            # Wait 3 seconds to allow current response to complete
            time.sleep(3)
            
            # Only provide suggestions if conversation is still active
            if self.conversation_active:
                try:
                    # Use the command dispatcher's proactive suggestion system
                    self.command_dispatcher.provide_proactive_suggestions(user_text)
                except Exception as e:
                    logging.error(f"Error providing proactive suggestions: {e}")
        
        # Start the delayed suggestion thread
        threading.Thread(target=delayed_suggestions, daemon=True).start()
    
    def _launch_app_from_dashboard(self, app_name: str) -> bool:
        """Launch an application from dashboard action"""
        try:
            import subprocess
            import os
            
            # Map app names to executables
            app_mapping = {
                "Google Chrome": "chrome",
                "Microsoft Edge": "msedge", 
                "Firefox": "firefox",
                "Visual Studio Code": "code",
                "Notepad": "notepad",
                "Calculator": "calc",
                "File Explorer": "explorer",
                "Command Prompt": "cmd",
                "PowerShell": "powershell",
                "Paint": "mspaint"
            }
            
            executable = app_mapping.get(app_name, app_name.lower().replace(" ", ""))
            
            if os.name == 'nt':  # Windows
                subprocess.Popen(f"start {executable}", shell=True)
            else:  # Unix-like
                subprocess.Popen(executable, shell=True)
            
            return True
            
        except Exception as e:
            logging.error(f"Error launching app {app_name}: {e}")
            return False
    
    def _open_project_in_vscode(self, project_path: str) -> bool:
        """Open a project in VSCode"""
        try:
            import subprocess
            import os
            
            # Try different VSCode commands
            vscode_commands = [
                'code',  # Standard command
                'code.cmd',  # Windows
                'code.exe',  # Windows
                r'C:\Users\{}\AppData\Local\Programs\Microsoft VS Code\Code.exe'.format(os.environ.get('USERNAME', '')),
                r'C:\Program Files\Microsoft VS Code\Code.exe',
                r'C:\Program Files (x86)\Microsoft VS Code\Code.exe'
            ]
            
            for cmd in vscode_commands:
                try:
                    # Use shell=True for Windows compatibility
                    result = subprocess.run(f'"{cmd}" "{project_path}"', 
                                           shell=True,
                                           capture_output=True, 
                                           text=True, 
                                           timeout=10)
                    
                    if result.returncode == 0:
                        logging.info(f"Successfully opened {project_path} in VSCode using {cmd}")
                        return True
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    continue
                except Exception as e:
                    logging.error(f"Error trying {cmd}: {e}")
                    continue
            
            # If VSCode not found, try to open in file explorer as fallback
            logging.warning("VSCode not found, opening in file explorer instead")
            try:
                if os.name == 'nt':  # Windows
                    subprocess.Popen(f'explorer "{project_path}"', shell=True)
                    return True
            except Exception as e:
                logging.error(f"Error opening file explorer: {e}")
            
            return False
                
        except Exception as e:
            logging.error(f"Error opening VSCode: {e}")
            return False
    
    def _create_new_project_from_dashboard(self) -> bool:
        """Create a new project from dashboard button"""
        try:
            # Use the command dispatcher's method
            return self.command_dispatcher._create_new_project("G:\\GitHub")
        except Exception as e:
            logging.error(f"Error creating new project: {e}")
            return False
    
    def _open_github_folder(self) -> bool:
        """Open the GitHub folder in file explorer"""
        try:
            import subprocess
            import os
            
            github_path = "G:\\GitHub"
            if not os.path.exists(github_path):
                os.makedirs(github_path)
            
            if os.name == 'nt':  # Windows
                subprocess.Popen(f'explorer "{github_path}"', shell=True)
            else:  # Unix-like
                subprocess.Popen(f'xdg-open "{github_path}"', shell=True)
            
            return True
            
        except Exception as e:
            logging.error(f"Error opening GitHub folder: {e}")
            return False
    
    def _is_verification_response(self, text: str) -> bool:
        """Check if the text is a verification response (yes/no/confirm/cancel)
        
        Args:
            text: User's message text
            
        Returns:
            bool: True if this is a verification response
        """
        text_lower = text.lower().strip()
        
        verification_keywords = [
            # Positive responses
            "yes", "confirm", "ok", "okay", "proceed", "do it", "go ahead", 
            "execute", "run it", "sure", "yep", "yeah", "affirmative", 
            "correct", "right", "that's right", "approve",
            
            # Negative responses
            "no", "cancel", "abort", "never mind", "stop", "don't", 
            "negative", "nope", "reject", "decline", "deny",
            
            # Time modification responses
            "change to", "make it", "modify"
        ]
        
        return any(keyword in text_lower for keyword in verification_keywords)
    
    def _get_contextual_follow_up(self):
        """Get a contextual follow-up message based on conversation state"""
        follow_up_messages = [
            "Anything else I can help you with?",
            "Is there something else you need?", 
            "What else can I do for you?",
            "Need help with anything else?",
            "Anything else on your mind?"
        ]
        
        return random.choice(follow_up_messages)
    
    def set_pending_action(self, action_type: str, context: dict, question: str):
        """Set a pending action that requires user input"""
        self.pending_action = {
            "type": action_type,
            "context": context,
            "question": question,
            "timestamp": time.time()
        }
        self.conversation_context = context
        logging.info(f"Set pending action: {action_type} - {question}")

    def handle_pending_action_response(self, user_response: str) -> bool:
        """Handle user response to a pending action question"""
        try:
            if not self.pending_action:
                return False
            
            action_type = self.pending_action["type"]
            context = self.pending_action["context"]
            
            logging.info(f"Handling pending action response: {action_type} - '{user_response}'")
            
            if action_type == "project_selection":
                return self._handle_project_selection(user_response, context)
            elif action_type == "app_selection":
                return self._handle_app_selection(user_response, context)
            elif action_type == "project_creation":
                return self._handle_project_creation_name(user_response, context)
            elif action_type == "clarification":
                return self._handle_clarification_response(user_response, context)
            
            return False
            
        except Exception as e:
            logging.error(f"Error handling pending action response: {e}")
            return False
        finally:
            # Clear pending action after handling
            self.clear_pending_action()

    def clear_pending_action(self):
        """Clear any pending action"""
        self.pending_action = None
        self.conversation_context = {}
        logging.info("Cleared pending action")

    def _handle_project_selection(self, project_name: str, context: dict) -> bool:
        """Handle project selection response"""
        try:
            github_path = context.get("github_path", "G:\\GitHub")
            
            # Find matching project
            if not os.path.exists(github_path):
                self._emit_ai_message("GitHub folder doesn't exist. Let me create it for you.", "response")
                self.voice_system.speak("GitHub folder doesn't exist. Let me create it for you.")
                return False
            
            projects = []
            for item in os.listdir(github_path):
                item_path = os.path.join(github_path, item)
                if os.path.isdir(item_path):
                    projects.append({"name": item, "path": item_path})
            
            # Find best match
            project_name_lower = project_name.lower().strip()
            matched_project = None
            
            # Exact match first
            for project in projects:
                if project["name"].lower() == project_name_lower:
                    matched_project = project
                    break
            
            # Partial match if no exact match
            if not matched_project:
                for project in projects:
                    if project_name_lower in project["name"].lower() or project["name"].lower().startswith(project_name_lower):
                        matched_project = project
                        break
            
            if matched_project:
                # Open project in VSCode
                success = self._open_project_in_vscode(matched_project["path"])
                if success:
                    response = f"Opening {matched_project['name']} in VSCode!"
                    self._emit_ai_message(response, "response")
                    self.voice_system.speak(response)
                    return True
                else:
                    response = f"Found {matched_project['name']} but couldn't open it in VSCode."
                    self._emit_ai_message(response, "error")
                    self.voice_system.speak(response)
                    return False
            else:
                # No match found - suggest creating new project
                response = f"I couldn't find a project named '{project_name}'. Would you like me to create a new project with that name?"
                self._emit_ai_message(response, "response")
                self.voice_system.speak(response)
                
                # Set new pending action for project creation
                self.set_pending_action("project_creation_confirm", {
                    "project_name": project_name,
                    "github_path": github_path
                }, f"Create new project '{project_name}'?")
                return True
                
        except Exception as e:
            logging.error(f"Error handling project selection: {e}")
            return False

    def _handle_app_selection(self, app_name: str, context: dict) -> bool:
        """Handle app selection response"""
        try:
            # Use the command dispatcher's intelligent app control functionality
            parameters = {
                "app_name": app_name.lower().strip(),
                "operation": "launch",
                "original_query": f"open {app_name}"
            }
            
            success = self.command_dispatcher._handle_app_control(parameters)
            
            # Provide voice feedback
            if success:
                self.voice_system.speak(f"I've launched {app_name} for you.")
            else:
                self.voice_system.speak(f"I couldn't launch {app_name}. Please check if it's properly installed.")
            
            return success
            
        except Exception as e:
            logging.error(f"Error handling app selection: {e}")
            return False

    def _handle_project_creation_name(self, project_name: str, context: dict) -> bool:
        """Handle project creation with specified name"""
        try:
            github_path = context.get("github_path", "G:\\GitHub")
            
            # Ensure GitHub folder exists
            if not os.path.exists(github_path):
                os.makedirs(github_path)
            
            # Create project with specified name
            project_path = os.path.join(github_path, project_name.strip())
            
            if os.path.exists(project_path):
                response = f"Project '{project_name}' already exists. Want me to open it instead?"
                self._emit_ai_message(response, "response")
                self.voice_system.speak(response)
                return True
            
            # Create project folder and files
            os.makedirs(project_path)
            
            # Create basic files
            readme_content = f"""# {project_name}

A new project created by Aiden AI Assistant.

## Getting Started

Add your project description here.

Created on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
            
            with open(os.path.join(project_path, "README.md"), "w") as f:
                f.write(readme_content)
            
            # Open in VSCode
            success = self._open_project_in_vscode(project_path)
            
            if success:
                response = f"Created project '{project_name}' and opened it in VSCode!"
                self._emit_ai_message(response, "response")
                self.voice_system.speak(response)
                return True
            else:
                response = f"Created project '{project_name}' but couldn't open VSCode."
                self._emit_ai_message(response, "response")
                self.voice_system.speak(response)
                return True
                
        except Exception as e:
            logging.error(f"Error handling project creation: {e}")
            return False

    def _handle_clarification_response(self, response: str, context: dict) -> bool:
        """Handle clarification response"""
        try:
            original_query = context.get("original_query", "")
            
            # Process the clarified command
            clarified_query = f"{original_query} {response}"
            
            # Process as new command
            command = self.llm_connector.process_command(clarified_query)
            
            # Record the interaction
            self.config_manager.record_interaction(
                command["action"],
                clarified_query,
                command["parameters"]
            )
            
            # Dispatch the command
            success = self.command_dispatcher.dispatch(command)
            return success
            
        except Exception as e:
            logging.error(f"Error handling clarification response: {e}")
            return False
    
    def _get_conversation_suggestions(self):
        """Generate personalized conversation suggestions based on user history and context"""
        try:
            user_profile = self.config_manager.get_user_profile()
            interactions = user_profile.get("history", {}).get("interactions", [])
            total_sessions = user_profile.get("history", {}).get("total_sessions", 0)
            
            suggestions = []
            
            # Analyze recent interactions for context
            recent_interactions = interactions[-10:] if len(interactions) > 10 else interactions
            
            # Check for recent coding activity
            has_recent_coding = any(
                any(app in i.get("text", "").lower() for app in ["vscode", "code", "python", "javascript", "programming"]) 
                for i in recent_interactions
            )
            
            # Check for recent fan usage
            has_recent_fan = any(i.get("type") == "fan_control" for i in recent_interactions)
            
            # Check time of day for context
            import datetime
            current_hour = datetime.datetime.now().hour
            
            if current_hour < 12:
                time_context = "morning"
            elif current_hour < 17:
                time_context = "afternoon"
            else:
                time_context = "evening"
            
            # Generate suggestions based on patterns
            if total_sessions < 3:
                # New user suggestions
                suggestions.extend([
                    {"text": "Ask me to open VSCode", "category": "Getting Started"},
                    {"text": "What can you do?", "category": "Exploration"},
                    {"text": "Turn on the fan", "category": "Smart Home"},
                    {"text": "What's the weather like?", "category": "Information"}
                ])
            
            elif has_recent_coding:
                # Coding-focused suggestions
                suggestions.extend([
                    {"text": "Help me create a new Python project", "category": "Coding"},
                    {"text": "Find JavaScript tutorials", "category": "Learning"},
                    {"text": "Open my development environment", "category": "Productivity"},
                    {"text": "Search for React documentation", "category": "Research"}
                ])
            
            elif has_recent_fan:
                # Smart home focused
                suggestions.extend([
                    {"text": "Set up fan automation", "category": "Smart Home"},
                    {"text": "Create voice shortcuts for fan control", "category": "Automation"},
                    {"text": "Check ESP32 status", "category": "Diagnostics"}
                ])
            
            # Time-based suggestions
            if time_context == "morning":
                suggestions.extend([
                    {"text": "What's on my agenda today?", "category": "Planning"},
                    {"text": "Open my project folders", "category": "Productivity"},
                    {"text": "Check the news", "category": "Information"}
                ])
            elif time_context == "afternoon":
                suggestions.extend([
                    {"text": "Help me organize my files", "category": "Productivity"},
                    {"text": "Find some coding tutorials", "category": "Learning"},
                    {"text": "What's a good project to work on?", "category": "Ideas"}
                ])
            else:  # evening
                suggestions.extend([
                    {"text": "Show me something interesting to learn", "category": "Learning"},
                    {"text": "What technology should I explore?", "category": "Exploration"},
                    {"text": "Help me plan tomorrow's work", "category": "Planning"}
                ])
            
            # Always include some general suggestions
            suggestions.extend([
                {"text": "Who is your owner?", "category": "About Aiden"},
                {"text": "Open my browser", "category": "Applications"},
                {"text": "What's the current time?", "category": "Information"},
                {"text": "Search for something interesting", "category": "Exploration"}
            ])
            
            # Remove duplicates and limit to 8 suggestions
            seen = set()
            unique_suggestions = []
            for suggestion in suggestions:
                if suggestion["text"] not in seen:
                    seen.add(suggestion["text"])
                    unique_suggestions.append(suggestion)
                    if len(unique_suggestions) >= 8:
                        break
            
            return unique_suggestions
            
        except Exception as e:
            logging.error(f"Error generating conversation suggestions: {e}")
            # Return default suggestions on error
            return [
                {"text": "What can you do?", "category": "Getting Started"},
                {"text": "Open VSCode", "category": "Applications"},
                {"text": "What's the time?", "category": "Information"},
                {"text": "Turn on the fan", "category": "Smart Home"}
            ]

    def _ask_for_follow_up(self):
        """Ask for follow-up and handle response with smart timeout handling"""
        time.sleep(1)
        
        # Update status to speaking
        self.socketio.emit('voice_status', {
            'listening': False,
            'conversation_active': True,
            'speaking': True,
            'status': 'speaking'
        })
        
        # Generate context-aware follow-up message
        follow_up_msg = self._get_contextual_follow_up()
        self._emit_ai_message(follow_up_msg, "follow_up")
        self.voice_system.speak(follow_up_msg)
        
        # Update status to listening for follow-up
        self.socketio.emit('voice_status', {
            'listening': True,
            'conversation_active': True,
            'speaking': False,
            'status': 'listening'
        })
        
        # Play ready sound for follow-up
        self.voice_system.play_ready_sound()
        
        # Listen for response with shorter timeout for follow-up
        success, response, error = self.stt_system.listen()
        
        if success and response:
            response = response.lower()
            self._emit_user_message(response, "voice")
            
            # Check if user wants to continue
            if any(word in response for word in ["no", "nope", "stop", "end", "finish", "that's all", "thanks"]):
                self.conversation_active = False
                goodbye_msg = "Alright! I'll be here if you need me."
                self._emit_ai_message(goodbye_msg, "goodbye")
                self.voice_system.speak(goodbye_msg)
            elif any(word in response for word in ["yes", "yeah", "sure", "okay"]):
                continue_msg = "What can I help you with?"
                self._emit_ai_message(continue_msg, "follow_up")
                self.voice_system.speak(continue_msg)
            else:
                # Treat as new command
                self._process_message_common(response)
        elif error == "timeout":
            # User didn't respond to follow-up - end conversation gracefully and silently
            print("Follow-up timeout - ending conversation silently")
            self.conversation_active = False
            # Don't show any error message or response for follow-up timeouts
        else:
            # Other error during follow-up - end conversation
            print(f"Follow-up error: {error}")
            self.conversation_active = False
    
    def _emit_user_message(self, text: str, input_type: str):
        """Emit user message to all clients"""
        message = {
            'id': len(self.current_conversation) + 1,
            'type': 'user',
            'text': text,
            'input_type': input_type,
            'timestamp': datetime.now().isoformat()
        }
        self.current_conversation.append(message)
        self.socketio.emit('new_message', message)
    
    def _emit_ai_message(self, text: str, message_type: str):
        """Emit AI message to all clients"""
        # Add debug logging for verification prompts
        if message_type == 'action_card' and isinstance(text, dict) and text.get('type') == 'verification_prompt':
            print(f"DEBUG: Emitting verification prompt with options: {text.get('options', [])}")
            print(f"DEBUG: Full verification prompt: {text}")
        
        # Skip sending duplicate messages
        if hasattr(self, '_last_ai_message') and self._last_ai_message:
            # Check if the message is substantially the same
            if isinstance(text, str) and isinstance(self._last_ai_message, str):
                # For string messages, check content similarity
                if text == self._last_ai_message and message_type != "system":
                    print("Skipping duplicate AI message")
                    return
            elif isinstance(text, dict) and isinstance(self._last_ai_message, dict):
                # For action cards, check if they're the same type with same key fields
                if (text.get('type') == self._last_ai_message.get('type') and 
                    text.get('message') == self._last_ai_message.get('message') and
                    text.get('message_id') == self._last_ai_message.get('message_id')):
                    print(f"Skipping duplicate action card: {text.get('type')} - {text.get('message_id')}")
                    return
        
        # Save this message for deduplication
        self._last_ai_message = text
        
        # Create and emit the message
        message = {
            'id': len(self.current_conversation) + 1,
            'type': 'ai',
            'text': text,
            'message_type': message_type,
            'timestamp': datetime.now().isoformat()
        }
        self.current_conversation.append(message)
        self.socketio.emit('new_message', message)
    
    def _reload_components(self):
        """Reload components with new configuration"""
        try:
            # Reload voice system safely
            try:
                self.voice_system = VoiceSystem(self.config_manager)
                print("Voice system reloaded successfully")
            except Exception as e:
                print(f"Warning: Could not reload voice system: {e}")
            
            # Reload ESP32 controller safely
            try:
                self.esp32_controller = ESP32Controller(self.config_manager)
                print("ESP32 controller reloaded successfully")
            except Exception as e:
                print(f"Warning: Could not reload ESP32 controller: {e}")
            
            # Reload command dispatcher safely
            try:
                self.command_dispatcher = CommandDispatcher(
                    self.config_manager, 
                    self.voice_system, 
                    dashboard_backend=self
                )
                print("Command dispatcher reloaded successfully")
            except Exception as e:
                print(f"Warning: Could not reload command dispatcher: {e}")
            
            print("Component reload completed (some components may have warnings)")
        except Exception as e:
            print(f"Error during component reload: {e}")
            # Don't raise the exception - just log it and continue
    
    def run(self, host='localhost', port=5000, debug=False):
        """Run the Flask application"""
        print(f"Starting Aiden Dashboard Backend on http://{host}:{port}")
        self.socketio.run(self.app, host=host, port=port, debug=debug)

def main():
    """Main entry point"""
    backend = AidenDashboardBackend()
    
    try:
        backend.run(host='0.0.0.0', port=5000, debug=True)
    except KeyboardInterrupt:
        print("\nShutting down Aiden Dashboard Backend...")
    except Exception as e:
        print(f"Error running backend: {e}")

if __name__ == '__main__':
    main()