"""Switch platform for 2N Intercom.

Automatically creates a switch entity for every enabled relay reported
by the device's ``/api/switch/caps`` endpoint.  No manual relay
configuration is required — the integration discovers relays at setup
time and uses the device's ``switchOnDuration`` as the default pulse
length.

Entities are added and removed dynamically as relays are enabled or
disabled on the device — no HA restart required.

Physical IO outputs are also discovered at setup, except the status LED.
These disabled-by-default switches latch until explicitly turned off.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from typing import TYPE_CHECKING

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_RELAY_DEVICE_TYPE,
    CONF_RELAY_NAME,
    CONF_RELAY_NUMBER,
    CONF_RELAY_PULSE_DURATION,
    CONF_RELAYS,
    DEFAULT_PULSE_DURATION,
    DEVICE_TYPE_GATE,
    DOMAIN,
    IO_EXCLUDED_OUTPUTS,
)
from .coordinator import TwoNIntercomCoordinator, TwoNIntercomRuntimeData
from .entity import TwoNIntercomEntity, io_ports_of_type, is_io_port_on

if TYPE_CHECKING:
    from .coordinator import TwoNIntercomConfigEntry

# Switch actions hit the device (relay trigger) so we serialise them per
# platform; reads come from the coordinator and don't count toward this limit.
PARALLEL_UPDATES = 1

_LOGGER = logging.getLogger(__name__)


def _get_user_relay_overrides(
    config_entry: TwoNIntercomConfigEntry,
) -> dict[int, dict[str, Any]]:
    """Return a ``{relay_number: relay_config}`` map from user options."""
    relays = config_entry.options.get(
        CONF_RELAYS, config_entry.data.get(CONF_RELAYS, [])
    )
    overrides: dict[int, dict[str, Any]] = {}
    for relay in relays or []:
        if not isinstance(relay, dict):
            continue
        num = relay.get(CONF_RELAY_NUMBER)
        if isinstance(num, int):
            overrides[num] = relay
    return overrides


def _build_switch_params(
    cap: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    """Build relay_name and pulse_duration from caps + user overrides."""
    relay_number = cap["switch"]

    # Device reports switchOnDuration in seconds; our pulse duration
    # is in milliseconds.
    device_duration_s = cap.get("switchOnDuration")
    if isinstance(device_duration_s, (int, float)) and device_duration_s > 0:
        default_pulse_ms = int(device_duration_s * 1000)
    else:
        default_pulse_ms = DEFAULT_PULSE_DURATION

    relay_name = override.get(CONF_RELAY_NAME) or f"Relay {relay_number}"
    pulse_duration = override.get(CONF_RELAY_PULSE_DURATION, default_pulse_ms)

    return {
        "relay_number": relay_number,
        "relay_name": relay_name,
        "pulse_duration": pulse_duration,
    }


def _switch_unique_id(entry_id: str, relay_number: int) -> str:
    """Return the unique_id for a switch entity."""
    return f"{entry_id}_switch_{relay_number}"


def _io_output_ports(coordinator: TwoNIntercomCoordinator) -> list[str]:
    """Return usable physical outputs present in both capabilities and status."""
    return [
        port
        for port in io_ports_of_type(coordinator.io_caps, coordinator.io_status, "output")
        if port not in IO_EXCLUDED_OUTPUTS
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TwoNIntercomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 2N Intercom switch platform with dynamic discovery."""
    runtime: TwoNIntercomRuntimeData = config_entry.runtime_data
    coordinator: TwoNIntercomCoordinator = runtime.coordinator

    # Track which relay numbers already have entities.
    tracked_relays: set[int] = set()

    def _get_eligible_caps() -> list[dict[str, Any]]:
        """Return caps entries that should be switch entities."""
        switch_caps = coordinator.switch_caps
        caps_switches = switch_caps.get("switches") or []
        user_overrides = _get_user_relay_overrides(config_entry)
        eligible: list[dict[str, Any]] = []
        for cap in caps_switches:
            if not isinstance(cap, dict) or not cap.get("enabled"):
                continue
            relay_number = cap.get("switch")
            if not isinstance(relay_number, int):
                continue
            override = user_overrides.get(relay_number, {})
            if override.get(CONF_RELAY_DEVICE_TYPE) == DEVICE_TYPE_GATE:
                continue
            eligible.append(cap)
        return eligible

    def _remove_stale_entities(
        enabled_numbers: set[int],
    ) -> None:
        """Remove entities for relays that are no longer enabled."""
        stale = tracked_relays - enabled_numbers
        if not stale:
            return
        registry = er.async_get(hass)
        for relay_number in stale:
            uid = _switch_unique_id(config_entry.entry_id, relay_number)
            entity_id = registry.async_get_entity_id("switch", DOMAIN, uid)
            if entity_id:
                registry.async_remove(entity_id)
                _LOGGER.info(
                    "Removed switch entity %s (relay %s disabled on device)",
                    entity_id,
                    relay_number,
                )
        tracked_relays.difference_update(stale)

    @callback
    def _async_check_relays() -> None:
        """React to coordinator updates — add/remove switch entities."""
        eligible = _get_eligible_caps()
        eligible_numbers = {c["switch"] for c in eligible}
        user_overrides = _get_user_relay_overrides(config_entry)

        # Remove entities for relays that disappeared.
        _remove_stale_entities(eligible_numbers)

        # Add entities for newly enabled relays.
        new_entities: list[TwoNIntercomSwitch] = []
        for cap in eligible:
            relay_number = cap["switch"]
            if relay_number in tracked_relays:
                continue
            override = user_overrides.get(relay_number, {})
            params = _build_switch_params(cap, override)
            new_entities.append(
                TwoNIntercomSwitch(coordinator, config_entry, **params)
            )
            tracked_relays.add(relay_number)

        if new_entities:
            async_add_entities(new_entities, True)

    # Initial population.
    _async_check_relays()

    io_outputs = [
        TwoNIntercomIoOutputSwitch(coordinator, config_entry, port)
        for port in _io_output_ports(coordinator)
    ]
    if io_outputs:
        async_add_entities(io_outputs)

    # Listen for future coordinator updates to add/remove dynamically.
    config_entry.async_on_unload(
        coordinator.async_add_listener(_async_check_relays)
    )


