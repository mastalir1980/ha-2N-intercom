"""Config flow for 2N Intercom integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_DOOR_TYPE,
    DEFAULT_PORT,
    DOMAIN,
    DOOR_TYPE_DOOR,
    DOOR_TYPES,
)


class TwoNIntercomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for 2N Intercom."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input.get("name", "2N Intercom"))
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input.get("name", "2N Intercom"),
                data=user_input,
            )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Optional("name", default="2N Intercom"): cv.string,
                vol.Required(CONF_DOOR_TYPE, default=DOOR_TYPE_DOOR): vol.In(
                    DOOR_TYPES
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
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
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_DOOR_TYPE,
                    default=self.config_entry.options.get(
                        CONF_DOOR_TYPE,
                        self.config_entry.data.get(CONF_DOOR_TYPE, DOOR_TYPE_DOOR),
                    ),
                ): vol.In(DOOR_TYPES),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
        )
