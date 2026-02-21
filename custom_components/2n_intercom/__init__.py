"""The 2N Intercom integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .api import TwoNIntercomAPI
from .const import (
    CONF_CALLED_ID,
    CONF_ENABLE_CAMERA,
    CONF_ENABLE_DOORBELL,
    CONF_PROTOCOL,
    CONF_RELAYS,
    CONF_VERIFY_SSL,
    DEFAULT_ENABLE_CAMERA,
    DEFAULT_ENABLE_DOORBELL,
    DEFAULT_PROTOCOL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)
from .coordinator import TwoNIntercomCoordinator

_LOGGER = logging.getLogger(__name__)


def _get_entry_data(entry: ConfigEntry) -> dict[str, object]:
    """Return merged config data with options overriding defaults."""
    return {**entry.data, **entry.options}

# Determine which platforms to set up based on config
def _get_platforms(entry: ConfigEntry) -> list[str]:
    """Get list of platforms to set up based on configuration."""
    data = _get_entry_data(entry)
    platforms = []
    
    # Camera platform
    if data.get(CONF_ENABLE_CAMERA, DEFAULT_ENABLE_CAMERA):
        platforms.append("camera")
    
    # Doorbell platform
    if data.get(CONF_ENABLE_DOORBELL, DEFAULT_ENABLE_DOORBELL):
        platforms.append("binary_sensor")
    
    # Relay platforms - check if we have relays configured
    relays = data.get(CONF_RELAYS, [])
    if relays:
        # Add switch for door relays
        platforms.append("switch")
        # Add cover for gate relays
        platforms.append("cover")
    
    # Always include lock for backward compatibility
    platforms.append("lock")
    
    return platforms


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up 2N Intercom from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    data = _get_entry_data(entry)
    
    # Create API client
    api = TwoNIntercomAPI(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        protocol=data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL),
        verify_ssl=data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
    )
    
    # Create coordinator
    coordinator = TwoNIntercomCoordinator(
        hass,
        api,
        called_id=data.get(CONF_CALLED_ID),
    )
    
    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()
    
    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "api": api,
    }
    
    # Set up platforms
    platforms = _get_platforms(entry)
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    
    # Register update listener
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    platforms = _get_platforms(entry)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    
    if unload_ok:
        # Close API session
        data = hass.data[DOMAIN].pop(entry.entry_id)
        if "api" in data:
            await data["api"].async_close()
    
    return unload_ok
