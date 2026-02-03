"""Event platform for 2N Intercom integration."""
from __future__ import annotations

import logging

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, EVENT_DOORBELL
from .coordinator import TwoNIntercomCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 2N Intercom event entities."""
    coordinator: TwoNIntercomCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities([TwoNIntercomDoorbellEvent(coordinator, entry)])


class TwoNIntercomDoorbellEvent(CoordinatorEntity[TwoNIntercomCoordinator], EventEntity):
    """Representation of a 2N Intercom doorbell event."""

    _attr_event_types = ["pressed"]

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the event entity."""
        super().__init__(coordinator)
        self._attr_name = "2N Intercom Doorbell"
        self._attr_unique_id = f"{entry.entry_id}_{EVENT_DOORBELL}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "2N",
            "model": "IP Intercom",
        }
        self._last_event_time = None
    
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Check if doorbell was pressed
        call_status = self.coordinator.data.get("call_status", {})
        event_time = call_status.get("doorbell_time")
        
        # Trigger event if new doorbell press detected
        if event_time and event_time != self._last_event_time:
            self._trigger_event("pressed", {"timestamp": event_time})
            self._last_event_time = event_time
        
        super()._handle_coordinator_update()
