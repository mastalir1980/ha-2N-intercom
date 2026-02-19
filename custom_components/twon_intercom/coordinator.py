"""DataUpdateCoordinator for 2N Intercom."""
from __future__ import annotations

from datetime import timedelta, datetime
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import TwoNIntercomAPI
from .const import DOMAIN, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class TwoNIntercomCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage data updates from 2N Intercom."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: TwoNIntercomAPI,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self._last_call_state: dict[str, Any] = {}
        self._ring_detected = False
        self._last_ring_time: datetime | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            # Get current call status
            call_status = await self.api.async_get_call_status()
            
            # Detect ring events
            current_state = call_status.get("state", "idle")
            previous_state = self._last_call_state.get("state", "idle")
            
            # Ring detection: state changes to "ringing"
            if current_state == "ringing" and previous_state != "ringing":
                self._ring_detected = True
                self._last_ring_time = datetime.now()
                _LOGGER.info("Doorbell ring detected")
            elif current_state != "ringing":
                # Reset ring detection when call ends
                if self._ring_detected and (
                    self._last_ring_time is None
                    or (datetime.now() - self._last_ring_time).total_seconds() > 30
                ):
                    self._ring_detected = False
            
            self._last_call_state = call_status
            
            return {
                "call_status": call_status,
                "ring_active": self._ring_detected,
                "last_ring_time": self._last_ring_time,
                "caller_info": call_status.get("caller", {}),
                "available": True,
            }
            
        except Exception as err:
            _LOGGER.error("Error updating data: %s", err)
            raise UpdateFailed(f"Error communicating with device: {err}") from err

    @property
    def ring_active(self) -> bool:
        """Return if doorbell is currently ringing."""
        if self.data:
            return self.data.get("ring_active", False)
        return False

    @property
    def last_ring_time(self) -> datetime | None:
        """Return last ring timestamp."""
        if self.data:
            return self.data.get("last_ring_time")
        return None

    @property
    def caller_info(self) -> dict[str, Any]:
        """Return caller information."""
        if self.data:
            return self.data.get("caller_info", {})
        return {}

    async def async_trigger_relay(
        self, relay: int, duration: int = 2000
    ) -> bool:
        """
        Trigger a relay.
        
        Args:
            relay: Relay number (1-4)
            duration: Pulse duration in milliseconds
            
        Returns:
            True if successful
        """
        try:
            success = await self.api.async_switch_control(
                relay=relay,
                action="trigger",
                duration=duration,
            )
            
            if success:
                _LOGGER.info("Relay %s triggered successfully", relay)
            else:
                _LOGGER.warning("Failed to trigger relay %s", relay)
                
            return success
            
        except Exception as err:
            _LOGGER.error("Error triggering relay %s: %s", relay, err)
            return False

    async def async_get_snapshot(self) -> bytes | None:
        """Get camera snapshot."""
        try:
            return await self.api.async_get_snapshot()
        except Exception as err:
            _LOGGER.error("Error getting snapshot: %s", err)
            return None
