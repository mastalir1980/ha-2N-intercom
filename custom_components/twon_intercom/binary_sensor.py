"""Binary sensor platform for 2N Intercom."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TwoNIntercomCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 2N Intercom binary sensor platform."""
    coordinator: TwoNIntercomCoordinator = hass.data[DOMAIN][config_entry.entry_id][
        "coordinator"
    ]
    
    async_add_entities(
        [TwoNIntercomDoorbell(coordinator, config_entry)],
        True,
    )


class TwoNIntercomDoorbell(CoordinatorEntity[TwoNIntercomCoordinator], BinarySensorEntity):
    """Representation of a 2N Intercom doorbell."""

    _attr_has_entity_name = True
    _attr_name = "Doorbell"
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY  # Fallback for older HA versions

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the doorbell."""
        super().__init__(coordinator)
        
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_doorbell"
        
        # Set device class to doorbell if available in HA version
        # This enables proper HomeKit doorbell integration
        try:
            self._attr_device_class = BinarySensorDeviceClass.DOORBELL
        except AttributeError:
            # Fallback for older HA versions
            self._attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information about this doorbell."""
        name = self._config_entry.options.get(
            "name",
            self._config_entry.data.get("name", "2N Intercom"),
        )
        return self.coordinator.get_device_info(self._config_entry.entry_id, name)

    @property
    def is_on(self) -> bool:
        """Return true if doorbell is ringing."""
        return self.coordinator.ring_active

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attributes: dict[str, Any] = {}
        
        if self.coordinator.last_ring_time:
            attributes["last_ring"] = self.coordinator.last_ring_time.isoformat()
        
        caller_info = self.coordinator.caller_info
        if caller_info:
            if "name" in caller_info:
                attributes["caller_name"] = caller_info["name"]
            if "number" in caller_info:
                attributes["caller_number"] = caller_info["number"]
            if "button" in caller_info:
                attributes["button"] = caller_info["button"]
        
        # Add call status info if available
        if self.coordinator.data:
            call_status = self.coordinator.data.call_status
            if call_status:
                if "state" in call_status:
                    attributes["call_state"] = call_status["state"]
                if "direction" in call_status:
                    attributes["call_direction"] = call_status["direction"]
        
        return attributes

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success
