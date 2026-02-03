"""Camera platform for 2N Intercom integration."""
from __future__ import annotations

import logging

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
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

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the camera."""
        super().__init__(coordinator)
        Camera.__init__(self)
        self._attr_name = "2N Intercom Camera"
        self._attr_unique_id = f"{entry.entry_id}_camera"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "2N",
            "model": "IP Intercom",
        }
    
    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a snapshot from the camera."""
        return await self.coordinator.async_get_snapshot()
