"""Informational firmware updates; installation happens in the device web UI."""
from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from typing import TYPE_CHECKING

import aiohttp
from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FIRMWARE_CHANNEL,
    DEFAULT_FIRMWARE_CHANNEL,
    FIRMWARE_CHANNEL_TRACKS,
    FIRMWARE_CHECK_INTERVAL,
)
from .coordinator import TwoNIntercomCoordinator
from .entity import TwoNIntercomEntity
from .firmware import FirmwareCheckError, check
from .web import device_web_url

if TYPE_CHECKING:
    from .coordinator import TwoNIntercomConfigEntry

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 1
# HA update entities limit the short summary to 255 characters.
RELEASE_SUMMARY_LIMIT = 255


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TwoNIntercomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add one update entity only when the device identifies its firmware package."""
    coordinator = config_entry.runtime_data.coordinator
    package = coordinator.system_info.get("firmwarePackage")
    if not isinstance(package, str) or not package.strip():
        _LOGGER.debug("No firmwarePackage in system/info; firmware entity not created")
        return
    async_add_entities(
        [
            TwoNIntercomFirmwareUpdate(
                coordinator, config_entry, async_get_clientsession(hass)
            )
        ],
        True,
    )


class TwoNIntercomFirmwareUpdate(TwoNIntercomEntity, UpdateEntity):  # type: ignore[misc]
    """Firmware version and notes, without any device firmware write capability."""

    _attr_translation_key = "firmware"
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_entity_category = EntityCategory.CONFIG
    _attr_supported_features = UpdateEntityFeature.RELEASE_NOTES

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        config_entry: TwoNIntercomConfigEntry,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize the entity with HA's shared, unauthenticated session."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_firmware"
        self._attr_release_url = device_web_url(config_entry.data)
        self._session = session
        self._release_notes: str | None = None
        self._attr_latest_version = config_entry.runtime_data.firmware_latest_version
        self._check_failed = False
        self._last_check: datetime | None = None
        self._check_lock = asyncio.Lock()

    async def async_added_to_hass(self) -> None:
        """Schedule catalog checks independently of device coordinator polling."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._async_interval_update, FIRMWARE_CHECK_INTERVAL
            )
        )

    async def _async_interval_update(self, now: datetime) -> None:
        """Publish the catalog result after a scheduled check."""
        await self.async_update()
        self.async_write_ha_state()

    @property
    def installed_version(self) -> str | None:
        """Follow the installed version refreshed by the device coordinator."""
        version = self.coordinator.system_info.get("swVersion")
        return version if isinstance(version, str) and version else None

    @property
    def release_summary(self) -> str | None:
        """Return the newest release notes within HA's short-summary limit."""
        return self._release_notes[:RELEASE_SUMMARY_LIMIT] if self._release_notes else None

    async def async_release_notes(self) -> str | None:
        """Return the full cached markdown, newest release first."""
        return self._release_notes

    async def async_update(self) -> None:
        """Check at setup, every six hours, and on homeassistant.update_entity."""
        async with self._check_lock:
            self._last_check = dt_util.utcnow()
            channel = self._config_entry.options.get(
                CONF_FIRMWARE_CHANNEL, DEFAULT_FIRMWARE_CHANNEL
            )
            try:
                if channel not in FIRMWARE_CHANNEL_TRACKS:
                    raise FirmwareCheckError("Invalid firmware channel")
                package = self.coordinator.system_info.get("firmwarePackage")
                installed = self.installed_version
                if not isinstance(package, str) or installed is None:
                    raise FirmwareCheckError("Missing firmware package or installed version")
                release = await check(
                    self._session, package, FIRMWARE_CHANNEL_TRACKS[channel], installed
                )
            except FirmwareCheckError as err:
                if not self._check_failed:
                    _LOGGER.warning("Firmware version check failed: %s", err)
                self._check_failed = True
                return

            self._check_failed = False
            self._attr_latest_version = release.version if release else installed
            self._release_notes = release.release_notes if release else None
            self._config_entry.runtime_data.firmware_latest_version = self._attr_latest_version
