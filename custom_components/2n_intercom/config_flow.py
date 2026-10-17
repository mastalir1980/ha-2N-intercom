"""Config flow for 2N Intercom integration."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import logging
import json
from pathlib import Path
from urllib.parse import urlsplit

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.selector import SelectOptionDict
from homeassistant.helpers.service_info.ssdp import (
    ATTR_UPNP_FRIENDLY_NAME,
    ATTR_UPNP_PRESENTATION_URL,
    ATTR_UPNP_SERIAL,
    SsdpServiceInfo,
)
import homeassistant.helpers.config_validation as cv

from .api import TwoNIntercomAPI, extract_directory_users
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
    CONF_GRANT_ACCESS_USER,
    CONF_LIVE_VIEW_MODE,
    CONF_MAC,
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


def _directory_user_label(language: str, uuid: str, *, unknown: bool = False) -> str:
    """Label directory users whose name cannot be resolved."""
    if language.startswith("cs"):
        return f"Neznámý uživatel ({uuid})" if unknown else f"{uuid} (bez jména)"
    if language.startswith("de"):
        return f"Unbekannter Benutzer ({uuid})" if unknown else f"{uuid} (ohne Namen)"
    return f"Unknown user ({uuid})" if unknown else f"{uuid} (no name)"


def _normalize_mac(mac: str) -> str:
    """Return *mac* as bare uppercase hex, stripping any `:`/`-` separators.

    2N's own ``/api/system/info`` reports it as e.g. ``7c-1e-b3-00-00-00``
    while SSDP's ``serialNumber``/``UDN`` fields report the same address as
    ``7C1EB3000000`` — normalizing both to the same form is what lets SSDP
    discovery recognize an already-configured device regardless of IP.
    """
    return mac.replace(":", "").replace("-", "").strip().upper()


def _read_integration_info(manifest_path: Path) -> tuple[str, str]:
    """Read integration name and version from the manifest."""
    with open(manifest_path, encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)

    return manifest.get("name", "2N Intercom"), manifest.get("version", "")


async def _async_get_called_peers(data: dict[str, Any]) -> list[str]:
    """Return list of called peers from directory."""
    peers, _users, _directory_ok = await _async_get_directory_choices(data)
    return peers


async def _async_get_directory_choices(
    data: dict[str, Any],
) -> tuple[list[str], list[dict[str, str]], bool]:
    """Return ``(called peers, directory users, directory ok)`` from dir/query."""
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
        directory = await api.async_get_directory(raise_on_device_error=True)

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

        return peers, extract_directory_users(users), True
    except Exception:  # pylint: disable=broad-except
        _LOGGER.warning(
            "Failed to load directory from dir/query host=%s",
            data.get(CONF_HOST),
        )
        _LOGGER.debug("Directory lookup failure details", exc_info=True)
        return [], [], False
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
        self._discovered_host: str | None = None
        self._discovered_name: str | None = None

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
                    else:
                        self._data.pop(CONF_SERIAL_NUMBER, None)
                    # Store the MAC independently of serial_number — on
                    # Control4-rebranded units serialNumber is a Control4
                    # part number, not the MAC, so it can't double as the
                    # cross-reference SSDP discovery needs to recognize an
                    # already-configured device regardless of serial scheme.
                    mac_addr = sys_info.get("macAddr")
                    if mac_addr:
                        user_input[CONF_MAC] = _normalize_mac(str(mac_addr))
                    else:
                        self._data.pop(CONF_MAC, None)
                    # Build a descriptive default name from device identity
                    variant = sys_info.get("variant", "").strip()
                    sn = str(serial).strip() if serial else ""
                    if variant and sn:
                        self._default_device_name = f"{variant} {sn}"
                    elif variant:
                        self._default_device_name = variant
                    elif sn:
                        self._default_device_name = f"2N Intercom {sn}"
                    else:
                        self._default_device_name = None
                    self._data.update(user_input)

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

        # Keep submitted connection details when validation fails.
        prefill = user_input or self._data
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST,
                    default=prefill.get(CONF_HOST, self._discovered_host or ""),
                ): cv.string,
                vol.Required(
                    CONF_USERNAME,
                    default=prefill.get(CONF_USERNAME, ""),
                ): cv.string,
                vol.Required(
                    CONF_PASSWORD,
                    default=prefill.get(CONF_PASSWORD, ""),
                ): cv.string,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            last_step=False,
        )

    async def async_step_ssdp(
        self, discovery_info: SsdpServiceInfo
    ) -> ConfigFlowResult:
        """Handle a 2N device discovered via SSDP.

        2N's ``serialNumber``/``UDN`` SSDP fields report the device's MAC
        address, not the same value ``/api/system/info`` calls
        ``serialNumber`` (a Control4 part number on Control4-rebranded
        units) — see ``_normalize_mac`` for why the MAC, not that field,
        is the cross-reference used here.
        """
        upnp = discovery_info.upnp
        raw_mac = upnp.get(ATTR_UPNP_SERIAL)
        if not raw_mac:
            return self.async_abort(reason="no_mac")
        mac = _normalize_mac(str(raw_mac))
        if len(mac) != 12 or any(char not in "0123456789ABCDEF" for char in mac):
            return self.async_abort(reason="no_mac")

        host = None
        for url in (
            upnp.get(ATTR_UPNP_PRESENTATION_URL),
            discovery_info.ssdp_location,
        ):
            if not url:
                continue
            try:
                candidate = urlsplit(str(url)).hostname
            except ValueError:
                continue
            if candidate and not any(char.isspace() for char in candidate):
                host = candidate
                break
        if not host:
            return self.async_abort(reason="no_host")

        # Already configured under the old host — update it in place rather
        # than offering a second setup flow for the same physical device.
        for entry in self._async_current_entries(include_ignore=False):
            if _normalize_mac(str(entry.data.get(CONF_MAC, ""))) == mac:
                old_host = entry.data.get(CONF_HOST)
                if old_host != host:
                    _LOGGER.info(
                        "2N intercom %s moved from %s to %s (SSDP); updating the entry",
                        entry.title,
                        old_host,
                        host,
                    )
                    self.hass.config_entries.async_update_entry(
                        entry, data={**entry.data, CONF_HOST: host}
                    )
                    self.hass.async_create_task(
                        self.hass.config_entries.async_reload(entry.entry_id)
                    )
                return self.async_abort(reason="already_configured")

        # Collapses duplicate in-progress flows if the device announces
        # itself more than once (e.g. on multiple network interfaces).
        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured()

        self._discovered_host = host
        friendly_name = upnp.get(ATTR_UPNP_FRIENDLY_NAME)
        if friendly_name:
            self._discovered_name = str(friendly_name)
        self.context["title_placeholders"] = {
            "name": str(friendly_name) if friendly_name else "2N Intercom",
            "host": host,
        }

        return await self.async_step_user()

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
            self._data.get("name")
            or self._discovered_name
            or self._default_device_name
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
                    CONF_ENABLE_CAMERA,
                    default=self._data.get(CONF_ENABLE_CAMERA, DEFAULT_ENABLE_CAMERA),
                ): cv.boolean,
                vol.Required(
                    CONF_ENABLE_DOORBELL,
                    default=self._data.get(
                        CONF_ENABLE_DOORBELL, DEFAULT_ENABLE_DOORBELL
                    ),
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
            last_step=True,
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
        # Relay overrides collected in this flow session, keyed by physical
        # relay number.
        self._relay_inputs: dict[int, dict[str, Any]] = {}
        self._relay_index = 0
        self._detected_relays: list[dict[str, Any]] = []

    def _current_option(self, key: str, default: Any = None) -> Any:
        """Return current value for a behavioral option.

        Prefers ``entry.options`` (previously saved options-flow output),
        falls back to ``entry.data`` (initial setup values), then *default*.
        """
        if key in self.config_entry.options:
            return self.config_entry.options[key]
        return self.config_entry.data.get(key, default)

    def _session_option(self, key: str, default: Any = None) -> Any:
        """Return the value for *key* preferring this flow session's input.

        Resolution order: values entered in this flow session -> saved
        options -> entry data -> *default*.
        """
        if key in self._data:
            return self._data[key]
        return self._current_option(key, default)

    def _refresh_detected_relays(self) -> None:
        """Refresh auto-detected relays from the running coordinator.

        Reads ``switch_caps`` already fetched by the coordinator — no I/O.
        Empty when the entry isn't loaded or the device exposes no
        enabled switches.
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

        # Relay detection drives both the follow-up steps and the
        # best-effort Next/Submit label below.
        self._refresh_detected_relays()

        # Connection data for the API call to fetch peers lives in entry.data.
        conn_data = dict(self.config_entry.data)
        conn_data[CONF_ALLOW_INSECURE] = self._current_option(
            CONF_ALLOW_INSECURE, DEFAULT_ALLOW_INSECURE
        )
        peers, directory_users, directory_ok = await _async_get_directory_choices(conn_data)
        if not directory_ok and user_input is None:
            errors["base"] = "directory_unavailable"
        called_options: list[SelectOptionDict] = [
            SelectOptionDict(
                label=_all_calls_label(self.hass.config.language),
                value=CALLED_ID_ALL,
            ),
        ] + [SelectOptionDict(label=peer, value=peer) for peer in peers]
        default_called = self._session_option(CONF_CALLED_ID) or CALLED_ID_ALL

        called_field = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=called_options,
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )

        current_grant_user = self._current_option(CONF_GRANT_ACCESS_USER) or None
        grant_user_options: list[SelectOptionDict] = [
            SelectOptionDict(
                label=user["name"] or _directory_user_label(
                    self.hass.config.language, user["uuid"]
                ),
                value=(
                    current_grant_user
                    if current_grant_user
                    and user["uuid"].lower() == current_grant_user.lower()
                    else user["uuid"]
                ),
            )
            for user in directory_users
        ]
        if current_grant_user and not any(
            option["value"] == current_grant_user
            for option in grant_user_options
        ):
            # Keep a stored uuid selectable even if the directory is
            # unreachable or the user has since been removed.
            grant_user_options.append(
                SelectOptionDict(
                    label=_directory_user_label(
                        self.hass.config.language, current_grant_user, unknown=True
                    ),
                    value=current_grant_user,
                )
            )
        grant_user_field = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=grant_user_options,
                mode=selector.SelectSelectorMode.DROPDOWN,
                custom_value=True,
            )
        )

        if user_input is not None:
            grant_user = str(user_input.get(CONF_GRANT_ACCESS_USER) or "").strip()
            if grant_user:
                user_input[CONF_GRANT_ACCESS_USER] = grant_user
            else:
                user_input.pop(CONF_GRANT_ACCESS_USER, None)
            # NumberSelector returns floats; coerce so the int round-trips
            # cleanly into entry.options and the coordinator's int comparison
            # holds.
            if CONF_SCAN_INTERVAL in user_input and user_input[CONF_SCAN_INTERVAL] is not None:
                user_input[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            self._data.update(user_input)

            # If the camera is enabled, surface the camera transport options
            # step so the user can tune live-view mode and MJPEG resolution.
            # Disabling the camera skips it entirely and omits camera values
            # from the saved options.
            if user_input.get(CONF_ENABLE_CAMERA, DEFAULT_ENABLE_CAMERA):
                return await self.async_step_camera()

            for camera_key in (
                CONF_LIVE_VIEW_MODE,
                CONF_CAMERA_SOURCE,
                CONF_MJPEG_WIDTH,
                CONF_MJPEG_HEIGHT,
                CONF_MJPEG_FPS,
                CONF_RTSP_USERNAME,
                CONF_RTSP_PASSWORD,
            ):
                self._data.pop(camera_key, None)

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
                    default=self._session_option("name", "2N Intercom"),
                ): cv.string,
                vol.Required(
                    CONF_ENABLE_CAMERA,
                    default=self._session_option(CONF_ENABLE_CAMERA, DEFAULT_ENABLE_CAMERA),
                ): cv.boolean,
                vol.Required(
                    CONF_ENABLE_DOORBELL,
                    default=self._session_option(
                        CONF_ENABLE_DOORBELL, DEFAULT_ENABLE_DOORBELL
                    ),
                ): cv.boolean,
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self._session_option(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): scan_interval_field,
                vol.Optional(
                    CONF_CALLED_ID,
                    default=default_called,
                ): called_field,
                vol.Optional(
                    CONF_GRANT_ACCESS_USER,
                    description={"suggested_value": current_grant_user},
                ): grant_user_field,
            }
        )

        # Best-effort Next/Submit label: whether another step follows depends
        # on the camera toggle on this very form, which the label cannot
        # react to live. We label from the *current* (session or saved)
        # camera setting plus detected relays.
        has_followup = bool(
            self._session_option(CONF_ENABLE_CAMERA, DEFAULT_ENABLE_CAMERA)
        ) or bool(self._detected_relays)

        return self.async_show_form(
            step_id="device",
            data_schema=data_schema,
            errors=errors,
            last_step=not has_followup,
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
            # RTSP credentials: the password field is a password-type
            # selector that is never pre-filled, so an empty password means
            # "keep the stored one". Clearing the username removes the whole
            # credential pair — without it the integration never tries RTSP
            # and uses MJPEG instead.
            rtsp_username = (user_input.get(CONF_RTSP_USERNAME) or "").strip()
            if not rtsp_username:
                user_input.pop(CONF_RTSP_USERNAME, None)
                user_input.pop(CONF_RTSP_PASSWORD, None)
                self._data.pop(CONF_RTSP_USERNAME, None)
                self._data.pop(CONF_RTSP_PASSWORD, None)
            else:
                user_input[CONF_RTSP_USERNAME] = rtsp_username
                if not user_input.get(CONF_RTSP_PASSWORD):
                    stored_password = self._session_option(CONF_RTSP_PASSWORD, "")
                    if stored_password:
                        user_input[CONF_RTSP_PASSWORD] = stored_password
                    else:
                        user_input.pop(CONF_RTSP_PASSWORD, None)
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
                    default=self._session_option(
                        CONF_LIVE_VIEW_MODE, DEFAULT_LIVE_VIEW_MODE
                    ),
                ): live_view_field,
                vol.Optional(
                    CONF_RTSP_USERNAME,
                    description={
                        "suggested_value": self._session_option(
                            CONF_RTSP_USERNAME, ""
                        ),
                    },
                ): str,
                # Password-type selector without a suggested value: the
                # stored RTSP password is never rendered in clear text.
                # Submitting the field empty keeps the stored password.
                vol.Optional(CONF_RTSP_PASSWORD): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
                vol.Required(
                    CONF_CAMERA_SOURCE,
                    default=self._session_option(
                        CONF_CAMERA_SOURCE, DEFAULT_CAMERA_SOURCE
                    ),
                ): camera_source_field,
                vol.Required(
                    CONF_MJPEG_WIDTH,
                    default=self._session_option(
                        CONF_MJPEG_WIDTH, DEFAULT_CAMERA_MJPEG_WIDTH
                    ),
                ): resolution_field,
                vol.Required(
                    CONF_MJPEG_HEIGHT,
                    default=self._session_option(
                        CONF_MJPEG_HEIGHT, DEFAULT_CAMERA_MJPEG_HEIGHT
                    ),
                ): resolution_field,
                vol.Required(
                    CONF_MJPEG_FPS,
                    default=self._session_option(
                        CONF_MJPEG_FPS, DEFAULT_CAMERA_MJPEG_FPS
                    ),
                ): fps_field,
            }
        )

        return self.async_show_form(
            step_id="camera",
            data_schema=data_schema,
            errors=errors,
            # Relay steps follow when relays were detected.
            last_step=not self._detected_relays,
        )

    def _get_existing_relay_override(self, relay_number: int) -> dict[str, Any]:
        """Return previously saved override for *relay_number*, if any."""
        for relay in self._current_option(CONF_RELAYS, []) or []:
            if isinstance(relay, dict) and relay.get(CONF_RELAY_NUMBER) == relay_number:
                return relay
        return {}

    async def _async_after_camera_step(self) -> ConfigFlowResult:
        """Continue after the (optional) camera step.

        Relays were already detected by the device step; offer per-relay
        overrides (name, device type, pulse duration). If no relays are
        detected or the entry isn't loaded, relay configuration is skipped.
        """
        if not self._detected_relays:
            self._data[CONF_RELAYS] = []
            return await self._async_create_entry()

        return await self.async_step_relay(relay_index=0)

    async def async_step_relay(
        self, user_input: dict[str, Any] | None = None,
        relay_index: int | None = None,
    ) -> ConfigFlowResult:
        """Collect overrides for one auto-detected relay.

        Shows name, device type (door/gate), and pulse duration in a
        single step.  The relay number is fixed — it comes from the
        device's ``/api/switch/caps`` response.

        HA re-invokes this step by ``step_id`` without the ``relay_index``
        argument, so the currently displayed index is tracked on the flow
        instance. Values are stored keyed by physical relay number until
        the final step saves all overrides.
        """
        errors: dict[str, str] = {}

        if relay_index is not None:
            self._relay_index = relay_index

        if user_input is not None:
            index = self._relay_index
            cap = self._detected_relays[index]
            self._relay_inputs[cap["switch"]] = user_input

            if index + 1 < len(self._detected_relays):
                return await self.async_step_relay(relay_index=index + 1)

            self._data[CONF_RELAYS] = [
                self._relay_inputs[cap["switch"]]
                for cap in self._detected_relays
                if cap["switch"] in self._relay_inputs
            ]
            return await self._async_create_entry()

        index = self._relay_index
        cap = self._detected_relays[index]
        relay_number = cap["switch"]
        # Pre-fill from this session's input first, then saved options.
        existing = self._relay_inputs.get(relay_number) or (
            self._get_existing_relay_override(relay_number)
        )

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
            last_step=index == len(self._detected_relays) - 1,
        )

    async def _async_create_entry(self) -> ConfigFlowResult:
        """Create the options entry."""
        self._data[CONF_ALLOW_INSECURE] = self._current_option(
            CONF_ALLOW_INSECURE, DEFAULT_ALLOW_INSECURE
        )
        return self.async_create_entry(title="", data=self._data)
