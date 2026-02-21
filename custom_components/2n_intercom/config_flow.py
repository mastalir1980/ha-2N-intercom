"""Config flow for 2N Intercom integration."""
from __future__ import annotations

from typing import Any
import logging
import json
from pathlib import Path

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .api import TwoNIntercomAPI
from .const import (
    CONF_CALLED_ID,
    CONF_DOOR_TYPE,
    CONF_ENABLE_CAMERA,
    CONF_ENABLE_DOORBELL,
    CONF_PROTOCOL,
    CONF_RELAY_COUNT,
    CONF_RELAY_DEVICE_TYPE,
    CONF_RELAY_NAME,
    CONF_RELAY_NUMBER,
    CONF_RELAY_PULSE_DURATION,
    CONF_RELAYS,
    CONF_VERIFY_SSL,
    DEFAULT_ENABLE_CAMERA,
    DEFAULT_ENABLE_DOORBELL,
    DEFAULT_PORT_HTTP,
    DEFAULT_PORT_HTTPS,
    DEFAULT_PROTOCOL,
    DEFAULT_PULSE_DURATION,
    DEFAULT_RELAY_COUNT,
    DEFAULT_VERIFY_SSL,
    DEVICE_TYPE_DOOR,
    DEVICE_TYPE_GATE,
    DOMAIN,
    DOOR_TYPE_DOOR,
    DOOR_TYPE_GATE,
    DOOR_TYPES,
    PROTOCOL_HTTP,
    PROTOCOL_HTTPS,
    PROTOCOLS,
)

_LOGGER = logging.getLogger(__name__)


def _all_calls_label(language: str) -> str:
    if language.startswith("cs"):
        return "Vsechny hovory"
    return "All calls"


class TwoNIntercomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for 2N Intercom."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._relays: list[dict[str, Any]] = []
        self._integration_name: str | None = None
        self._integration_version: str | None = None

    async def _ensure_integration_info(self) -> None:
        """Load and cache integration name/version."""
        if self._integration_name is not None and self._integration_version is not None:
            return

        manifest_path = Path(__file__).resolve().parent / "manifest.json"
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
            self._integration_name = manifest.get("name", "2N Intercom")
            self._integration_version = manifest.get("version", "")
        except (OSError, json.JSONDecodeError):
            self._integration_name = "2N Intercom"
            self._integration_version = ""

    def _name_with_version(self, name: str) -> str:
        """Return name unchanged (version is not appended)."""
        return name

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - connection settings."""
        errors = {}

        if user_input is not None:
            # Validate connection
            try:
                # Determine port based on protocol if not specified
                if CONF_PORT not in user_input:
                    user_input[CONF_PORT] = (
                        DEFAULT_PORT_HTTPS
                        if user_input.get(CONF_PROTOCOL) == PROTOCOL_HTTPS
                        else DEFAULT_PORT_HTTP
                    )

                api = TwoNIntercomAPI(
                    host=user_input[CONF_HOST],
                    port=user_input[CONF_PORT],
                    username=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                    protocol=user_input.get(CONF_PROTOCOL, DEFAULT_PROTOCOL),
                    verify_ssl=user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                )

                # Test connection
                if not await api.async_test_connection():
                    errors["base"] = "cannot_connect"
                else:
                    await api.async_close()
                    # Store data and move to device configuration
                    self._data = user_input
                    return await self.async_step_device()

            except Exception:  # pylint: disable=broad-except
                errors["base"] = "cannot_connect"

        # Default port based on protocol
        default_protocol = (
            user_input.get(CONF_PROTOCOL)
            if user_input is not None
            else DEFAULT_PROTOCOL
        )
        default_port = (
            DEFAULT_PORT_HTTPS
            if default_protocol == PROTOCOL_HTTPS
            else DEFAULT_PORT_HTTP
        )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Required(CONF_PORT, default=default_port): cv.port,
                vol.Required(CONF_PROTOCOL, default=DEFAULT_PROTOCOL): vol.In(
                    PROTOCOLS
                ),
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Required(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle device configuration step."""
        errors = {}

        if user_input is not None:
            self._data.update(user_input)
            
            # If relays are configured, move to relay configuration
            relay_count = user_input.get(CONF_RELAY_COUNT, DEFAULT_RELAY_COUNT)
            if relay_count > 0:
                self._relays = []
                return await self.async_step_relay(relay_index=0)
            else:
                # No relays, create entry
                return await self._async_create_entry()

        await self._ensure_integration_info()
        default_name = self._integration_name or "2N Intercom"
        peers = await self._async_get_called_peers(self._data)
        called_options = [
            {
                "label": _all_calls_label(self.hass.config.language),
                "value": "",
            }
        ] + [{"label": peer, "value": peer} for peer in peers]
        default_called = self._data.get(CONF_CALLED_ID, "")

        called_field = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=called_options,
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )

        data_schema = vol.Schema(
            {
                vol.Required("name", default=default_name): cv.string,
                vol.Required(
                    CONF_ENABLE_CAMERA, default=DEFAULT_ENABLE_CAMERA
                ): cv.boolean,
                vol.Required(
                    CONF_ENABLE_DOORBELL, default=DEFAULT_ENABLE_DOORBELL
                ): cv.boolean,
                vol.Required(
                    CONF_RELAY_COUNT, default=DEFAULT_RELAY_COUNT
                ): vol.In([0, 1, 2, 3, 4]),
                vol.Optional(
                    CONF_CALLED_ID, default=default_called
                ): called_field,
            }
        )

        return self.async_show_form(
            step_id="device",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_relay(
        self, user_input: dict[str, Any] | None = None, relay_index: int = 0
    ) -> FlowResult:
        """Handle relay configuration step."""
        errors = {}
        relay_count = self._data.get(CONF_RELAY_COUNT, DEFAULT_RELAY_COUNT)

        if user_input is not None:
            self._relays.append(user_input)
            
            # Check if we need to configure more relays
            if len(self._relays) < relay_count:
                return await self.async_step_relay(relay_index=len(self._relays))
            else:
                # All relays configured, create entry
                self._data[CONF_RELAYS] = self._relays
                return await self._async_create_entry()

        # relay_index is 0-based, but we show 1-based numbers to users
        relay_display_number = relay_index + 1
        
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_RELAY_NAME, default=f"Relay {relay_display_number}"
                ): cv.string,
                vol.Required(
                    CONF_RELAY_NUMBER, default=relay_display_number
                ): vol.In([1, 2, 3, 4]),
                vol.Required(
                    CONF_RELAY_DEVICE_TYPE, default=DEVICE_TYPE_DOOR
                ): vol.In([DEVICE_TYPE_DOOR, DEVICE_TYPE_GATE]),
                vol.Required(
                    CONF_RELAY_PULSE_DURATION, default=DEFAULT_PULSE_DURATION
                ): cv.positive_int,
            }
        )

        return self.async_show_form(
            step_id="relay",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"relay_number": str(relay_display_number)},
        )

    async def _async_create_entry(self) -> FlowResult:
        """Create the config entry."""
        await self._ensure_integration_info()
        entry_name = self._data.get("name", self._integration_name or "2N Intercom")
        title = self._name_with_version(entry_name)

        await self.async_set_unique_id(
            f"{self._data[CONF_HOST]}_{entry_name}"
        )
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=title,
            data=self._data,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TwoNIntercomOptionsFlow:
        """Get the options flow for this handler."""
        return TwoNIntercomOptionsFlow(config_entry)


class TwoNIntercomOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for 2N Intercom."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._data: dict[str, Any] = {}
        self._relays: list[dict[str, Any]] = []

    def _merged_data(self) -> dict[str, Any]:
        """Return merged config data with options overriding defaults."""
        return {**self._config_entry.data, **self._config_entry.options}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Start full options flow at connection settings."""
        return await self.async_step_user(user_input)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle connection settings in options."""
        errors = {}
        current_data = self._merged_data()

        if user_input is not None:
            try:
                if not user_input.get(CONF_USERNAME):
                    user_input[CONF_USERNAME] = current_data.get(CONF_USERNAME, "")
                if not user_input.get(CONF_PASSWORD):
                    user_input[CONF_PASSWORD] = current_data.get(CONF_PASSWORD, "")

                if CONF_PORT not in user_input:
                    user_input[CONF_PORT] = (
                        DEFAULT_PORT_HTTPS
                        if user_input.get(CONF_PROTOCOL) == PROTOCOL_HTTPS
                        else DEFAULT_PORT_HTTP
                    )

                api = TwoNIntercomAPI(
                    host=user_input[CONF_HOST],
                    port=user_input[CONF_PORT],
                    username=user_input[CONF_USERNAME],
                    password=user_input[CONF_PASSWORD],
                    protocol=user_input.get(CONF_PROTOCOL, DEFAULT_PROTOCOL),
                    verify_ssl=user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                )

                if not await api.async_test_connection():
                    _LOGGER.warning(
                        "Options connection test failed host=%s port=%s protocol=%s verify_ssl=%s",
                        user_input.get(CONF_HOST),
                        user_input.get(CONF_PORT),
                        user_input.get(CONF_PROTOCOL, DEFAULT_PROTOCOL),
                        user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                    )
                    errors["base"] = "cannot_connect"
                else:
                    await api.async_close()
                    self._data = user_input
                    return await self.async_step_device()

            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception(
                    "Options connection test exception host=%s port=%s protocol=%s verify_ssl=%s",
                    user_input.get(CONF_HOST),
                    user_input.get(CONF_PORT),
                    user_input.get(CONF_PROTOCOL, DEFAULT_PROTOCOL),
                    user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                )
                errors["base"] = "cannot_connect"

        default_protocol = (
            user_input.get(CONF_PROTOCOL)
            if user_input is not None
            else current_data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL)
        )
        default_port = current_data.get(CONF_PORT)
        if default_port is None:
            default_port = (
                DEFAULT_PORT_HTTPS
                if default_protocol == PROTOCOL_HTTPS
                else DEFAULT_PORT_HTTP
            )

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST, default=current_data.get(CONF_HOST, "")
                ): cv.string,
                vol.Required(CONF_PORT, default=default_port): cv.port,
                vol.Required(
                    CONF_PROTOCOL, default=default_protocol
                ): vol.In(PROTOCOLS),
                vol.Required(
                    CONF_USERNAME, default=current_data.get(CONF_USERNAME, "")
                ): cv.string,
                vol.Required(
                    CONF_PASSWORD, default=current_data.get(CONF_PASSWORD, "")
                ): cv.string,
                vol.Required(
                    CONF_VERIFY_SSL,
                    default=current_data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                ): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle device configuration step in options."""
        errors = {}
        current_data = self._merged_data()

        peers = await self._async_get_called_peers(current_data)
        called_options = [
            {
                "label": _all_calls_label(self.hass.config.language),
                "value": "",
            }
        ] + [{"label": peer, "value": peer} for peer in peers]
        default_called = current_data.get(CONF_CALLED_ID, "")

        called_field = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=called_options,
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )

        relays = current_data.get(CONF_RELAYS, [])
        derived_door_type = DOOR_TYPE_GATE if any(
            relay.get(CONF_RELAY_DEVICE_TYPE) == DEVICE_TYPE_GATE
            for relay in relays
        ) else DOOR_TYPE_DOOR

        if user_input is not None:
            self._data.update(user_input)

            relay_count = user_input.get(CONF_RELAY_COUNT, DEFAULT_RELAY_COUNT)
            if relay_count > 0:
                self._relays = []
                return await self.async_step_relay(relay_index=0)

            self._data[CONF_RELAYS] = []
            return await self._async_create_entry()

        data_schema = vol.Schema(
            {
                vol.Required(
                    "name",
                    default=current_data.get("name", "2N Intercom"),
                ): cv.string,
                vol.Required(
                    CONF_ENABLE_CAMERA,
                    default=current_data.get(CONF_ENABLE_CAMERA, DEFAULT_ENABLE_CAMERA),
                ): cv.boolean,
                vol.Required(
                    CONF_ENABLE_DOORBELL,
                    default=current_data.get(
                        CONF_ENABLE_DOORBELL, DEFAULT_ENABLE_DOORBELL
                    ),
                ): cv.boolean,
                vol.Required(
                    CONF_RELAY_COUNT,
                    default=current_data.get(CONF_RELAY_COUNT, DEFAULT_RELAY_COUNT),
                ): vol.In([0, 1, 2, 3, 4]),
                vol.Required(
                    CONF_DOOR_TYPE,
                    default=current_data.get(CONF_DOOR_TYPE, derived_door_type),
                ): vol.In(DOOR_TYPES),
                vol.Optional(
                    CONF_CALLED_ID,
                    default=default_called,
                ): called_field,
            }
        )

        return self.async_show_form(
            step_id="device",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_relay(
        self, user_input: dict[str, Any] | None = None, relay_index: int = 0
    ) -> FlowResult:
        """Handle relay configuration step in options."""
        errors = {}
        current_data = self._merged_data()
        relay_count = self._data.get(CONF_RELAY_COUNT, DEFAULT_RELAY_COUNT)
        existing_relays = current_data.get(CONF_RELAYS, [])

        if user_input is not None:
            self._relays.append(user_input)

            if len(self._relays) < relay_count:
                return await self.async_step_relay(relay_index=len(self._relays))

            self._data[CONF_RELAYS] = self._relays
            return await self._async_create_entry()

        relay_display_number = relay_index + 1
        default_relay = (
            existing_relays[relay_index]
            if relay_index < len(existing_relays)
            else {}
        )

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_RELAY_NAME,
                    default=default_relay.get(
                        CONF_RELAY_NAME, f"Relay {relay_display_number}"
                    ),
                ): cv.string,
                vol.Required(
                    CONF_RELAY_NUMBER,
                    default=default_relay.get(
                        CONF_RELAY_NUMBER, relay_display_number
                    ),
                ): vol.In([1, 2, 3, 4]),
                vol.Required(
                    CONF_RELAY_DEVICE_TYPE,
                    default=default_relay.get(
                        CONF_RELAY_DEVICE_TYPE, DEVICE_TYPE_DOOR
                    ),
                ): vol.In([DEVICE_TYPE_DOOR, DEVICE_TYPE_GATE]),
                vol.Required(
                    CONF_RELAY_PULSE_DURATION,
                    default=default_relay.get(
                        CONF_RELAY_PULSE_DURATION, DEFAULT_PULSE_DURATION
                    ),
                ): cv.positive_int,
            }
        )

        return self.async_show_form(
            step_id="relay",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"relay_number": str(relay_display_number)},
        )

    async def _async_create_entry(self) -> FlowResult:
        """Create the options entry."""
        return self.async_create_entry(title="", data=self._data)

    async def _async_get_called_peers(self, data: dict[str, Any]) -> list[str]:
        """Return list of called peers from directory."""
        try:
            api = TwoNIntercomAPI(
                host=data[CONF_HOST],
                port=data.get(CONF_PORT, DEFAULT_PORT_HTTPS),
                username=data.get(CONF_USERNAME, ""),
                password=data.get(CONF_PASSWORD, ""),
                protocol=data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL),
                verify_ssl=data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
            )
            directory = await api.async_get_directory()
            await api.async_close()

            users: list[dict[str, Any]] = []
            if isinstance(directory, list):
                for entry in directory:
                    if isinstance(entry, dict) and "users" in entry:
                        users.extend(entry.get("users") or [])
                    elif isinstance(entry, dict):
                        users.append(entry)
            elif isinstance(directory, dict):
                if "users" in directory:
                    users = directory.get("users", [])
                elif "result" in directory:
                    result = directory.get("result")
                    if isinstance(result, dict):
                        users = result.get("users", [])
                    elif isinstance(result, list):
                        users = result

            peers: list[str] = []
            for user in users:
                for call_pos in user.get("callPos", []) or []:
                    peer = call_pos.get("peer")
                    if peer and peer not in peers:
                        peers.append(peer)

            return peers
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception(
                "Failed to load called peers from dir/query host=%s",
                data.get(CONF_HOST),
            )
            return []
