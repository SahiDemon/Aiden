"""
ESP32 Controller for Aiden
Handles communication with ESP32 device for fan control
"""
import requests
import logging
from typing import Dict, Any, Optional

class ESP32Controller:
    """Controller for ESP32-based fan device"""
    
    def __init__(self, config_manager):
        """Initialize the ESP32 controller
        
        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager
        
        # Get ESP32 configuration or use default
        general_config = config_manager.get_config("general")
        self.esp32_config = general_config.get("esp32", {})
        
        # Set ESP32 IP address (default or from config)
        self.ip_address = self.esp32_config.get("ip_address", "192.168.1.180")
        self.base_url = f"http://{self.ip_address}"
        
        logging.info(f"ESP32 controller initialized with IP: {self.ip_address}")
    
    def _send_command(self, command_path: str) -> bool:
        """Send a command to the ESP32 server
        
        Args:
            command_path: The path part of the URL (e.g., "on", "off")
            
        Returns:
            True if command was sent successfully, False otherwise
        """
        try:
            url = f"{self.base_url}/{command_path}"
            logging.info(f"Sending command to ESP32: {url}")
            
            # Set a timeout to prevent hanging
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                logging.info(f"ESP32 command successful: {response.text}")
                return True
            else:
                logging.error(f"ESP32 error: status code {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            logging.error(f"ESP32 connection error: {e}")
            return False
    
    def turn_on(self) -> bool:
        """Turn the fan on at any speed
        
        Returns:
            True if successful, False otherwise
        """
        return self._send_command("on")
    
    def turn_off(self) -> bool:
        """Turn the fan off
        
        Returns:
            True if successful, False otherwise
        """
        return self._send_command("off")
    
    def change_mode(self) -> bool:
        """Change the fan mode
        
        Returns:
            True if successful, False otherwise
        """
        return self._send_command("mode")
    
    # These functions are for backward compatibility but all call the same turn_on method
    # since the ESP32 now uses a single command for all speeds
    def set_speed_1(self) -> bool:
        """Set fan to speed 1 (same as turn_on)
        
        Returns:
            True if successful, False otherwise
        """
        return self.turn_on()
    
    def set_speed_2(self) -> bool:
        """Set fan to speed 2
        
        Returns:
            True if successful, False otherwise
        """
        return self._send_command("speed2")
    
    def set_speed_3(self) -> bool:
        """Set fan to speed 3
        
        Returns:
            True if successful, False otherwise
        """
        return self._send_command("speed3")
    
    def set_speed(self, speed: int) -> bool:
        """Set fan to specific speed
        
        Args:
            speed: Speed level (1, 2, or 3)
            
        Returns:
            True if successful, False otherwise
        """
        if speed == 1:
            return self.turn_on()  # /on endpoint for speed 1
        elif speed == 2:
            return self.set_speed_2()  # /speed2 endpoint
        elif speed == 3:
            return self.set_speed_3()  # /speed3 endpoint
        else:
            logging.error(f"Invalid speed level: {speed}. Must be 1, 2, or 3")
            return False
    
    def cycle_speed(self) -> bool:
        """Intelligently cycle through fan speeds using /on endpoint
        
        The /on endpoint automatically increments speed based on current state:
        - Off → Speed 1
        - Speed 1 → Speed 2  
        - Speed 2 → Speed 3
        - Speed 3 → Speed 1 (cycles back)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get current status for logging purposes
            status_info = self.get_status()
            
            if status_info['success']:
                current_state = status_info['parsed']['state']
                current_speed = status_info['parsed']['speed']
                logging.info(f"Current fan state: {current_state}, speed: {current_speed}")
                
                if current_state == 'off':
                    logging.info("Fan is off, /on will turn on at speed 1")
                elif current_speed == '1':
                    logging.info("Fan at speed 1, /on will increase to speed 2")
                elif current_speed == '2':
                    logging.info("Fan at speed 2, /on will increase to speed 3")
                elif current_speed == '3':
                    logging.info("Fan at speed 3, /on will cycle back to speed 1")
                else:
                    logging.info(f"Fan state: {current_state}, /on will handle cycling")
            else:
                logging.warning("Cannot get fan status, but /on will still work")
            
            # Use /on endpoint for intelligent speed cycling
            # The ESP32 handles the logic internally
            return self.turn_on()
                
        except Exception as e:
            logging.error(f"Error in smart speed cycling: {e}")
            # Fallback to /on command
            return self.turn_on()
    
    def get_human_readable_status(self) -> str:
        """Get a human-readable status description
        
        Returns:
            String describing current fan status
        """
        status_info = self.get_status()
        
        if not status_info['success']:
            return f"Unable to connect to fan (IP: {self.ip_address}). Error: {status_info.get('error', 'Unknown error')}"
        
        parsed = status_info['parsed']
        state = parsed['state']
        speed = parsed['speed']
        message = parsed.get('message', '')
        
        if state == 'off':
            return f"Fan is currently OFF. {message}"
        elif state == 'on':
            if speed in ['1', '2', '3']:
                return f"Fan is ON at speed {speed}. {message}"
            elif speed == 'mode_changed':
                return f"Fan is ON and mode was recently changed. {message}"
            else:
                return f"Fan is ON at unknown speed. {message}"
        elif state == 'unknown':
            if 'just started' in message:
                return f"Fan controller just started up. No commands sent yet."
            else:
                return f"Fan status is unknown. {message}"
        else:
            return f"Fan status: {message}"
    
    def get_status(self) -> Dict[str, Any]:
        """Get current fan status from ESP32
        
        Returns:
            Dictionary with current fan status information
        """
        try:
            url = f"{self.base_url}/status"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                status_text = response.text.strip()
                logging.info(f"ESP32 status: {status_text}")
                
                # Parse the status to determine current state
                parsed_status = self._parse_status(status_text)
                return {
                    'success': True,
                    'raw_status': status_text,
                    'parsed': parsed_status
                }
            else:
                logging.error(f"ESP32 status error: status code {response.status_code}")
                return {
                    'success': False,
                    'error': f'HTTP {response.status_code}',
                    'parsed': {'state': 'unknown', 'speed': 'unknown'}
                }
                
        except requests.exceptions.RequestException as e:
            logging.error(f"ESP32 status connection error: {e}")
            return {
                'success': False,
                'error': str(e),
                'parsed': {'state': 'unknown', 'speed': 'unknown'}
            }
    
    def _parse_status(self, status_text: str) -> Dict[str, str]:
        """Parse the status text from ESP32 to extract fan state
        
        Args:
            status_text: Raw status text from ESP32
            
        Returns:
            Dictionary with parsed state and speed information
        """
        status_text = status_text.lower()
        
        if "device just started" in status_text or "no command sent" in status_text:
            return {'state': 'unknown', 'speed': 'unknown', 'message': 'Device just started'}
        elif "power off" in status_text or "off" in status_text:
            return {'state': 'off', 'speed': '0', 'message': 'Fan is off'}
        elif "speed 1" in status_text or "on" in status_text:
            return {'state': 'on', 'speed': '1', 'message': 'Fan on speed 1'}
        elif "speed 2" in status_text:
            return {'state': 'on', 'speed': '2', 'message': 'Fan on speed 2'}
        elif "speed 3" in status_text:
            return {'state': 'on', 'speed': '3', 'message': 'Fan on speed 3'}
        elif "mode change" in status_text:
            return {'state': 'on', 'speed': 'mode_changed', 'message': 'Fan mode changed'}
        else:
            return {'state': 'unknown', 'speed': 'unknown', 'message': f'Unknown status: {status_text}'}

    def check_connection(self) -> bool:
        """Check if ESP32 is reachable without changing fan state
        
        Returns:
            True if ESP32 is reachable, False otherwise
        """
        try:
            # Test 1: Simple GET to root endpoint
            response = requests.get(self.base_url, timeout=3)
            logging.info(f"ESP32 root endpoint test: status {response.status_code}")
            
            # Accept various responses as proof of connectivity
            if response.status_code in [200, 404, 400, 301, 302]:
                logging.info("ESP32 connectivity confirmed via root endpoint")
                return True
            
            # Test 2: Try a known working endpoint (but use HEAD to avoid state change)
            try:
                response = requests.head(f"{self.base_url}/on", timeout=2)
                logging.info(f"ESP32 HEAD test: status {response.status_code}")
                if response.status_code in [200, 404, 400, 405, 501]:  # Various "device exists" responses
                    logging.info("ESP32 connectivity confirmed via HEAD request")
                    return True
            except:
                pass
            
            # Test 3: Final attempt with ping-like approach
            try:
                response = requests.get(f"{self.base_url}/status", timeout=2)
                logging.info(f"ESP32 status endpoint test: status {response.status_code}")
                # Even if status endpoint doesn't exist, device responded
                if response.status_code in [200, 404, 500]:
                    logging.info("ESP32 connectivity confirmed via status endpoint")
                    return True
            except:
                pass
                
            logging.warning("ESP32 connectivity tests failed")
            return False
                
        except requests.exceptions.RequestException as e:
            logging.error(f"ESP32 connection error: {e}")
            return False
    
    def get_detailed_status(self) -> dict:
        """Get detailed status information about ESP32 and fan
        
        Returns:
            Dictionary with detailed status information
        """
        status = {
            'ip_address': self.ip_address,
            'base_url': self.base_url,
            'connected': False,
            'ping_test': False,
            'endpoints_tested': [],
            'error': None
        }
        
        try:
            # Test basic connectivity
            status['connected'] = self.check_connection()
            
            # Test specific endpoints
            endpoints_to_test = ['', '/on', '/off', '/mode', '/status']
            
            for endpoint in endpoints_to_test:
                try:
                    url = f"{self.base_url}{endpoint}"
                    response = requests.head(url, timeout=2)
                    status['endpoints_tested'].append({
                        'endpoint': endpoint or 'root',
                        'status_code': response.status_code,
                        'available': response.status_code < 500
                    })
                except Exception as e:
                    status['endpoints_tested'].append({
                        'endpoint': endpoint or 'root',
                        'status_code': None,
                        'available': False,
                        'error': str(e)
                    })
            
            # Basic ping test (simulated via HTTP)
            try:
                response = requests.get(self.base_url, timeout=1)
                status['ping_test'] = True
            except:
                status['ping_test'] = False
                
        except Exception as e:
            status['error'] = str(e)
            
        return status
