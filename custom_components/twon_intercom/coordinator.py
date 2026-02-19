"""DataUpdateCoordinator for 2N Intercom."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta, datetime
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import TwoNIntercomAPI, TwoNAuthenticationError, TwoNConnectionError
from .const import DOMAIN, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

# Maximum number of retries before giving up
MAX_RETRIES = 5


@dataclass
class TwoNIntercomData:
    """Data structure for 2N Intercom coordinator."""

    call_status: dict[str, Any]
    last_ring_time: datetime | None
    caller_info: dict[str, Any] | None
    available: bool


class TwoNIntercomCoordinator(DataUpdateCoordinator[TwoNIntercomData]):
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
        self._retry_count = 0
        self._snapshot_cache: bytes | None = None
        self._snapshot_cache_time: datetime | None = None

    async def _async_update_data(self) -> TwoNIntercomData:
        """Fetch data from API."""
        try:
            # Get current call status
            call_status = await self.api.async_get_call_status()
            
            # Reset retry count on successful update
            self._retry_count = 0
            
            # Detect ring events
            current_state = call_status.get("state", "idle")
            previous_state = self._last_call_state.get("state", "idle")
            
            # Ring detection: state changes to "ringing"
            if current_state == "ringing" and previous_state != "ringing":
                self._ring_detected = True
                self._last_ring_time = datetime.now()
                _LOGGER.info("Doorbell ring detected")
            elif current_state != "ringing":
                # Reset ring detection when call ends or timeout (30 seconds)
                if self._ring_detected and (
                    self._last_ring_time is None
                    or (datetime.now() - self._last_ring_time).total_seconds() > 30
                ):
                    self._ring_detected = False
            
            self._last_call_state = call_status
            
            # Extract caller info
            caller_info = call_status.get("caller", {})
            
            return TwoNIntercomData(
                call_status=call_status,
                last_ring_time=self._last_ring_time,
                caller_info=caller_info if caller_info else None,
                available=True,
            )
            
        except TwoNAuthenticationError as err:
            # Authentication errors require user intervention
            _LOGGER.error("Authentication failed: %s", err)
            # Create persistent notification for user
            self.hass.components.persistent_notification.async_create(
                f"Authentication failed for 2N Intercom: {err}. "
                "Please check your credentials and reconfigure the integration.",
                title="2N Intercom Authentication Error",
                notification_id=f"{DOMAIN}_auth_error",
            )
            raise ConfigEntryNotReady(f"Authentication failed: {err}") from err
            
        except (TwoNConnectionError, ConnectionError, TimeoutError) as err:
            # Connection errors - implement exponential backoff
            if self._retry_count < MAX_RETRIES:
                self._retry_count += 1
                delay = min(2 ** self._retry_count, 60)  # Max 60 seconds
                _LOGGER.warning(
                    "Connection error (retry %s/%s, next attempt in %ss): %s",
                    self._retry_count,
                    MAX_RETRIES,
                    delay,
                    err,
                )
                raise UpdateFailed(f"Connection error: {err}") from err
            else:
                # Max retries exceeded
                _LOGGER.error(
                    "Max retries (%s) exceeded for connection to device",
                    MAX_RETRIES,
                )
                raise ConfigEntryNotReady(
                    f"Failed to connect after {MAX_RETRIES} retries"
                ) from err
                
        except Exception as err:
            # Generic API errors - mark entities unavailable but keep trying
            _LOGGER.warning("API error: %s", err)
            raise UpdateFailed(f"Error communicating with device: {err}") from err

    @property
    def ring_active(self) -> bool:
        """Return if doorbell is currently ringing."""
        if self.data:
            # Ring is active if state is ringing or within timeout period
            return self._ring_detected
        return False

    @property
    def last_ring_time(self) -> datetime | None:
        """Return last ring timestamp."""
        if self.data:
            return self.data.last_ring_time
        return None

    @property
    def caller_info(self) -> dict[str, Any]:
        """Return caller information."""
        if self.data and self.data.caller_info:
            return self.data.caller_info
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
        """Get camera snapshot with 1-second caching."""
        try:
            # Check cache to avoid excessive API calls
            current_time = datetime.now()
            
            if (
                self._snapshot_cache is not None
                and self._snapshot_cache_time is not None
                and (current_time - self._snapshot_cache_time).total_seconds() < 1
            ):
                _LOGGER.debug("Returning cached snapshot")
                return self._snapshot_cache
            
            # Fetch new snapshot
            snapshot = await self.api.async_get_snapshot()
            
            if snapshot:
                self._snapshot_cache = snapshot
                self._snapshot_cache_time = current_time
                _LOGGER.debug("Fetched new snapshot from API")
            
            return snapshot
            
        except Exception as err:
            _LOGGER.error("Error getting snapshot: %s", err)
            return None