class TwoNIntercomIoOutputSwitch(TwoNIntercomEntity, SwitchEntity):  # type: ignore[misc]
    """Direct, latching control of a physical IO output."""

    _attr_translation_key = "io_output"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        config_entry: TwoNIntercomConfigEntry,
        port: str,
    ) -> None:
        """Initialize the output switch."""
        super().__init__(coordinator, config_entry)
        self._port = port
        self._attr_unique_id = f"{config_entry.entry_id}_io_{port}"
        self._attr_translation_placeholders = {"port": port}

    @property
    def is_on(self) -> bool:
        """Return the device-confirmed output state."""
        return is_io_port_on(self.coordinator.io_status, self._port)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Latch the output on."""
        await self._async_set_output(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Latch the output off."""
        await self._async_set_output(False)

    async def _async_set_output(self, on: bool) -> None:
        """Control the output or surface the device rejection."""
        if not await self.coordinator.async_set_io_output(self._port, on):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="io_control_failed",
                translation_placeholders={"port": self._port},
            )


class TwoNIntercomSwitch(TwoNIntercomEntity, SwitchEntity):  # type: ignore[misc]
    """Representation of a 2N Intercom switch (for doors)."""

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        config_entry: TwoNIntercomConfigEntry,
        *,
        relay_number: int,
        relay_name: str,
        pulse_duration: int,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, config_entry)

        self._relay_number = relay_number
        self._pulse_duration = pulse_duration

        self._attr_name = relay_name
        self._attr_unique_id = _switch_unique_id(
            config_entry.entry_id, relay_number
        )
        self._attr_is_on = False
        self._turning_off_task: asyncio.Task[None] | None = None

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        # Prefer live status from coordinator when available.
        switches = self.coordinator.switch_status.get("switches")
        if isinstance(switches, list):
            for sw in switches:
                if not isinstance(sw, dict):
                    continue
                if sw.get("switch") != self._relay_number:
                    continue
                active = sw.get("active")
                held = sw.get("held")
                if isinstance(active, bool):
                    return active or bool(held)
                break
        return bool(self._attr_is_on)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on (trigger relay)."""
        self._cancel_turning_off_task()

        # Trigger relay
        success = await self.coordinator.async_trigger_relay(
            relay=self._relay_number,
            duration=self._pulse_duration,
        )

        if success:
            self._attr_is_on = True
            self.async_write_ha_state()

            # Schedule automatic turn off after pulse duration.
            # Use hass.async_create_task for proper lifecycle tracking;
            # fall back to asyncio.create_task in test environments.
            coro = self._async_turn_off_after_delay()
            if self.hass is not None:
                self._turning_off_task = self.hass.async_create_task(
                    coro, eager_start=False,
                )
            else:
                self._turning_off_task = asyncio.create_task(coro)
        else:
            _LOGGER.error("Failed to trigger relay %s", self._relay_number)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off (no actual action, just update state)."""
        self._cancel_turning_off_task()
        self._attr_is_on = False
        self.async_write_ha_state()

    def _cancel_turning_off_task(self) -> None:
        """Cancel any pending delayed turn-off task."""
        if self._turning_off_task and not self._turning_off_task.done():
            self._turning_off_task.cancel()
            self._turning_off_task = None

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        self._cancel_turning_off_task()
        await super().async_will_remove_from_hass()

    async def _async_turn_off_after_delay(self) -> None:
        """Turn off the switch after the pulse duration."""
        try:
            # Wait for pulse duration (convert milliseconds to seconds)
            await asyncio.sleep(self._pulse_duration / 1000)
            self._attr_is_on = False
            self.async_write_ha_state()
        except asyncio.CancelledError:
            # Task was cancelled, do nothing
            pass
