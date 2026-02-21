"""2N Intercom API Client."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
import logging
from typing import Any

import aiohttp
import async_timeout

_LOGGER = logging.getLogger(__name__)

API_TIMEOUT = 10
RTSP_PATH = "h264_stream"


class TwoNIntercomAPI:
    """API client for 2N Intercom."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 443,
        protocol: str = "https",
        verify_ssl: bool = False,
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
                connector=aiohttp.TCPConnector(ssl=self.verify_ssl),
            )
        return self._session

    def _get_auth(self) -> aiohttp.BasicAuth:
        """Return HTTP BasicAuth for all requests."""
        return aiohttp.BasicAuth(self.username, self.password)

    async def async_close(self) -> None:
        """Close the API session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def async_connect(self) -> bool:
        """
        Establish and validate connection to the intercom.
        
        This method creates a new session and validates connectivity.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Close any existing session first
            await self.async_close()
            
            # Create new session
            await self.async_get_session()
            
            # Test connection by getting call status
            await self.async_get_call_status()
            
            _LOGGER.info("Successfully connected to 2N Intercom at %s", self._base_url)
            return True
            
        except Exception as err:
            _LOGGER.error("Failed to connect to 2N Intercom: %s", err)
            await self.async_close()
            return False

    async def async_reconnect(self) -> bool:
        """
        Force reconnection after error.
        
        Returns:
            True if reconnection successful, False otherwise
        """
        _LOGGER.info("Attempting to reconnect to 2N Intercom")
        return await self.async_connect()

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
                async with session.get(
                    url,
                    auth=self._get_auth(),
                ) as response:
                    # Check for authentication errors
                    if response.status == 401:
                        raise TwoNAuthenticationError(
                            "Authentication failed - invalid credentials"
                        )
                    
                    response.raise_for_status()
                    data = await response.json()
                    
            # Parse directory data
            # Expected format: {"success": true, "result": {...}} or list
            if isinstance(data, dict) and data.get("success") is False:
                _LOGGER.debug("Directory error response=%s", data.get("error"))
                return data

            if isinstance(data, dict) and "result" in data:
                result = data.get("result")
                _LOGGER.debug("Directory response full=%s", data)
                if isinstance(result, dict):
                    users = result.get("users") or []
                    _LOGGER.debug(
                        "Directory result dict users=%s keys=%s",
                        len(users),
                        list(result.keys()),
                    )
                elif isinstance(result, list):
                    _LOGGER.debug(
                        "Directory result list length=%s",
                        len(result),
                    )
                else:
                    _LOGGER.debug(
                        "Directory result type=%s",
                        type(result).__name__,
                    )
                return result or []

            if isinstance(data, dict) and "users" in data:
                users = data.get("users") or []
                _LOGGER.debug("Directory response full=%s", data)
                _LOGGER.debug(
                    "Directory dict users=%s keys=%s",
                    len(users),
                    list(data.keys()),
                )
                return data

            _LOGGER.debug(
                "Directory response type=%s keys=%s",
                type(data).__name__,
                list(data.keys()) if isinstance(data, dict) else None,
            )
            return []
            
        except TwoNAuthenticationError:
            # Re-raise authentication errors
            raise
        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout getting directory: %s", err)
            raise TwoNConnectionError(f"Timeout: {err}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("Error getting directory: %s", err)
            raise TwoNConnectionError(f"Connection error: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error getting directory: %s", err)
            raise TwoNAPIError(f"API error: {err}") from err

    async def async_get_call_status(self) -> dict[str, Any]:
        """Get current call status from /api/call/status."""
        try:
            session = await self.async_get_session()
            url = f"{self._base_url}/api/call/status"
            
            async with async_timeout.timeout(API_TIMEOUT):
                async with session.get(
                    url,
                    auth=self._get_auth(),
                ) as response:
                    # Check for authentication errors
                    if response.status == 401:
                        raise TwoNAuthenticationError(
                            "Authentication failed - invalid credentials"
                        )
                    
                    response.raise_for_status()
                    data = await response.json()
                    
            # Expected format: {"success": true, "result": {...}}
            if isinstance(data, dict):
                return data.get("result", {})
            return {}
            
        except TwoNAuthenticationError:
            # Re-raise authentication errors
            raise
        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout getting call status: %s", err)
            raise TwoNConnectionError(f"Timeout: {err}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("Error getting call status: %s", err)
            raise TwoNConnectionError(f"Connection error: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error getting call status: %s", err)
            raise TwoNAPIError(f"API error: {err}") from err

    async def async_get_system_info(self) -> dict[str, Any]:
        """Get system info from /api/system/info."""
        try:
            session = await self.async_get_session()
            url = f"{self._base_url}/api/system/info"

            async with async_timeout.timeout(API_TIMEOUT):
                async with session.get(
                    url,
                    auth=self._get_auth(),
                ) as response:
                    if response.status == 401:
                        raise TwoNAuthenticationError(
                            "Authentication failed - invalid credentials"
                        )

                    response.raise_for_status()
                    data = await response.json()

            if isinstance(data, dict):
                return data.get("result", {})
            return {}

        except TwoNAuthenticationError:
            raise
        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout getting system info: %s", err)
            raise TwoNConnectionError(f"Timeout: {err}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("Error getting system info: %s", err)
            raise TwoNConnectionError(f"Connection error: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error getting system info: %s", err)
            raise TwoNAPIError(f"API error: {err}") from err

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
                async with session.get(
                    url,
                    params=params,
                    auth=self._get_auth(),
                ) as response:
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

    async def async_get_snapshot(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Get camera snapshot from /api/camera/snapshot."""
        try:
            session = await self.async_get_session()
            url = f"{self._base_url}/api/camera/snapshot"
            params: dict[str, Any] = {"source": "internal"}
            if width is None:
                width = 640
            if height is None:
                height = 480
            params["width"] = width
            params["height"] = height
            
            async with async_timeout.timeout(API_TIMEOUT):
                async with session.get(
                    url,
                    params=params,
                    headers={"Accept": "image/jpeg"},
                    auth=self._get_auth(),
                ) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("Content-Type", "")
                    if "image" not in content_type:
                        error_body = await response.text()
                        request_url = str(response.url)
                        _LOGGER.error(
                            "Snapshot returned non-image content-type: %s body=%s request_url=%s params=%s",
                            content_type,
                            error_body,
                            request_url,
                            params,
                        )

                        error_code = None
                        try:
                            payload = json.loads(error_body)
                            error_code = payload.get("error", {}).get("code")
                        except json.JSONDecodeError:
                            error_code = None

                        if error_code == 12 and (width, height) != (640, 480):
                            _LOGGER.warning(
                                "Retrying snapshot with fallback resolution 640x480 request_url=%s params=%s",
                                request_url,
                                params,
                            )
                            return await self.async_get_snapshot(width=640, height=480)

                        return None
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

    def _get_rtsp_port(self) -> int:
        """Return RTSP port, avoiding HTTP/HTTPS ports."""
        if self.port in (80, 443):
            return 554
        return self.port

    def get_rtsp_url(self) -> str:
        """
        Get RTSP stream URL.
            
        Returns:
            RTSP URL with embedded credentials
        """
        # Redact password in logs
        rtsp_port = self._get_rtsp_port()
        return (
            f"rtsp://{self.username}:****@{self.host}:{rtsp_port}/{RTSP_PATH}"
        )

    def get_rtsp_url_with_credentials(self) -> str:
        """
        Get RTSP stream URL with credentials (for actual use).
            
        Returns:
            RTSP URL with embedded credentials
        """
        rtsp_port = self._get_rtsp_port()
        return (
            f"rtsp://{self.username}:{self.password}@{self.host}:{rtsp_port}/{RTSP_PATH}"
        )


class TwoNAuthenticationError(Exception):
    """Authentication failed."""


class TwoNConnectionError(Exception):
    """Connection to intercom failed."""


class TwoNAPIError(Exception):
    """Generic API error."""
