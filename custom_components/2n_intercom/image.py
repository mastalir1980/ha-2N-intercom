"""Image platform for 2N Intercom — snapshot taken at the last ring."""
from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TwoNIntercomCoordinator, TwoNIntercomRuntimeData
from .entity import TwoNIntercomEntity

if TYPE_CHECKING:
    from .coordinator import TwoNIntercomConfigEntry

# The entity only serves bytes the coordinator already captured.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TwoNIntercomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the last-ring image (only forwarded when the camera is enabled)."""
    runtime: TwoNIntercomRuntimeData = config_entry.runtime_data
    async_add_entities(
        [TwoNIntercomLastRingImage(hass, runtime.coordinator, config_entry)]
    )


class TwoNIntercomLastRingImage(TwoNIntercomEntity, ImageEntity):  # type: ignore[misc]
    """JPEG captured when the doorbell rang, not the current camera view."""

    _attr_translation_key = "last_ring"
    _attr_content_type = "image/jpeg"

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: TwoNIntercomCoordinator,
        config_entry: TwoNIntercomConfigEntry,
    ) -> None:
        """Initialise the entity."""
        TwoNIntercomEntity.__init__(self, coordinator, config_entry)
        ImageEntity.__init__(self, hass)
        self._attr_unique_id = f"{config_entry.entry_id}_last_ring"
        self._attr_image_last_updated = coordinator.ring_snapshot_time

    @callback  # type: ignore[misc]
    def _handle_coordinator_update(self) -> None:
        """Pick up a newly captured ring snapshot."""
        self._attr_image_last_updated = self.coordinator.ring_snapshot_time
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        """Return the JPEG captured at the last ring."""
        return self.coordinator.ring_snapshot
