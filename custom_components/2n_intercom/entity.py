"""Shared entity base for 2N Intercom platforms.

Centralises ``device_info``, ``available`` and the ``has_entity_name``
flag so the per-platform entities don't reimplement the same five lines
each. The camera entity does its own thing because it inherits from
``MjpegCamera`` and the multiple inheritance with ``CoordinatorEntity``
already pulls in everything we need (see ``camera.py``).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import TwoNIntercomCoordinator

if TYPE_CHECKING:
    from .coordinator import TwoNIntercomConfigEntry


def io_ports_of_type(
    io_caps: dict[str, Any],
    io_status: dict[str, Any],
    port_type: str,
) -> list[str]:
    """Return distinct ports of the requested type present in caps and status."""
    caps_ports = io_caps.get("ports")
    status_ports = io_status.get("ports")
    if not isinstance(caps_ports, list) or not isinstance(status_ports, list):
        return []
    available = {
        port["port"]
        for port in status_ports
        if isinstance(port, dict) and isinstance(port.get("port"), str)
    }
    ports: list[str] = []
    for cap in caps_ports:
        if not isinstance(cap, dict) or cap.get("type") != port_type:
            continue
        port = cap.get("port")
        if (
            isinstance(port, str)
            and port
            and port in available
            and port not in ports
        ):
            ports.append(port)
    return ports


def is_io_port_on(io_status: dict[str, Any], port_name: str) -> bool:
    """Read a physical port state using the device's supported encodings."""
    ports = io_status.get("ports")
    if not isinstance(ports, list):
        return False
    for port in ports:
        if isinstance(port, dict) and port.get("port") == port_name:
            return port.get("state") in (1, True, "1", "on", "true")
    return False


class TwoNIntercomEntity(CoordinatorEntity[TwoNIntercomCoordinator]):  # type: ignore[misc]
    """Base entity that wires the config entry and shared device info."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TwoNIntercomCoordinator,
        config_entry: TwoNIntercomConfigEntry,
    ) -> None:
        """Initialise the entity with its config entry."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        name: str = config_entry.options.get(
            "name",
            config_entry.data.get("name", "2N Intercom"),
        )
        self._attr_device_info = coordinator.get_device_info(
            config_entry.entry_id, name
        )
