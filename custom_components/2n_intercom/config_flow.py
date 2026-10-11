"""Config flow for 2N Intercom integration."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import logging
import json
from pathlib import Path

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.selector import SelectOptionDict
import homeassistant.helpers.config_validation as cv

from .api import TwoNIntercomAPI
from .const import (
    CALLED_ID_ALL,
    CAMERA_MJPEG_FPS_MAX,
    CAMERA_MJPEG_FPS_MIN,
    CAMERA_SOURCES,
    CONF_ALLOW_INSECURE,
    CONF_CALLED_ID,
    CONF_CAMERA_SOURCE,
    CONF_ENABLE_CAMERA,
    CONF_ENABLE_DOORBELL,
    CONF_LIVE_VIEW_MODE,
    CONF_MJPEG_FPS,
    CONF_MJPEG_HEIGHT,
    CONF_MJPEG_WIDTH,
    CONF_PROTOCOL,
    CONF_RELAY_DEVICE_TYPE,
    CONF_RELAY_NAME,
    CONF_RELAY_NUMBER,
    CONF_RELAY_PULSE_DURATION,
    CONF_RELAYS,
    CONF_RTSP_PASSWORD,
    CONF_RTSP_USERNAME,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL_NUMBER,
    CONF_VERIFY_SSL,
    DEFAULT_ALLOW_INSECURE,
    DEFAULT_CAMERA_MJPEG_FPS,
    DEFAULT_CAMERA_MJPEG_HEIGHT,
    DEFAULT_CAMERA_MJPEG_WIDTH,
    DEFAULT_CAMERA_SOURCE,
    DEFAULT_ENABLE_CAMERA,
    DEFAULT_ENABLE_DOORBELL,
    DEFAULT_LIVE_VIEW_MODE,
    DEFAULT_PORT_HTTP,
    DEFAULT_PORT_HTTPS,
    DEFAULT_PROTOCOL,
    DEFAULT_PULSE_DURATION,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DEVICE_TYPE_DOOR,
    DEVICE_TYPE_GATE,
    DOMAIN,
    LIVE_VIEW_MODES,
    PROTOCOL_HTTP,
    PROTOCOL_HTTPS,
    PROTOCOLS,
    SCAN_INTERVAL_MAX,
    SCAN_INTERVAL_MIN,
)
from .coordinator import TwoNIntercomRuntimeData

_LOGGER = logging.getLogger(__name__)


def _all_calls_label(language: str) -> str:
    if language.startswith("cs"):
        return "Vsechny hovory"
    return "All calls"


def _read_integration_info(manifest_path: Path) -> tuple[str, str]:
    """Read integration name and version from the manifest."""
    with open(manifest_path, encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)

    return manifest.get("name", "2N Intercom"), manifest.get("version", "")


async def _async_get_called_peers(data: dict[str, Any]) -> list[str]:
    """Return list of called peers from directory."""
    api: TwoNIntercomAPI | None = None
    try:
        api = TwoNIntercomAPI(
            host=data[CONF_HOST],
            port=data.get(CONF_PORT, DEFAULT_PORT_HTTPS),
            username=data.get(CONF_USERNAME, ""),
            password=data.get(CONF_PASSWORD, ""),
            protocol=data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL),
            verify_ssl=data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
            allow_insecure=data.get(CONF_ALLOW_INSECURE, DEFAULT_ALLOW_INSECURE),
        )
        directory = await api.async_get_directory()

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
    finally:
        if api is not None:
            await api.async_close()


class TwoNIntercomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg,misc]
    """Handle a config flow for 2N Intercom."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._integration_name: str | None = None
        self._integration_version: str | None = None
        self._default_device_name: str | None = None
        self._reauth_entry: config_entries.ConfigEntry | None = None
        self._reconfigure_entry: config_entries.ConfigEntry | None = None

    async def _ensure_integration_info(self) -> None:
        """Load and cache integration name/version."""
        if self._integration_name is not None and self._integration_version is not None:
            return

        manifest_path = Path(__file__).resolve().parent / "manifest.json"
        try:
            (
                self._integration_name,
                self._integration_version,
            ) = await self.hass.async_add_executor_job(
                _read_integration_info, manifest_path
            )
        except (OSError, json.JSONDecodeError):
            self._integration_name = "2N Intercom"
            self._integration_version = ""

    def _name_with_version(self, name: str) -> str:
        """Return name unchanged (version is not appended)."""
        return name

    async def _async_try_connect(
        self, host: str, username: str, password: str,
        protocol: str, port: int, verify_ssl: bool,
    ) -> tuple[TwoNIntercomAPI | None, bool]:
        """Try to connect with the given parameters. Returns (api, success)."""
        api = TwoNIntercomAPI(
            host=host, port=port, username=username,
            password=password, protocol=protocol, verify_ssl=verify_ssl,
        )
        try:
            if await api.async_test_connection():
                return api, True
        except Exception:  # pylint: disable=broad-except
            pass
        await api.async_close()
        return None, False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - connection settings.

        Only asks for host, username, and password. Protocol and port are
        auto-detected by trying HTTPS:443 first, then HTTP:80.  The user
        can override via the reconfigure flow if the device uses a
        non-standard combination.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            api: TwoNIntercomAPI | None = None

            try:
                # Auto-detect in order of decreasing security:
                #   1. HTTPS:443 with certificate verification (most secure)
                #   2. HTTPS:443 without verification (self-signed 2N cert —
                #      encrypted in transit, the realistic 2N default)
                #   3. HTTP:80 (plaintext — last resort, warned below)
                # Preferring verify_ssl=True means users with a valid/own-CA
                # certificate get a verified connection instead of being pinned
                # to verify_ssl=False forever.
                for protocol, port, verify_ssl in (
                    (PROTOCOL_HTTPS, DEFAULT_PORT_HTTPS, True),
                    (PROTOCOL_HTTPS, DEFAULT_PORT_HTTPS, False),
                    (PROTOCOL_HTTP, DEFAULT_PORT_HTTP, False),
                ):
                    api, ok = await self._async_try_connect(
                        host, username, password, protocol, port,
                        verify_ssl=verify_ssl,
                    )
                    if ok:
                        user_input[CONF_PROTOCOL] = protocol
                        user_input[CONF_PORT] = port
                        user_input[CONF_VERIFY_SSL] = verify_ssl
                        if protocol == PROTOCOL_HTTP:
                            _LOGGER.warning(
                                "2N host=%s is only reachable over plaintext "
                                "HTTP; credentials are not encrypted in transit. "
                                "Enable HTTPS on the device for a secure "
                                "connection.",
                                host,
                            )
                        break
                else:
                    _LOGGER.warning(
                        "Auto-detect failed for host=%s "
                        "(tried HTTPS:443 verified, HTTPS:443 unverified, HTTP:80)",
                        host,
                    )
                    errors["base"] = "cannot_connect"

                if api is not None and not errors:
                    # Fetch stable device identity for unique-id
                    try:
                        sys_info = await api.async_get_system_info()
                    except Exception:  # pylint: disable=broad-except
                        sys_info = {}
                    serial = (
                        sys_info.get("serialNumber")
                        or sys_info.get("macAddr")
                        or ""
                    )
                    if serial:
                        user_input[CONF_SERIAL_NUMBER] = str(serial).strip()
                    # Build a descriptive default name from device identity
                    variant = sys_info.get("variant", "").strip()
                    sn = str(serial).strip() if serial else ""
                    if variant and sn:
                        self._default_device_name = f"{variant} {sn}"
                    elif variant:
                        self._default_device_name = variant
                    elif sn:
                        self._default_device_name = f"2N Intercom {sn}"
                    self._data = user_input

            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception(
                    "Connection test exception host=%s", host,
                )
                errors["base"] = "cannot_connect"
            finally:
                if api is not None:
                    await api.async_close()

            if not errors:
                return await self.async_step_device()

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST, default=user_input.get(CONF_HOST, "") if user_input else ""
                ): cv.string,
                vol.Required(
                    CONF_USERNAME,
                    default=user_input.get(CONF_USERNAME, "") if user_input else "",
                ): cv.string,
                vol.Required(
                    CONF_PASSWORD,
                    default=user_input.get(CONF_PASSWORD, "") if user_input else "",
                ): cv.string,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle device configuration step.

        Relays are not configured here — the integration auto-discovers
        them from ``/api/switch/caps`` at runtime.  The user can assign
        relay types (door switch / gate cover) and pulse durations in the
        options flow after setup.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self._async_create_entry()

        await self._ensure_integration_info()
        default_name = (
            self._default_device_name
            or self._integration_name
            or "2N Intercom"
        )
        peers = await _async_get_called_peers(self._data)
        called_options: list[SelectOptionDict] = [
            SelectOptionDict(
                label=_all_calls_label(self.hass.config.language),
                value=CALLED_ID_ALL,
            ),
        ] + [SelectOptionDict(label=peer, value=peer) for peer in peers]
        default_called = self._data.get(CONF_CALLED_ID) or CALLED_ID_ALL

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

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthentication when stored credentials stop working."""
        entry_id: str | None = self.context.get("entry_id")
        self._reauth_entry = (
            self.hass.config_entries.async_get_entry(entry_id)
            if entry_id
            else None
        )
        if self._reauth_entry is not None:
            self._data = dict(self._reauth_entry.data)
        else:
            self._data = dict(entry_data)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Prompt the user to confirm or update credentials."""
        errors: dict[str, str] = {}
        existing = self._data
        api: TwoNIntercomAPI | None = None

        if user_input is not None:
            merged = {
                **existing,
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            try:
                api = TwoNIntercomAPI(
                    host=merged[CONF_HOST],
                    port=merged.get(CONF_PORT, DEFAULT_PORT_HTTPS),
                    username=merged[CONF_USERNAME],
                    password=merged[CONF_PASSWORD],
                    protocol=merged.get(CONF_PROTOCOL, DEFAULT_PROTOCOL),
                    verify_ssl=merged.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                    allow_insecure=self._reauth_entry.options.get(
                        CONF_ALLOW_INSECURE,
                        merged.get(CONF_ALLOW_INSECURE, DEFAULT_ALLOW_INSECURE),
                    ) if self._reauth_entry is not None else DEFAULT_ALLOW_INSECURE,
                )
                if not await api.async_test_connection():
                    errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception(
                    "Reauth connection test failed host=%s",
                    merged.get(CONF_HOST),
                )
                errors["base"] = "invalid_auth"
            finally:
                if api is not None:
                    await api.async_close()

            if not errors and self._reauth_entry is not None:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry, data=merged
                )
                await self.hass.config_entries.async_reload(
                    self._reauth_entry.entry_id
                )
                return self.async_abort(reason="reauth_successful")

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_USERNAME,
                    default=existing.get(CONF_USERNAME, ""),
                ): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "host": str(existing.get(CONF_HOST, "")),
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow the user to change host/port/credentials without dropping the entry."""
        entry_id = self.context.get("entry_id")
        self._reconfigure_entry = (
            self.hass.config_entries.async_get_entry(entry_id)
            if entry_id
            else None
        )
        if self._reconfigure_entry is not None:
            self._data = dict(self._reconfigure_entry.data)
        return await self._async_reconfigure_user_step(user_input)

    async def _async_reconfigure_user_step(
        self, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Reuse the user step shape for reconfigure with current values prefilled."""
        errors: dict[str, str] = {}
        api: TwoNIntercomAPI | None = None
        entry = self._reconfigure_entry
        current_allow_insecure = self._data.get(
            CONF_ALLOW_INSECURE, DEFAULT_ALLOW_INSECURE
        )
        if entry is not None:
            current_allow_insecure = entry.options.get(
                CONF_ALLOW_INSECURE, current_allow_insecure
            )

        if user_input is not None:
            try:
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
                    allow_insecure=user_input.get(
                        CONF_ALLOW_INSECURE, current_allow_insecure
                    ),
                )
                if not await api.async_test_connection():
                    errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception(
                    "Reconfigure connection test failed host=%s",
                    user_input.get(CONF_HOST),
                )
                errors["base"] = "cannot_connect"
            finally:
                if api is not None:
                    await api.async_close()

            if not errors and self._reconfigure_entry is not None:
                merged = {**self._data, **user_input}
                allow_insecure = merged.pop(
                    CONF_ALLOW_INSECURE, current_allow_insecure
                )
                self.hass.config_entries.async_update_entry(
                    self._reconfigure_entry,
                    data=merged,
                    options={
                        **self._reconfigure_entry.options,
                        CONF_ALLOW_INSECURE: allow_insecure,
                    },
                )
                await self.hass.config_entries.async_reload(
                    self._reconfigure_entry.entry_id
                )
                return self.async_abort(reason="reconfigure_successful")

        current = self._data
        default_protocol = current.get(CONF_PROTOCOL, DEFAULT_PROTOCOL)
        default_port = current.get(CONF_PORT) or (
            DEFAULT_PORT_HTTPS
            if default_protocol == PROTOCOL_HTTPS
            else DEFAULT_PORT_HTTP
        )
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST, default=current.get(CONF_HOST, "")
                ): cv.string,
                vol.Required(CONF_PORT, default=default_port): cv.port,
                vol.Required(
                    CONF_PROTOCOL, default=default_protocol
                ): vol.In(PROTOCOLS),
                vol.Required(
                    CONF_USERNAME, default=current.get(CONF_USERNAME, "")
                ): cv.string,
                vol.Required(
                    CONF_PASSWORD, default=current.get(CONF_PASSWORD, "")
                ): cv.string,
                vol.Required(
                    CONF_VERIFY_SSL,
                    default=current.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
                ): cv.boolean,
                vol.Required(
                    CONF_ALLOW_INSECURE,
                    default=current_allow_insecure,
                ): cv.boolean,
            }
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
            errors=errors,
        )

    async def _async_create_entry(self) -> ConfigFlowResult:
        """Create the config entry."""
        await self._ensure_integration_info()
        entry_name = self._data.get("name", self._integration_name or "2N Intercom")
        title = self._name_with_version(entry_name)

        # Use device serial/MAC as the unique id so the same physical
        # intercom cannot be added twice, regardless of display name or
        # host/IP changes. Fall back to host when the device did not
        # return a serial (very old firmware).
        serial = self._data.get(CONF_SERIAL_NUMBER)
        unique_id = serial if serial else self._data[CONF_HOST]
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        # Guard against duplicates when an older entry was created with a
        # host-based unique_id before serial support was added. Check all
        # existing entries for the same domain by host or serial overlap.
        new_host = self._data.get(CONF_HOST)
        domain = getattr(self, "handler", "2n_intercom")
        for entry in self.hass.config_entries.async_entries(domain):
            existing_data: Mapping[str, Any] = entry.data or {}
            if serial and existing_data.get(CONF_SERIAL_NUMBER) == serial:
                return self.async_abort(reason="already_configured")
            if new_host and existing_data.get(CONF_HOST) == new_host:
                return self.async_abort(reason="already_configured")

        return self.async_create_entry(
            title=title,
            data=self._data,
        )

    @staticmethod
    @callback  # type: ignore[untyped-decorator]
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TwoNIntercomOptionsFlow:
        """Get the options flow for this handler."""
        return TwoNIntercomOptionsFlow(config_entry)


