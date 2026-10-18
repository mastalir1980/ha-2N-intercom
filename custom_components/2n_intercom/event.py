"""Doorbell event platform for 2N Intercom."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TwoNIntercomCoordinator, TwoNIntercomRuntimeData
from .entity import TwoNIntercomEntity

if TYPE_CHECKING:
    from .coordinator import TwoNIntercomConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TwoNIntercomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the doorbell event (only forwarded when doorbell is enabled)."""
    runtime: TwoNIntercomRuntimeData = config_entry.runtime_data
    async_add_entities(
        [TwoNIntercomDoorbellEvent(runtime.coordinator, config_entry)]
    )


class TwoNIntercomDoorbellEvent(TwoNIntercomEntity, EventEntity):  # type: ignore[misc]
    """A single event for each new intercom-started doorbell ring."""

    _attr_device_class = EventDeviceClass.DOORBELL
    _attr_event_types = ["ring"]
    _attr_translation_key = "doorbell"

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        config_entry: TwoNIntercomConfigEntry,
    ) -> None:
        """Initialize the doorbell event."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_doorbell_event"
        self._last_ring_count = coordinator.ring_count

    async def async_added_to_hass(self) -> None:
        """Ignore rings from before this entity started listening."""
        self._last_ring_count = self.coordinator.ring_count
        await super().async_added_to_hass()

    @callback  # type: ignore[misc]
    def _handle_coordinator_update(self) -> None:
        """Emit only for a new ring, not for duplicate call or poll updates."""
        if self.coordinator.ring_count > self._last_ring_count:
            self._last_ring_count = self.coordinator.ring_count
            attributes: dict[str, Any] = {}
            if self.coordinator.called_peer:
                attributes["called_peer"] = self.coordinator.called_peer
            caller_info = self.coordinator.caller_info
            if "name" in caller_info:
                attributes["caller_name"] = caller_info["name"]
            if "number" in caller_info:
                attributes["caller_number"] = caller_info["number"]
            self._trigger_event("ring", attributes)
        self.async_write_ha_state()
