"""Binary sensor platform for 2N Intercom."""
from __future__ import annotations

import logging
from typing import Any

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
try:
    from homeassistant.const import EntityCategory
except ImportError:  # pragma: no cover — test stub compat
    from homeassistant.helpers.entity import EntityCategory  # type: ignore[no-redef,assignment,attr-defined]
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TwoNIntercomCoordinator, TwoNIntercomRuntimeData
from .entity import TwoNIntercomEntity, io_ports_of_type, is_io_port_on

if TYPE_CHECKING:
    from .coordinator import TwoNIntercomConfigEntry

# Entities are pure consumers of the coordinator's cached data and never hit
# the device on async_update, so unlimited concurrency is the right answer per
# the HA quality-scale `parallel-updates` rule.
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


def _port_exists(
    payload: dict[str, Any],
    port_name: str,
    *,
    port_type: str | None = None,
) -> bool:
    """Return True when the cached port payload contains the requested port."""
    ports = payload.get("ports") or []
    for port in ports:
        if not isinstance(port, dict):
            continue
        if port.get("port") != port_name:
            continue
        if port_type is not None and port.get("type") != port_type:
            continue
        return True
    return False


def _switch_exists(payload: dict[str, Any], switch_number: int) -> bool:
    """Return True when the cached switch payload contains the requested switch."""
    switches = payload.get("switches") or []
    for switch in switches:
        if not isinstance(switch, dict):
            continue
        if switch.get("switch") == switch_number:
            return True
    return False


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: TwoNIntercomConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up 2N Intercom binary sensor platform."""
    runtime: TwoNIntercomRuntimeData = config_entry.runtime_data
    coordinator: TwoNIntercomCoordinator = runtime.coordinator
    entities: list[BinarySensorEntity] = [TwoNIntercomDoorbell(coordinator, config_entry)]

    for port in io_ports_of_type(coordinator.io_caps, coordinator.io_status, "input"):
        if port == "input1":
            entities.append(TwoNIntercomInput1Sensor(coordinator, config_entry))
        else:
            entities.append(TwoNIntercomIoInputSensor(coordinator, config_entry, port))

    if _switch_exists(coordinator.switch_caps, 1):
        entities.append(TwoNIntercomRelay1ActiveSensor(coordinator, config_entry))

    if coordinator.motion_detection_available:
        entities.append(TwoNIntercomMotionSensor(coordinator, config_entry))

    async_add_entities(
        entities,
        True,
    )


class TwoNIntercomDoorbell(TwoNIntercomEntity, BinarySensorEntity):  # type: ignore[misc]
    """Representation of a 2N Intercom doorbell.

    Uses ``OCCUPANCY`` rather than ``DOORBELL`` because HomeKit's
    programmable-switch / doorbell mapping wants the dedicated
    HomeKit accessory wired up via the ``homekit`` integration —
    occupancy gives the right HA semantics for "someone pressed
    the button" without overloading device-class meaning.
    """

    _attr_translation_key = "doorbell"

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        config_entry: TwoNIntercomConfigEntry,
    ) -> None:
        """Initialize the doorbell."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_doorbell"

    @property
    def is_on(self) -> bool:
        """Return true if doorbell is ringing."""
        active: bool = self.coordinator.ring_active
        return active

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attributes: dict[str, Any] = {}

        if self.coordinator.last_ring_time:
            attributes["last_ring"] = self.coordinator.last_ring_time.isoformat()

        if self.coordinator.called_peer:
            attributes["called_peer"] = self.coordinator.called_peer

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
            call_state = self.coordinator.call_state
            if call_state:
                attributes["call_state"] = call_state
            if call_status and "direction" in call_status:
                attributes["call_direction"] = call_status["direction"]

        return attributes


class TwoNIntercomInput1Sensor(TwoNIntercomEntity, BinarySensorEntity):  # type: ignore[misc]
    """Representation of the real IO input 1 state."""

    _attr_translation_key = "input_1"

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        config_entry: TwoNIntercomConfigEntry,
    ) -> None:
        """Initialize the input sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_input1"

    @staticmethod
    def _is_port_on(io_status: dict[str, Any]) -> bool:
        return is_io_port_on(io_status, "input1")

    @property
    def is_on(self) -> bool:
        """Return true if input 1 is active."""
        return self._is_port_on(self.coordinator.io_status)


class TwoNIntercomIoInputSensor(TwoNIntercomEntity, BinarySensorEntity):  # type: ignore[misc]
    """Representation of a physical IO input, including module tamper ports."""

    _attr_translation_key = "io_input"

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        config_entry: TwoNIntercomConfigEntry,
        port: str,
    ) -> None:
        """Initialize the input sensor with its device port name."""
        super().__init__(coordinator, config_entry)
        self._port = port
        self._attr_unique_id = f"{config_entry.entry_id}_io_{port}"
        self._attr_translation_placeholders = {"port": port}
        if port == "tamper" or port.endswith(".tamper"):
            self._attr_device_class = BinarySensorDeviceClass.TAMPER
            self._attr_translation_key = "io_tamper"

    @property
    def is_on(self) -> bool:
        """Return true if this input is active in the cached device status."""
        return is_io_port_on(self.coordinator.io_status, self._port)


class TwoNIntercomRelay1ActiveSensor(TwoNIntercomEntity, BinarySensorEntity):  # type: ignore[misc]
    """Representation of the relay 1 active state."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "relay_1_active"

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        config_entry: TwoNIntercomConfigEntry,
    ) -> None:
        """Initialize the relay sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_relay1_active"

    @staticmethod
    def _is_switch_active(switch_status: dict[str, Any]) -> bool:
        switches = switch_status.get("switches") or []
        for switch in switches:
            if not isinstance(switch, dict):
                continue
            if switch.get("switch") == 1:
                return switch.get("active") in (1, True, "1", "on", "true")
        return False

    @property
    def is_on(self) -> bool:
        """Return true if relay 1 is active."""
        return self._is_switch_active(self.coordinator.switch_status)


class TwoNIntercomMotionSensor(TwoNIntercomEntity, BinarySensorEntity):  # type: ignore[misc]
    """Motion detection from the 2N camera.

    Driven by ``MotionDetected`` log events pushed from the device.
    Only created when ``/api/system/caps`` reports ``motionDetection``
    as ``"active,licensed"``.
    """

    _attr_device_class = BinarySensorDeviceClass.MOTION

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        config_entry: TwoNIntercomConfigEntry,
    ) -> None:
        """Initialize the motion sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_motion"

    @property
    def is_on(self) -> bool:
        """Return true if motion is detected."""
        return self.coordinator.motion_detected

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attrs: dict[str, Any] = {}
        if self.coordinator.last_motion_time:
            attrs["last_motion"] = self.coordinator.last_motion_time.isoformat()
        return attrs