class TwoNIntercomOptionsFlow(config_entries.OptionsFlow):  # type: ignore[misc]
    """Handle options flow for 2N Intercom.

    The options flow manages **behavioral** preferences only: polling
    interval, feature toggles, relay configuration, camera transport
    settings.  Connection identity (host, port, credentials, SSL) lives
    exclusively in ``entry.data`` and is changed through the reconfigure
    or reauth flows — never through options.  This prevents the
    options-flow output from shadowing a successful reauth/reconfigure.
    """

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow.

        HA 2024.12+ provides ``self.config_entry`` automatically; we accept
        the argument for backward compatibility with the existing
        ``async_get_options_flow`` callable but do not store it.
        """
        del config_entry  # provided by the framework as self.config_entry
        self._data: dict[str, Any] = {}
        self._relays: list[dict[str, Any]] = []
        self._detected_relays: list[dict[str, Any]] = []

    def _current_option(self, key: str, default: Any = None) -> Any:
        """Return current value for a behavioral option.

        Prefers ``entry.options`` (previously saved options-flow output),
        falls back to ``entry.data`` (initial setup values), then *default*.
        """
        if key in self.config_entry.options:
            return self.config_entry.options[key]
        return self.config_entry.data.get(key, default)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start options flow directly at device preferences."""
        return await self.async_step_device(user_input)

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle device configuration step in options."""
        errors: dict[str, str] = {}

        # Connection data for the API call to fetch peers lives in entry.data.
        conn_data = dict(self.config_entry.data)
        conn_data[CONF_ALLOW_INSECURE] = self._current_option(
            CONF_ALLOW_INSECURE, DEFAULT_ALLOW_INSECURE
        )
        peers = await _async_get_called_peers(conn_data)
        called_options: list[SelectOptionDict] = [
            SelectOptionDict(
                label=_all_calls_label(self.hass.config.language),
                value=CALLED_ID_ALL,
            ),
        ] + [SelectOptionDict(label=peer, value=peer) for peer in peers]
        default_called = self._current_option(CONF_CALLED_ID) or CALLED_ID_ALL

        called_field = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=called_options,
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )

        if user_input is not None:
            # NumberSelector returns floats; coerce so the int round-trips
            # cleanly into entry.options and the coordinator's int comparison
            # holds.
            if CONF_SCAN_INTERVAL in user_input and user_input[CONF_SCAN_INTERVAL] is not None:
                user_input[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            self._data.update(user_input)

            # If the camera is enabled, surface the camera transport options
            # step so the user can tune live-view mode and MJPEG resolution.
            # Disabling the camera skips it entirely — the defaults stay as a
            # no-op until the user re-enables.
            if user_input.get(CONF_ENABLE_CAMERA, DEFAULT_ENABLE_CAMERA):
                return await self.async_step_camera()

            return await self._async_after_camera_step()

        scan_interval_field = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=SCAN_INTERVAL_MIN,
                max=SCAN_INTERVAL_MAX,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement="s",
            )
        )

        data_schema = vol.Schema(
            {
                vol.Required(
                    "name",
                    default=self._current_option("name", "2N Intercom"),
                ): cv.string,
                vol.Required(
                    CONF_ENABLE_CAMERA,
                    default=self._current_option(CONF_ENABLE_CAMERA, DEFAULT_ENABLE_CAMERA),
                ): cv.boolean,
                vol.Required(
                    CONF_ENABLE_DOORBELL,
                    default=self._current_option(
                        CONF_ENABLE_DOORBELL, DEFAULT_ENABLE_DOORBELL
                    ),
                ): cv.boolean,
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self._current_option(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): scan_interval_field,
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

    async def async_step_camera(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle camera transport options.

        Lets the user override how the integration talks to the 2N camera —
        live-view mode (auto/rtsp/mjpeg/jpeg-only) and MJPEG stream
        resolution/fps. The defaults match the device's high-res preset, so
        leaving every field untouched preserves the previous behavior. The
        coordinator picks the new values up via ``async_update_options`` →
        ``async_reload``, no manual restart required.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            # Coerce NumberSelector outputs (which arrive as float) to ints
            # so the coordinator's ``isinstance(..., int)`` checks pass and
            # the values round-trip cleanly through entry.options storage.
            for int_key in (CONF_MJPEG_WIDTH, CONF_MJPEG_HEIGHT, CONF_MJPEG_FPS):
                if int_key in user_input and user_input[int_key] is not None:
                    user_input[int_key] = int(user_input[int_key])
            self._data.update(user_input)
            return await self._async_after_camera_step()

        live_view_field = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    SelectOptionDict(label=mode, value=mode) for mode in LIVE_VIEW_MODES
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
                translation_key=CONF_LIVE_VIEW_MODE,
            )
        )

        # Most 2N intercoms expose only the built-in sensor as ``internal``,
        # but the Verso family can mount a secondary camera module reachable
        # as ``external``. We surface both unconditionally — the API resolver
        # falls back to the device's preferred source if a value isn't
        # advertised by ``/api/camera/caps``, so picking the wrong one is a
        # warning at most, not a hard failure.
        camera_source_field = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    SelectOptionDict(label=source, value=source) for source in CAMERA_SOURCES
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
                translation_key=CONF_CAMERA_SOURCE,
            )
        )

        # NumberSelector with a sensible upper bound — 2N caps MJPEG output
        # at the device's max sensor resolution; we don't enforce that here
        # because capabilities are device-specific. The API still validates
        # against ``CameraCapabilities`` and falls back to the closest match.
        resolution_field = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=160,
                max=2592,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
            )
        )

        fps_field = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=CAMERA_MJPEG_FPS_MIN,
                max=CAMERA_MJPEG_FPS_MAX,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
            )
        )

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_LIVE_VIEW_MODE,
                    default=self._current_option(
                        CONF_LIVE_VIEW_MODE, DEFAULT_LIVE_VIEW_MODE
                    ),
                ): live_view_field,
                vol.Optional(
                    CONF_RTSP_USERNAME,
                    description={
                        "suggested_value": self._current_option(
                            CONF_RTSP_USERNAME, ""
                        ),
                    },
                ): str,
                vol.Optional(
                    CONF_RTSP_PASSWORD,
                    description={
                        "suggested_value": self._current_option(
                            CONF_RTSP_PASSWORD, ""
                        ),
                    },
                ): str,
                vol.Required(
                    CONF_CAMERA_SOURCE,
                    default=self._current_option(
                        CONF_CAMERA_SOURCE, DEFAULT_CAMERA_SOURCE
                    ),
                ): camera_source_field,
                vol.Required(
                    CONF_MJPEG_WIDTH,
                    default=self._current_option(
                        CONF_MJPEG_WIDTH, DEFAULT_CAMERA_MJPEG_WIDTH
                    ),
                ): resolution_field,
                vol.Required(
                    CONF_MJPEG_HEIGHT,
                    default=self._current_option(
                        CONF_MJPEG_HEIGHT, DEFAULT_CAMERA_MJPEG_HEIGHT
                    ),
                ): resolution_field,
                vol.Required(
                    CONF_MJPEG_FPS,
                    default=self._current_option(
                        CONF_MJPEG_FPS, DEFAULT_CAMERA_MJPEG_FPS
                    ),
                ): fps_field,
            }
        )

        return self.async_show_form(
            step_id="camera",
            data_schema=data_schema,
            errors=errors,
        )

    def _get_existing_relay_override(self, relay_number: int) -> dict[str, Any]:
        """Return previously saved override for *relay_number*, if any."""
        for relay in self._current_option(CONF_RELAYS, []) or []:
            if isinstance(relay, dict) and relay.get(CONF_RELAY_NUMBER) == relay_number:
                return relay
        return {}

    async def _async_after_camera_step(self) -> ConfigFlowResult:
        """Continue after the (optional) camera step.

        Discovers relays from the running coordinator's switch_caps and
        offers per-relay overrides (name, device type, pulse duration).
        If no relays are detected or the entry isn't loaded, relay
        configuration is skipped.
        """
        runtime: TwoNIntercomRuntimeData | None = getattr(
            self.config_entry, "runtime_data", None
        )
        if runtime is not None:
            caps = runtime.coordinator.switch_caps
            switches = caps.get("switches") or []
            self._detected_relays = [
                s
                for s in switches
                if isinstance(s, dict)
                and s.get("enabled")
                and isinstance(s.get("switch"), int)
            ]
        else:
            self._detected_relays = []

        if not self._detected_relays:
            self._data[CONF_RELAYS] = []
            return await self._async_create_entry()

        self._relays = []
        return await self.async_step_relay(relay_index=0)

    async def async_step_relay(
        self, user_input: dict[str, Any] | None = None, relay_index: int = 0
    ) -> ConfigFlowResult:
        """Collect overrides for one auto-detected relay.

        Shows name, device type (door/gate), and pulse duration in a
        single step.  The relay number is fixed — it comes from the
        device's ``/api/switch/caps`` response.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            self._relays.append(user_input)
            if len(self._relays) < len(self._detected_relays):
                return await self.async_step_relay(
                    relay_index=len(self._relays)
                )
            self._data[CONF_RELAYS] = self._relays
            return await self._async_create_entry()

        cap = self._detected_relays[relay_index]
        relay_number = cap["switch"]
        existing = self._get_existing_relay_override(relay_number)

        # Default pulse from device's switchOnDuration (seconds → ms).
        device_duration_s = cap.get("switchOnDuration")
        if isinstance(device_duration_s, (int, float)) and device_duration_s > 0:
            default_pulse = int(device_duration_s * 1000)
        else:
            default_pulse = DEFAULT_PULSE_DURATION

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_RELAY_NUMBER, default=relay_number
                ): vol.In([relay_number]),
                vol.Required(
                    CONF_RELAY_NAME,
                    default=existing.get(
                        CONF_RELAY_NAME, f"Relay {relay_number}"
                    ),
                ): cv.string,
                vol.Required(
                    CONF_RELAY_DEVICE_TYPE,
                    default=existing.get(
                        CONF_RELAY_DEVICE_TYPE, DEVICE_TYPE_DOOR
                    ),
                ): vol.In([DEVICE_TYPE_DOOR, DEVICE_TYPE_GATE]),
                vol.Required(
                    CONF_RELAY_PULSE_DURATION,
                    default=existing.get(
                        CONF_RELAY_PULSE_DURATION, default_pulse
                    ),
                ): cv.positive_int,
            }
        )

        return self.async_show_form(
            step_id="relay",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"relay_number": str(relay_number)},
        )

    async def _async_create_entry(self) -> ConfigFlowResult:
        """Create the options entry."""
        self._data[CONF_ALLOW_INSECURE] = self._current_option(
            CONF_ALLOW_INSECURE, DEFAULT_ALLOW_INSECURE
        )
        return self.async_create_entry(title="", data=self._data)
