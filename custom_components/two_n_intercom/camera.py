"""Camera platform for 2N Intercom integration."""
from __future__ import annotations

import logging
from urllib.parse import quote_plus

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_RTSP_PORT,
    DEFAULT_RTSP_PORT,
    DOMAIN,
    RTSP_STREAM_PATH,
)
from .coordinator import TwoNIntercomCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 2N Intercom camera entity."""
    coordinator: TwoNIntercomCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities([TwoNIntercomCamera(coordinator, entry)])


class TwoNIntercomCamera(CoordinatorEntity[TwoNIntercomCoordinator], Camera):
    """Representation of a 2N Intercom camera."""

    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the camera."""
        super().__init__(coordinator)
        Camera.__init__(self)
        self._entry = entry
        self._attr_name = "2N Intercom Camera"
        self._attr_unique_id = f"{entry.entry_id}_camera"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "2N",
            "model": "IP Intercom",
        }

    async def stream_source(self) -> str | None:
        """Return the RTSP stream source URL."""
        host = self._entry.data[CONF_HOST]
        username = self._entry.data.get(CONF_USERNAME)
        password = self._entry.data.get(CONF_PASSWORD)
        rtsp_port = self._entry.data.get(CONF_RTSP_PORT, DEFAULT_RTSP_PORT)

        if username and password:
            # URL-encode credentials for special characters
            encoded_user = quote_plus(username)
            encoded_pass = quote_plus(password)
            return f"rtsp://{encoded_user}:{encoded_pass}@{host}:{rtsp_port}{RTSP_STREAM_PATH}"
        return f"rtsp://{host}:{rtsp_port}{RTSP_STREAM_PATH}"

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a snapshot from the camera."""
        return await self.coordinator.async_get_snapshot()
