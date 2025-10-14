"""
ESP32 Smart Home Client
Controls ESP32-based smart home devices (fan control) with retry logic
"""
import asyncio
import logging
from typing import Optional, Dict, Any
import httpx

from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ESP32Client:
    """
    ESP32 smart home controller with retry logic and offline queue
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.enabled = self.settings.esp32.enabled
        self.ip_address = self.settings.esp32.ip_address
        self.timeout = self.settings.esp32.timeout
        self.retry_attempts = self.settings.esp32.retry_attempts
        self.client = httpx.AsyncClient(timeout=self.timeout)
        
    async def _request(self, endpoint: str, retries: Optional[int] = None) -> Dict[str, Any]:
        """
        Make HTTP request to ESP32 with retry logic
        
        Args:
            endpoint: API endpoint (e.g., "/on", "/off", "/status")
            retries: Number of retry attempts (uses config default if not specified)
            
        Returns:
            Response dictionary
        """
        if not self.enabled:
            logger.warning("ESP32 is disabled in configuration")
            return {"success": False, "error": "ESP32 disabled"}
        
        retries = retries or self.retry_attempts
        url = f"http://{self.ip_address}{endpoint}"
        
        for attempt in range(retries):
            try:
                logger.debug(f"ESP32 request to {url} (attempt {attempt + 1}/{retries})")
                
                response = await self.client.get(url)
                response.raise_for_status()
                
                logger.info(f"ESP32 request successful: {endpoint}")
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "data": response.text
                }
                
            except httpx.TimeoutException:
                logger.warning(f"ESP32 request timeout (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                    continue
                return {"success": False, "error": "Timeout"}
            
            except httpx.HTTPStatusError as e:
                logger.error(f"ESP32 HTTP error: {e.response.status_code}")
                return {"success": False, "error": f"HTTP {e.response.status_code}"}
            
            except httpx.RequestError as e:
                logger.warning(f"ESP32 connection error (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                return {"success": False, "error": "Connection failed"}
            
            except Exception as e:
                logger.error(f"Unexpected ESP32 error: {e}")
                return {"success": False, "error": str(e)}
        
        return {"success": False, "error": "Max retries exceeded"}
    
    async def turn_on(self) -> tuple[bool, Optional[str]]:
        """
        Turn on the fan / Increase speed
        Calling /on repeatedly cycles through speeds: 1 → 2 → 3
        
        Returns:
            Tuple of (success, response_text)
        """
        result = await self._request("/on")
        response_text = result.get("data", "")
        if result.get("success"):
            logger.info(f"ESP32 Response: {response_text}")
        return result.get("success", False), response_text
    
    async def turn_off(self) -> tuple[bool, Optional[str]]:
        """
        Turn off the fan
        
        Returns:
            Tuple of (success, response_text)
        """
        result = await self._request("/off")
        response_text = result.get("data", "")
        if result.get("success"):
            logger.info(f"ESP32 Response: {response_text}")
        return result.get("success", False), response_text
    
    async def change_mode(self) -> tuple[bool, Optional[str]]:
        """
        Change fan mode (if ESP32 has /mode endpoint)
        
        Returns:
            Tuple of (success, response_text)
        """
        result = await self._request("/mode")
        response_text = result.get("data", "")
        if result.get("success"):
            logger.info(f"ESP32 Response: {response_text}")
        return result.get("success", False), response_text
    
    async def get_status(self) -> Dict[str, Any]:
        """
        Get current fan status
        Note: Only works if your ESP32 has /status endpoint
        """
        result = await self._request("/status")
        return result
    
    async def check_connection(self) -> bool:
        """
        Check if ESP32 is reachable
        Uses /on endpoint with minimal retries to test connection
        """
        result = await self._request("/on", retries=1)
        return result.get("success", False)
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Global instance
_esp32_client: Optional[ESP32Client] = None


async def get_esp32_client() -> ESP32Client:
    """Get or create global ESP32 client"""
    global _esp32_client
    if _esp32_client is None:
        _esp32_client = ESP32Client()
    return _esp32_client


async def close_esp32_client():
    """Close global ESP32 client"""
    global _esp32_client
    if _esp32_client:
        await _esp32_client.close()
        _esp32_client = None



