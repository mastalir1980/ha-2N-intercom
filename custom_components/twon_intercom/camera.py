"""Camera platform for 2N Intercom."""
from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TwoNIntercomCoordinator

_LOGGER = logging.getLogger(__name__)

# Cache snapshots for 1 second to avoid excessive API calls
SNAPSHOT_CACHE_DURATION = timedelta(seconds=1)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 2N Intercom camera platform."""
    coordinator: TwoNIntercomCoordinator = hass.data[DOMAIN][config_entry.entry_id][
        "coordinator"
    ]
    
    async_add_entities(
        [TwoNIntercomCamera(coordinator, config_entry)],
        True,
    )


class TwoNIntercomCamera(CoordinatorEntity[TwoNIntercomCoordinator], Camera):
    """Representation of a 2N Intercom camera."""

    _attr_has_entity_name = True
    _attr_name = "Camera"
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the camera."""
        super().__init__(coordinator)
        Camera.__init__(self)
        
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_camera"
        self._last_snapshot: bytes | None = None
        self._last_snapshot_time: float = 0

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information about this camera."""
        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": self._config_entry.data.get("name", "2N Intercom"),
            "manufacturer": "2N",
            "model": "IP Intercom",
            "sw_version": "1.0.0",
        }

    @property
    def is_recording(self) -> bool:
        """Return true if the device is recording."""
        return False

    @property
    def motion_detection_enabled(self) -> bool:
        """Return the camera motion detection status."""
        return False

    @property
    def brand(self) -> str:
        """Return the camera brand."""
        return "2N"

    @property
    def model(self) -> str:
        """Return the camera model."""
        return "IP Intercom"

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return bytes of camera image."""
        # Check cache to avoid excessive API calls
        current_time = time.time()
        
        if (
            self._last_snapshot is not None
            and current_time - self._last_snapshot_time < SNAPSHOT_CACHE_DURATION.total_seconds()
        ):
            return self._last_snapshot
        
        # Fetch new snapshot
        snapshot = await self.coordinator.async_get_snapshot(
            width=width, height=height
        )
        
        if snapshot:
            self._last_snapshot = snapshot
            self._last_snapshot_time = current_time
        
        return snapshot

    async def stream_source(self) -> str | None:
        """Return the source of the stream."""
        # Return RTSP URL for streaming
        return self.coordinator.api.get_rtsp_url_with_credentials()

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success
