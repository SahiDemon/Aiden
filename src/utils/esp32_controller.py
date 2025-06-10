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
        self.ip_address = self.esp32_config.get("ip_address", "192.168.1.6")
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
        """Set fan to speed 2 (same as turn_on)
        
        Returns:
            True if successful, False otherwise
        """
        return self.turn_on()
    
    def set_speed_3(self) -> bool:
        """Set fan to speed 3 (same as turn_on)
        
        Returns:
            True if successful, False otherwise
        """
        return self.turn_on()
    
    def change_speed(self) -> bool:
        """Change fan speed by cycling through available speeds
        
        Returns:
            True if successful, False otherwise
        """
        # Since the ESP32 currently doesn't support speed cycling directly,
        # we'll just turn it on which will maintain its current speed or start at default
        return self._send_command("on")

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
