"""Credential-free links to the intercom web interface."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .const import (
    CONF_PROTOCOL,
    DEFAULT_PORT_HTTP,
    DEFAULT_PORT_HTTPS,
    DEFAULT_PROTOCOL,
    PROTOCOL_HTTP,
)


def device_web_url(data: Mapping[str, Any]) -> str:
    """Build the web UI URL from connection identity, not behavioral options."""
    protocol = data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL)
    default_port = DEFAULT_PORT_HTTP if protocol == PROTOCOL_HTTP else DEFAULT_PORT_HTTPS
    port = data.get("port", default_port)
    host = str(data["host"]).rsplit("@", 1)[-1].strip("[]")
    if ":" in host:
        host = f"[{host}]"
    authority = host if int(port) == default_port else f"{host}:{port}"
    return f"{protocol}://{authority}/"
