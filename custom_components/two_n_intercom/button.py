"""Button platform for 2N Intercom integration."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import TwoNIntercomCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 2N Intercom button entities."""
    coordinator: TwoNIntercomCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities([TwoNIntercomDoorButton(coordinator, entry)])


class TwoNIntercomDoorButton(ButtonEntity):
    """Representation of a 2N Intercom door open button."""

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the button."""
        self.coordinator = coordinator
        self._entry = entry
        self._attr_name = "2N Intercom Open Door"
        self._attr_unique_id = f"{entry.entry_id}_door_open"
        self._attr_icon = "mdi:door-open"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "2N",
            "model": "IP Intercom",
        }

    async def async_press(self) -> None:
        """Handle the button press - open the door."""
        _LOGGER.info("Door open button pressed")
        await self.coordinator.async_open_door()
