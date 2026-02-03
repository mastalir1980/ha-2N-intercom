"""The 2N Intercom integration."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import TwoNIntercomCoordinator

if TYPE_CHECKING:
    from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

# Platforms to support
PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.CAMERA,
    Platform.BINARY_SENSOR,
    Platform.EVENT,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the 2N Intercom component."""
    _LOGGER.debug("Setting up 2N Intercom integration")
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up 2N Intercom from a config entry."""
    _LOGGER.debug("Setting up 2N Intercom config entry: %s", entry.entry_id)
    
    # Create coordinator for this config entry
    coordinator = TwoNIntercomCoordinator(hass, entry)
    
    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()
    
    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    _LOGGER.info("2N Intercom integration successfully set up for %s", entry.title)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading 2N Intercom config entry: %s", entry.entry_id)
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Remove coordinator
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.info("2N Intercom integration successfully unloaded for %s", entry.title)
    
    return unload_ok
