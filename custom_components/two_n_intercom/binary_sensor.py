"""Binary sensor platform for 2N Intercom integration."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BINARY_SENSOR_CALL_STATE, BINARY_SENSOR_MOTION, DOMAIN
from .coordinator import TwoNIntercomCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 2N Intercom binary sensor entities."""
    coordinator: TwoNIntercomCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = [
        TwoNIntercomCallStateSensor(coordinator, entry),
        TwoNIntercomMotionSensor(coordinator, entry),
    ]
    
    async_add_entities(entities)


class TwoNIntercomBinarySensor(CoordinatorEntity[TwoNIntercomCoordinator], BinarySensorEntity):
    """Base class for 2N Intercom binary sensors."""

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        entry: ConfigEntry,
        sensor_type: str,
        name: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._attr_name = f"2N Intercom {name}"
        self._attr_unique_id = f"{entry.entry_id}_{sensor_type}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "2N",
            "model": "IP Intercom",
        }


class TwoNIntercomCallStateSensor(TwoNIntercomBinarySensor):
    """Binary sensor for call state."""

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the call state sensor."""
        super().__init__(coordinator, entry, BINARY_SENSOR_CALL_STATE, "Call State")
        self._attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    
    @property
    def is_on(self) -> bool:
        """Return true if there is an active call."""
        call_status = self.coordinator.data.get("call_status", {})
        return call_status.get("active", False)


class TwoNIntercomMotionSensor(TwoNIntercomBinarySensor):
    """Binary sensor for motion detection."""

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the motion sensor."""
        super().__init__(coordinator, entry, BINARY_SENSOR_MOTION, "Motion")
        self._attr_device_class = BinarySensorDeviceClass.MOTION
    
    @property
    def is_on(self) -> bool:
        """Return true if motion is detected."""
        status = self.coordinator.data.get("status", {})
        return status.get("motion", False)
