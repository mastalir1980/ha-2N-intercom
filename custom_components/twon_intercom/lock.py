"""Support for 2N Intercom locks."""
from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity, LockEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DOOR_TYPE, DOMAIN, DOOR_TYPE_GATE
from .coordinator import TwoNIntercomCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 2N Intercom lock platform."""
    coordinator: TwoNIntercomCoordinator = hass.data[DOMAIN][config_entry.entry_id][
        "coordinator"
    ]
    
    door_type = config_entry.options.get(
        CONF_DOOR_TYPE, config_entry.data.get(CONF_DOOR_TYPE)
    )

    async_add_entities(
        [TwoNIntercomLock(coordinator, config_entry, door_type)],
        True,
    )


class TwoNIntercomLock(CoordinatorEntity[TwoNIntercomCoordinator], LockEntity):
    """Representation of a 2N Intercom lock."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = LockEntityFeature.OPEN

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        config_entry: ConfigEntry,
        door_type: str | None,
    ) -> None:
        """Initialize the lock."""
        super().__init__(coordinator)
        
        self._config_entry = config_entry
        self._door_type = door_type
        self._attr_unique_id = f"{config_entry.entry_id}_lock"
        self._attr_is_locked = True

        # Set device class based on door type for HomeKit
        # Gate -> DEVICE_CLASS_GATE for HomeKit garage door accessory
        # Door -> no device class (default door lock)
        if door_type == DOOR_TYPE_GATE:
            self._attr_device_class = "gate"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information about this lock."""
        return {
            "identifiers": {(DOMAIN, self._config_entry.entry_id)},
            "name": self._config_entry.data.get("name", "2N Intercom"),
            "manufacturer": "2N",
            "model": "Intercom",
        }

    @property
    def is_locked(self) -> bool:
        """Return true if lock is locked."""
        return self._attr_is_locked

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the lock."""
        self._attr_is_locked = True
        self.async_write_ha_state()

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the lock."""
        # Trigger relay 1 (default relay for legacy lock)
        success = await self.coordinator.async_trigger_relay(relay=1, duration=2000)
        
        if success:
            self._attr_is_locked = False
            self.async_write_ha_state()

    async def async_open(self, **kwargs: Any) -> None:
        """Open the door/gate."""
        # Same as unlock
        await self.async_unlock(**kwargs)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success
