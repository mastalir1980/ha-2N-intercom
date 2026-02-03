"""Switch platform for 2N Intercom integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SWITCH_AUTO_OPEN, SWITCH_CAMERA, SWITCH_MICROPHONE
from .coordinator import TwoNIntercomCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 2N Intercom switch entities."""
    coordinator: TwoNIntercomCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    
    # Check which switches are supported by the device
    switch_caps = coordinator.data.get("switch_caps", {})
    
    if switch_caps.get(SWITCH_CAMERA):
        entities.append(TwoNIntercomSwitch(coordinator, entry, SWITCH_CAMERA, "Camera"))
    
    if switch_caps.get(SWITCH_MICROPHONE):
        entities.append(TwoNIntercomSwitch(coordinator, entry, SWITCH_MICROPHONE, "Microphone"))
    
    if switch_caps.get(SWITCH_AUTO_OPEN):
        entities.append(TwoNIntercomSwitch(coordinator, entry, SWITCH_AUTO_OPEN, "Auto Open"))
    
    async_add_entities(entities)


class TwoNIntercomSwitch(CoordinatorEntity[TwoNIntercomCoordinator], SwitchEntity):
    """Representation of a 2N Intercom switch."""

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        entry: ConfigEntry,
        switch_type: str,
        name: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._switch_type = switch_type
        self._attr_name = f"2N Intercom {name}"
        self._attr_unique_id = f"{entry.entry_id}_{switch_type}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "2N",
            "model": "IP Intercom",
        }
    
    @property
    def is_on(self) -> bool | None:
        """Return true if switch is on."""
        switch_caps = self.coordinator.data.get("switch_caps", {})
        return switch_caps.get(self._switch_type, {}).get("state", False)
    
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.coordinator.async_switch_control(self._switch_type, True)
        await self.coordinator.async_request_refresh()
    
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.coordinator.async_switch_control(self._switch_type, False)
        await self.coordinator.async_request_refresh()
