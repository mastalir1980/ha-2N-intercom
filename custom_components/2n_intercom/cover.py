"""Cover platform for 2N Intercom."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_RELAY_DEVICE_TYPE,
    CONF_RELAY_NAME,
    CONF_RELAY_NUMBER,
    CONF_RELAY_PULSE_DURATION,
    CONF_RELAYS,
    DEFAULT_GATE_DURATION,
    DEVICE_TYPE_GATE,
    DOMAIN,
)
from .coordinator import TwoNIntercomCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 2N Intercom cover platform."""
    coordinator: TwoNIntercomCoordinator = hass.data[DOMAIN][config_entry.entry_id][
        "coordinator"
    ]
    
    relays = {**config_entry.data, **config_entry.options}.get(CONF_RELAYS, [])
    
    # Create cover entities for gate-type relays
    covers = []
    for relay_config in relays:
        if relay_config.get(CONF_RELAY_DEVICE_TYPE) == DEVICE_TYPE_GATE:
            covers.append(
                TwoNIntercomCover(coordinator, config_entry, relay_config)
            )
    
    if covers:
        async_add_entities(covers, True)


class TwoNIntercomCover(CoordinatorEntity[TwoNIntercomCoordinator], CoverEntity):
    """Representation of a 2N Intercom cover (for gates)."""

    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.GATE
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        config_entry: ConfigEntry,
        relay_config: dict[str, Any],
    ) -> None:
        """Initialize the cover."""
        super().__init__(coordinator)
        
        self._config_entry = config_entry
        self._relay_config = relay_config
        self._relay_number = relay_config[CONF_RELAY_NUMBER]
        self._relay_name = relay_config[CONF_RELAY_NAME]
        self._pulse_duration = relay_config.get(
            CONF_RELAY_PULSE_DURATION, DEFAULT_GATE_DURATION
        )
        
        self._attr_name = self._relay_name
        self._attr_unique_id = f"{config_entry.entry_id}_cover_{self._relay_number}"
        self._attr_is_closed = True
        self._is_opening = False
        self._is_closing = False
        self._state_task: asyncio.Task | None = None

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information about this cover."""
        name = self._config_entry.options.get(
            "name",
            self._config_entry.data.get("name", "2N Intercom"),
        )
        return self.coordinator.get_device_info(self._config_entry.entry_id, name)

    @property
    def is_closed(self) -> bool:
        """Return if the cover is closed."""
        return self._attr_is_closed

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening."""
        return self._is_opening

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing."""
        return self._is_closing

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover (gate)."""
        # Cancel any pending state task
        if self._state_task and not self._state_task.done():
            self._state_task.cancel()
        
        # Trigger relay to open
        success = await self.coordinator.async_trigger_relay(
            relay=self._relay_number,
            duration=self._pulse_duration,
        )
        
        if success:
            # Set opening state
            self._is_opening = True
            self._is_closing = False
            self._attr_is_closed = False
            self.async_write_ha_state()
            
            # Schedule state change after duration
            self._state_task = asyncio.create_task(
                self._async_set_open_after_delay()
            )
        else:
            _LOGGER.error("Failed to open cover %s", self._relay_number)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover (gate)."""
        # Cancel any pending state task
        if self._state_task and not self._state_task.done():
            self._state_task.cancel()
        
        # Trigger relay to close
        success = await self.coordinator.async_trigger_relay(
            relay=self._relay_number,
            duration=self._pulse_duration,
        )
        
        if success:
            # Set closing state
            self._is_closing = True
            self._is_opening = False
            self.async_write_ha_state()
            
            # Schedule state change after duration
            self._state_task = asyncio.create_task(
                self._async_set_closed_after_delay()
            )
        else:
            _LOGGER.error("Failed to close cover %s", self._relay_number)

    async def _async_set_open_after_delay(self) -> None:
        """Set cover to fully open after delay."""
        try:
            # Wait for operation duration (convert milliseconds to seconds)
            await asyncio.sleep(self._pulse_duration / 1000)
            
            self._is_opening = False
            self._attr_is_closed = False
            self.async_write_ha_state()
        except asyncio.CancelledError:
            # Task was cancelled, do nothing
            pass

    async def _async_set_closed_after_delay(self) -> None:
        """Set cover to fully closed after delay."""
        try:
            # Wait for operation duration (convert milliseconds to seconds)
            await asyncio.sleep(self._pulse_duration / 1000)
            
            self._is_closing = False
            self._attr_is_closed = True
            self.async_write_ha_state()
        except asyncio.CancelledError:
            # Task was cancelled, do nothing
            pass

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success
