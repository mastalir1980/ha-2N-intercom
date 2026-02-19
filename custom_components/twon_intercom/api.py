"""2N Intercom API Client."""
from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from typing import Any

import aiohttp
import async_timeout

_LOGGER = logging.getLogger(__name__)

API_TIMEOUT = 10


class TwoNIntercomAPI:
    """API client for 2N Intercom."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        protocol: str = "http",
        verify_ssl: bool = True,
    ) -> None:
        """Initialize the API client."""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.protocol = protocol
        self.verify_ssl = verify_ssl
        self._session: aiohttp.ClientSession | None = None
        self._base_url = f"{protocol}://{host}:{port}"

    async def async_get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                auth=aiohttp.BasicAuth(self.username, self.password),
                connector=aiohttp.TCPConnector(ssl=self.verify_ssl),
            )
        return self._session

    async def async_close(self) -> None:
        """Close the API session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def async_test_connection(self) -> bool:
        """Test connection to the intercom."""
        try:
            await self.async_get_call_status()
            return True
        except Exception as err:
            _LOGGER.error("Connection test failed: %s", err)
            return False

    async def async_get_directory(self) -> list[dict[str, Any]]:
        """Get directory entries from /api/dir/query."""
        try:
            session = await self.async_get_session()
            url = f"{self._base_url}/api/dir/query"
            
            async with async_timeout.timeout(API_TIMEOUT):
                async with session.get(url) as response:
                    response.raise_for_status()
                    data = await response.json()
                    
            # Parse directory data
            # Expected format: {"success": true, "result": [...]}
            if isinstance(data, dict) and "result" in data:
                return data["result"]
            return []
            
        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout getting directory: %s", err)
            raise
        except aiohttp.ClientError as err:
            _LOGGER.error("Error getting directory: %s", err)
            raise
        except Exception as err:
            _LOGGER.error("Unexpected error getting directory: %s", err)
            raise

    async def async_get_call_status(self) -> dict[str, Any]:
        """Get current call status from /api/call/status."""
        try:
            session = await self.async_get_session()
            url = f"{self._base_url}/api/call/status"
            
            async with async_timeout.timeout(API_TIMEOUT):
                async with session.get(url) as response:
                    response.raise_for_status()
                    data = await response.json()
                    
            # Expected format: {"success": true, "result": {...}}
            if isinstance(data, dict):
                return data.get("result", {})
            return {}
            
        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout getting call status: %s", err)
            raise
        except aiohttp.ClientError as err:
            _LOGGER.error("Error getting call status: %s", err)
            raise
        except Exception as err:
            _LOGGER.error("Unexpected error getting call status: %s", err)
            raise

    async def async_switch_control(
        self, relay: int, action: str = "on", duration: int = 0
    ) -> bool:
        """
        Control relay via /api/switch/ctrl.
        
        Args:
            relay: Relay number (1-4)
            action: Action to perform ("on", "off", "trigger")
            duration: Duration in milliseconds for trigger action
            
        Returns:
            True if successful, False otherwise
        """
        try:
            session = await self.async_get_session()
            url = f"{self._base_url}/api/switch/ctrl"
            
            params = {
                "switch": relay,
                "action": action,
            }
            
            if duration > 0:
                params["duration"] = duration
            
            async with async_timeout.timeout(API_TIMEOUT):
                async with session.get(url, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
                    
            # Check if action was successful
            if isinstance(data, dict):
                return data.get("success", False)
            return False
            
        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout controlling switch %s: %s", relay, err)
            return False
        except aiohttp.ClientError as err:
            _LOGGER.error("Error controlling switch %s: %s", relay, err)
            return False
        except Exception as err:
            _LOGGER.error("Unexpected error controlling switch %s: %s", relay, err)
            return False

    async def async_get_snapshot(self) -> bytes | None:
        """Get camera snapshot from /api/camera/snapshot."""
        try:
            session = await self.async_get_session()
            url = f"{self._base_url}/api/camera/snapshot"
            
            async with async_timeout.timeout(API_TIMEOUT):
                async with session.get(url) as response:
                    response.raise_for_status()
                    return await response.read()
                    
        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout getting snapshot: %s", err)
            return None
        except aiohttp.ClientError as err:
            _LOGGER.error("Error getting snapshot: %s", err)
            return None
        except Exception as err:
            _LOGGER.error("Unexpected error getting snapshot: %s", err)
            return None

    def get_rtsp_url(self, profile: str = "default") -> str:
        """
        Get RTSP stream URL.
        
        Args:
            profile: Stream profile name (e.g., "default", "high", "low")
            
        Returns:
            RTSP URL with embedded credentials
        """
        # Redact password in logs
        return f"rtsp://{self.username}:****@{self.host}:{self.port}/{profile}"

    def get_rtsp_url_with_credentials(self, profile: str = "default") -> str:
        """
        Get RTSP stream URL with credentials (for actual use).
        
        Args:
            profile: Stream profile name
            
        Returns:
            RTSP URL with embedded credentials
        """
        return f"rtsp://{self.username}:{self.password}@{self.host}:{self.port}/{profile}"


class AuthenticationError(Exception):
    """Authentication failed."""


class ConnectionError(Exception):
    """Connection to intercom failed."""


class APIError(Exception):
    """Generic API error."""
