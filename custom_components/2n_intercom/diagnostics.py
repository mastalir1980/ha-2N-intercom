"""Diagnostics support for 2N Intercom.

Implements the HA quality-scale ``diagnostics`` rule: a redacted dump of
the config entry plus the coordinator's cached device payloads, intended
for users to attach to bug reports without leaking credentials or identities.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CALLED_ID,
    CONF_FIRMWARE_CHANNEL,
    CONF_GRANT_ACCESS_USER,
    CONF_MAC,
    CONF_RTSP_PASSWORD,
    CONF_RTSP_USERNAME,
    CONF_SERIAL_NUMBER,
    DEFAULT_FIRMWARE_CHANNEL,
)
from .coordinator import TwoNIntercomRuntimeData

if TYPE_CHECKING:
    from .coordinator import TwoNIntercomConfigEntry

# Credentials and private identifiers. Host/port are intentionally NOT
# redacted because they're load-bearing for any meaningful triage.
TO_REDACT_ENTRY = {
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_RTSP_USERNAME,
    CONF_RTSP_PASSWORD,
    CONF_GRANT_ACCESS_USER,
    CONF_MAC,
    CONF_SERIAL_NUMBER,
    CONF_CALLED_ID,
}
# Directory identities on access events are personal data, not triage data.
TO_REDACT_ACCESS_EVENT = {"user_uuid", "user_name"}
TO_REDACT = TO_REDACT_ENTRY | TO_REDACT_ACCESS_EVENT | {
    "serialNumber",
    "macAddr",
    "called_peer",
    "caller",
    "caller_info",
    "caller_name",
    "caller_number",
}
# Keep only non-identifying phone telemetry; firmware may add identity fields.
PHONE_STATUS_FIELDS = {
    "accountType",
    "enabled",
    "registrationEnabled",
    "registered",
    "registerTime",
    "registrationState",
    "state",
}


def _redact_phone_status(data: Any) -> Any:
    """Retain phone status structure and registration telemetry, not identities."""
    if isinstance(data, list):
        return [_redact_phone_status(value) for value in data]
    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                redacted[key] = _redact_phone_status(value)
            elif key in PHONE_STATUS_FIELDS or (
                key in {"account", "sipAccount"} and type(value) is int
            ):
                redacted[key] = value
            else:
                redacted[key] = REDACTED
        return redacted
    return REDACTED


def _redact_identifier_values(data: Any, pattern: re.Pattern[str]) -> Any:
    """Remove device identifiers embedded in titles, names or other text."""
    if isinstance(data, dict):
        return {
            key: _redact_identifier_values(value, pattern)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [_redact_identifier_values(value, pattern) for value in data]
    if isinstance(data, str):
        return pattern.sub(REDACTED, data)
    return data


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TwoNIntercomConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a 2N Intercom config entry."""
    runtime: TwoNIntercomRuntimeData = entry.runtime_data
    coordinator = runtime.coordinator
    transport = coordinator.camera_transport_info
    last_access_event = coordinator.last_access_event
    log_caps = coordinator.log_caps

    diagnostics = {
        "entry": {
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval is not None
                else None
            ),
            "loaded_platforms": list(runtime.loaded_platforms),
        },
        "device": {
            "system_info": coordinator.system_info,
            "system_caps": coordinator.system_caps,
            "phone_status": _redact_phone_status(coordinator.phone_status),
            "switch_caps": coordinator.switch_caps,
            "switch_status": coordinator.switch_status,
            "io_caps": coordinator.io_caps,
            "io_status": coordinator.io_status,
        },
        "firmware": {
            "installed_version": coordinator.system_info.get("swVersion"),
            "latest_version": runtime.firmware_latest_version,
            "channel": entry.options.get(CONF_FIRMWARE_CHANNEL, DEFAULT_FIRMWARE_CHANNEL),
        },
        "call_state": {
            "active_session_id": coordinator.active_session_id,
            "call_state": coordinator.call_state,
            "ring_active": coordinator.ring_active,
            "called_peer": coordinator.called_peer,
        },
        "motion_detection": {
            "available": coordinator.motion_detection_available,
            "detected": coordinator.motion_detected,
            "last_motion_time": (
                coordinator.last_motion_time.isoformat()
                if coordinator.last_motion_time is not None
                else None
            ),
        },
        "access_control": {
            "log_caps_events": sorted(log_caps) if log_caps is not None else None,
            "subscribed_events": list(coordinator.subscribed_log_events),
            "last_access_event": (
                last_access_event.as_dict()
                if last_access_event is not None
                else None
            ),
        },
        "ring_snapshot": {
            "captured": coordinator.ring_snapshot is not None,
            "time": (
                coordinator.ring_snapshot_time.isoformat()
                if coordinator.ring_snapshot_time is not None
                else None
            ),
        },
        "camera_transport": {
            "requested_mode": transport.requested_mode,
            "selected_mode": transport.selected_mode,
            "resolved": transport.resolved,
            "live_view_available": transport.live_view_available,
            "rtsp_available": transport.rtsp_available,
            "mjpeg_available": transport.mjpeg_available,
            "mjpeg_public_url_available": transport.mjpeg_public_url_available,
            "jpeg_snapshot_available": transport.jpeg_snapshot_available,
            "source": transport.source,
            "mjpeg_width": transport.mjpeg_width,
            "mjpeg_height": transport.mjpeg_height,
            "mjpeg_fps": transport.mjpeg_fps,
            "available_sources": list(transport.capabilities.sources),
        },
    }
    diagnostics = async_redact_data(diagnostics, TO_REDACT)
    identifiers = {
        value.strip()
        for value in (
            entry.data.get(CONF_SERIAL_NUMBER),
            entry.data.get(CONF_MAC),
            coordinator.system_info.get("serialNumber"),
            coordinator.system_info.get("macAddr"),
        )
        if isinstance(value, str) and value.strip()
    }
    if identifiers:
        pattern = re.compile(
            "|".join(
                re.escape(value) for value in sorted(identifiers, key=len, reverse=True)
            ),
            re.IGNORECASE,
        )
        diagnostics = _redact_identifier_values(diagnostics, pattern)
    return diagnostics
