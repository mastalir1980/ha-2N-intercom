"""DataUpdateCoordinator for the 2N Intercom integration."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

import aiohttp
from aiohttp import BasicAuth

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_CALL_STATUS,
    API_CAMERA_SNAPSHOT,
    API_STATUS,
    API_SWITCH_CAPS,
    API_SWITCH_CTRL,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class TwoNIntercomCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching 2N Intercom data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.host = entry.data[CONF_HOST]
        self.username = entry.data.get(CONF_USERNAME)
        self.password = entry.data.get(CONF_PASSWORD)
        
        # Get poll interval from config or use default
        poll_interval = entry.options.get(
            CONF_POLL_INTERVAL, 
            entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        )
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=poll_interval),
        )
        
        self._session = async_get_clientsession(hass)
        self._base_url = f"http://{self.host}"
        self._auth = None
        if self.username and self.password:
            self._auth = BasicAuth(self.username, self.password)
    
    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the 2N intercom device."""
        _LOGGER.debug("Updating 2N Intercom data from %s", self.host)
        
        try:
            data = {}
            
            # Fetch system status
            status = await self._api_request(API_STATUS)
            if status:
                data["status"] = status
            
            # Fetch switch capabilities
            switch_caps = await self._api_request(API_SWITCH_CAPS)
            if switch_caps:
                data["switch_caps"] = switch_caps
            
            # Fetch call status
            call_status = await self._api_request(API_CALL_STATUS)
            if call_status:
                data["call_status"] = call_status
            
            _LOGGER.debug("Successfully updated data: %s", data)
            return data
            
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with device: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error updating data: {err}") from err
    
    async def _api_request(self, endpoint: str) -> dict[str, Any] | None:
        """Make an API request to the 2N device."""
        url = f"{self._base_url}{endpoint}"
        
        try:
            async with self._session.get(
                url,
                auth=self._auth,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as err:
            if err.status == 404:
                _LOGGER.debug("Endpoint %s not found (404), skipping", endpoint)
                return None
            _LOGGER.error("HTTP error %s for %s: %s", err.status, url, err)
            raise
        except aiohttp.ClientError as err:
            _LOGGER.error("Client error for %s: %s", url, err)
            raise
    
    async def async_switch_control(
        self, switch_type: str, state: bool
    ) -> dict[str, Any] | None:
        """Control a switch on the 2N device."""
        url = f"{self._base_url}{API_SWITCH_CTRL}"
        
        payload = {
            "switch": switch_type,
            "state": state,
        }
        
        try:
            async with self._session.post(
                url,
                json=payload,
                auth=self._auth,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as err:
            _LOGGER.error("Error controlling switch %s: %s", switch_type, err)
            raise
    
    async def async_get_snapshot(self) -> bytes | None:
        """Get a camera snapshot from the 2N device."""
        url = f"{self._base_url}{API_CAMERA_SNAPSHOT}"
        
        try:
            async with self._session.get(
                url,
                auth=self._auth,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as response:
                response.raise_for_status()
                return await response.read()
        except aiohttp.ClientError as err:
            _LOGGER.error("Error getting snapshot: %s", err)
            return None
