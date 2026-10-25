"""Unit tests for the 2N Intercom config flow.

Covers the user, reauth, and reconfigure entry points. The point is to lock
in the contracts that broke (or got added) during the HA 2026.4+ remediation:

* the **user** step still validates connection and moves to the device step
* a failed connection on the user step shows ``cannot_connect`` and stays on
  the form
* **reauth** pulls the existing entry data, rejects bad creds, accepts good
  ones, updates the entry, and aborts with ``reauth_successful``
* **reconfigure** uses the existing entry, validates the new credentials,
  updates the entry, and aborts with ``reconfigure_successful``
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import json
import logging
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from _stubs import (
    API_PATH,
    CONFIG_FLOW_PATH,
    CONST_PATH,
    REPO_ROOT,
    ensure_package,
    install_api_stubs,
    load_module,
)


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _FormResult(dict):
    """Marker dict so tests can assert on the kind of flow result returned."""


def _install_voluptuous_stub() -> None:
    voluptuous = types.ModuleType("voluptuous")

    class Schema:
        def __init__(self, schema):
            self.schema = schema

    class Required:
        def __init__(self, key, default=None, description=None):
            self.key = key
            self.default = default
            self.description = description

        def __hash__(self) -> int:
            return hash(("required", self.key))

        def __eq__(self, other) -> bool:
            return isinstance(other, Required) and other.key == self.key

    class Optional(Required):
        def __hash__(self) -> int:
            return hash(("optional", self.key))

        def __eq__(self, other) -> bool:
            return isinstance(other, Optional) and other.key == self.key

    class In:
        def __init__(self, options):
            self.options = options

    voluptuous.Schema = Schema
    voluptuous.Required = Required
    voluptuous.Optional = Optional
    voluptuous.In = In
    sys.modules["voluptuous"] = voluptuous


def _install_homeassistant_stubs() -> None:
    ensure_package("homeassistant")

    const = types.ModuleType("homeassistant.const")
    const.CONF_HOST = "host"
    const.CONF_PASSWORD = "password"
    const.CONF_PORT = "port"
    const.CONF_USERNAME = "username"
    sys.modules["homeassistant.const"] = const

    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object

    def callback(func):
        return func

    core.callback = callback
    sys.modules["homeassistant.core"] = core

    data_entry_flow = types.ModuleType("homeassistant.data_entry_flow")
    data_entry_flow.FlowResult = dict
    sys.modules["homeassistant.data_entry_flow"] = data_entry_flow

    config_entries = types.ModuleType("homeassistant.config_entries")

    class _BaseFlow:
        def __init__(self) -> None:
            self.context: dict[str, object] = {}
            self.hass: object | None = None
            self._unique_id: str | None = None

        async def async_set_unique_id(self, unique_id):
            self._unique_id = unique_id
            return None

        def _abort_if_unique_id_configured(self):
            return None

        def async_show_form(
            self,
            *,
            step_id,
            data_schema=None,
            errors=None,
            description_placeholders=None,
            last_step=None,
        ):
            return _FormResult(
                type="form",
                step_id=step_id,
                data_schema=data_schema,
                errors=errors or {},
                description_placeholders=description_placeholders or {},
                last_step=last_step,
            )

        def async_abort(self, *, reason):
            return _FormResult(type="abort", reason=reason)

        def async_create_entry(self, *, title, data):
            return _FormResult(type="create_entry", title=title, data=data)

        def _async_current_entries(self, include_ignore=True):
            return self.hass.config_entries.async_entries("2n_intercom")

    class ConfigFlow(_BaseFlow):
        def __init_subclass__(cls, **kwargs):
            kwargs.pop("domain", None)
            super().__init_subclass__(**kwargs)

    class OptionsFlow(_BaseFlow):
        config_entry = None

    config_entries.ConfigFlow = ConfigFlow
    config_entries.OptionsFlow = OptionsFlow
    config_entries.ConfigEntry = object
    config_entries.ConfigFlowResult = dict
    sys.modules["homeassistant.config_entries"] = config_entries

    helpers = ensure_package("homeassistant.helpers")
    selector_module = types.ModuleType("homeassistant.helpers.selector")

    class SelectSelector:
        def __init__(self, config):
            self.config = config

    class SelectSelectorConfig:
        def __init__(self, *, options, mode, custom_value=False, translation_key=None):
            self.options = options
            self.mode = mode
            self.custom_value = custom_value
            self.translation_key = translation_key

    class SelectSelectorMode:
        DROPDOWN = "dropdown"

    class NumberSelector:
        def __init__(self, config):
            self.config = config

    class NumberSelectorConfig:
        def __init__(self, *, min=0, max=100, step=1, mode="box", unit_of_measurement=None):
            self.min = min
            self.max = max
            self.step = step
            self.mode = mode
            self.unit_of_measurement = unit_of_measurement

    class NumberSelectorMode:
        BOX = "box"

    def SelectOptionDict(*, label: str, value: str) -> dict[str, str]:
        return {"label": label, "value": value}

    class TextSelector:
        def __init__(self, config):
            self.config = config

    class TextSelectorConfig:
        def __init__(self, *, type="text"):
            self.type = type

    class TextSelectorType:
        TEXT = "text"
        PASSWORD = "password"

    selector_module.SelectSelector = SelectSelector
    selector_module.SelectSelectorConfig = SelectSelectorConfig
    selector_module.SelectSelectorMode = SelectSelectorMode
    selector_module.SelectOptionDict = SelectOptionDict
    selector_module.NumberSelector = NumberSelector
    selector_module.NumberSelectorConfig = NumberSelectorConfig
    selector_module.NumberSelectorMode = NumberSelectorMode
    selector_module.TextSelector = TextSelector
    selector_module.TextSelectorConfig = TextSelectorConfig
    selector_module.TextSelectorType = TextSelectorType
    sys.modules["homeassistant.helpers.selector"] = selector_module

    cv_module = types.ModuleType("homeassistant.helpers.config_validation")
    cv_module.string = str
    cv_module.boolean = bool
    cv_module.port = int
    cv_module.positive_int = int
    sys.modules["homeassistant.helpers.config_validation"] = cv_module
    helpers.selector = selector_module
    helpers.config_validation = cv_module

    ensure_package("homeassistant.helpers.service_info")
    ssdp_module = types.ModuleType("homeassistant.helpers.service_info.ssdp")

    class SsdpServiceInfo:
        def __init__(self, *, upnp, ssdp_location=None):
            self.upnp = upnp
            self.ssdp_location = ssdp_location

    ssdp_module.SsdpServiceInfo = SsdpServiceInfo
    ssdp_module.ATTR_UPNP_FRIENDLY_NAME = "friendlyName"
    ssdp_module.ATTR_UPNP_PRESENTATION_URL = "presentationURL"
    ssdp_module.ATTR_UPNP_SERIAL = "serialNumber"
    sys.modules["homeassistant.helpers.service_info.ssdp"] = ssdp_module
    helpers.service_info = ssdp_module


def load_config_flow_module():
    install_api_stubs()
    _install_voluptuous_stub()
    _install_homeassistant_stubs()
    ensure_package("custom_components")
    ensure_package("custom_components.2n_intercom")
    load_module("custom_components.2n_intercom.const", CONST_PATH)
    load_module("custom_components.2n_intercom.api", API_PATH)
    coordinator_module = types.ModuleType("custom_components.2n_intercom.coordinator")
    coordinator_module.TwoNIntercomRuntimeData = object
    sys.modules["custom_components.2n_intercom.coordinator"] = coordinator_module
    return load_module("custom_components.2n_intercom.config_flow", CONFIG_FLOW_PATH)


# ---------------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------------


class FakeAPI:
    """In-memory replacement for ``TwoNIntercomAPI``.

    The flow calls ``async_test_connection``, ``async_get_system_info``,
    ``async_get_directory``, and ``async_close``.
    """

    instances: list["FakeAPI"] = []

    def __init__(
        self,
        *,
        host,
        port,
        username,
        password,
        protocol,
        verify_ssl,
        allow_insecure=False,
        allow_basic_fallback=True,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.protocol = protocol
        self.verify_ssl = verify_ssl
        self.allow_insecure = allow_insecure
        self.allow_basic_fallback = allow_basic_fallback
        self.closed = False
        FakeAPI.instances.append(self)

    async def async_test_connection(self) -> bool:
        return FakeAPI.connection_result

    async def async_get_system_info(self, *, log_errors=True) -> dict:
        return FakeAPI.system_info

    async def async_get_directory(self, *, raise_on_device_error=False):
        return []

    async def async_close(self) -> None:
        self.closed = True


FakeAPI.connection_result = True
FakeAPI.system_info = {"serialNumber": "SN-123456", "macAddr": "00:11:22:33:44:55"}


class FakeConfigEntry:
    def __init__(self, entry_id, data, options=None, domain="2n_intercom") -> None:
        self.entry_id = entry_id
        self.data = data
        self.options = options or {}
        self.domain = domain
        self.title = data.get("name", "Front door")
        self.unique_id = None


class FakeConfigEntries:
    def __init__(self, entries) -> None:
        self._entries = {entry.entry_id: entry for entry in entries}
        self.update_calls: list[tuple[str, dict]] = []
        self.reload_calls: list[str] = []

    def async_get_entry(self, entry_id):
        return self._entries.get(entry_id)

    def async_entries(self, domain=None):
        entries = list(self._entries.values())
        if domain is not None:
            entries = [e for e in entries if getattr(e, "domain", None) == domain]
        return entries

    def async_update_entry(self, entry, *, data=None, options=None, **_kwargs):
        if data is not None:
            entry.data = data
        if options is not None:
            entry.options = options
        self.update_calls.append((entry.entry_id, dict(entry.data)))

    async def async_reload(self, entry_id):
        self.reload_calls.append(entry_id)


class FakeHass:
    def __init__(self, entries) -> None:
        self.config_entries = FakeConfigEntries(entries)
        self.config = types.SimpleNamespace(language="en")
        self.data = {}

    async def async_add_executor_job(self, func, *args):
        return func(*args)

    def async_create_task(self, coro):
        import asyncio

        return asyncio.get_event_loop().create_task(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _form_field_marker(result: dict, key: str):
    """Find the voluptuous marker (Required/Optional) for *key* in a form."""
    for marker in result["data_schema"].schema:
        if getattr(marker, "key", None) == key:
            return marker
    raise AssertionError(f"field {key!r} not found in form {result['step_id']!r}")


def _form_default(result: dict, key: str):
    """Return the pre-filled default of a form field."""
    return _form_field_marker(result, key).default


def _make_runtime(switches: list[dict]):
    """Fake runtime_data carrying switch_caps for relay auto-detection."""
    return type("RT", (), {
        "coordinator": type("C", (), {
            "switch_caps": {"switches": switches}
        })(),
    })()


class ConfigFlowTests(unittest.IsolatedAsyncioTestCase):
    """Lock in user / reauth / reconfigure flow contracts."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config_flow_module = load_config_flow_module()
        # Patch the loaded module's TwoNIntercomAPI symbol so the flow uses
        # our fake instead of the real (network-touching) implementation.
        cls.discovery_api_type = cls.config_flow_module.TwoNIntercomAPI
        cls.config_flow_module.TwoNIntercomAPI = FakeAPI

    def setUp(self) -> None:
        FakeAPI.instances = []
        FakeAPI.connection_result = True

    def _make_flow(self, hass: FakeHass | None = None):
        flow = self.config_flow_module.TwoNIntercomConfigFlow()
        flow.hass = hass or FakeHass([])
        # Real HA's FlowHandler provides `context` as a class-level default
        # (not via __init__), so our own __init__ override never needing to
        # call super() is fine in production — the stub's _BaseFlow.__init__
        # just never runs for a subclass with its own __init__, so set it
        # explicitly here instead.
        flow.context = {}
        return flow

    async def test_user_step_happy_path_advances_to_device(self) -> None:
        flow = self._make_flow()
        result = await flow.async_step_user(
            {
                "host": "192.0.2.20",
                "username": "homeassistant",
                "password": "secret",
            }
        )
        # Successful auth advances to the device step (form, not error).
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "device")
        self.assertEqual(result["errors"], {})
        # Auto-detect stores the discovered protocol/port in _data.
        self.assertEqual(flow._data["protocol"], "https")
        self.assertEqual(flow._data["port"], 443)
        # Secure-by-default: when the device answers on HTTPS, the first
        # candidate (verify_ssl=True) wins, so we pin a *verified* connection
        # instead of disabling TLS verification forever.
        self.assertTrue(flow._data["verify_ssl"])
        # Every API the flow opens is also closed — no resource leaks.
        self.assertGreaterEqual(len(FakeAPI.instances), 1)
        self.assertTrue(all(instance.closed for instance in FakeAPI.instances))

    async def test_user_step_falls_back_to_unverified_https(self) -> None:
        """If cert verification fails, auto-detect drops to unverified HTTPS."""
        flow = self._make_flow()
        attempts: list[tuple[str, int, bool]] = []

        async def fake_try_connect(
            host, username, password, protocol, port, *, verify_ssl
        ):
            attempts.append((protocol, port, verify_ssl))
            # Verified HTTPS fails (e.g. self-signed cert); unverified succeeds.
            if protocol == "https" and verify_ssl:
                return None, False
            api = FakeAPI(
                host=host, port=port, username=username, password=password,
                protocol=protocol, verify_ssl=verify_ssl,
            )
            return api, True

        flow._async_try_connect = fake_try_connect  # type: ignore[assignment]
        result = await flow.async_step_user(
            {"host": "192.0.2.20", "username": "u", "password": "p"}
        )
        self.assertEqual(result["step_id"], "device")
        # Verified HTTPS was tried first, then unverified HTTPS won.
        self.assertEqual(attempts[0], ("https", 443, True))
        self.assertEqual(flow._data["protocol"], "https")
        self.assertEqual(flow._data["port"], 443)
        self.assertFalse(flow._data["verify_ssl"])

    async def test_user_step_http_is_last_resort(self) -> None:
        """Plaintext HTTP is only used when neither HTTPS variant connects."""
        flow = self._make_flow()
        attempts: list[tuple[str, int, bool]] = []

        async def fake_try_connect(
            host, username, password, protocol, port, *, verify_ssl
        ):
            attempts.append((protocol, port, verify_ssl))
            if protocol == "https":
                return None, False
            api = FakeAPI(
                host=host, port=port, username=username, password=password,
                protocol=protocol, verify_ssl=verify_ssl,
            )
            return api, True

        flow._async_try_connect = fake_try_connect  # type: ignore[assignment]
        result = await flow.async_step_user(
            {"host": "192.0.2.20", "username": "u", "password": "p"}
        )
        self.assertEqual(result["step_id"], "device")
        # HTTPS (verified, then unverified) attempted before HTTP.
        self.assertEqual(
            attempts,
            [("https", 443, True), ("https", 443, False), ("http", 80, False)],
        )
        self.assertEqual(flow._data["protocol"], "http")
        self.assertEqual(flow._data["port"], 80)

    async def test_user_step_failed_connection_keeps_form_with_error(self) -> None:
        FakeAPI.connection_result = False
        flow = self._make_flow()
        result = await flow.async_step_user(
            {
                "host": "192.0.2.20",
                "username": "homeassistant",
                "password": "wrong",
            }
        )
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "user")
        self.assertEqual(result["errors"], {"base": "cannot_connect"})

    async def test_user_step_remembers_basic_refusal_across_candidates(self) -> None:
        flow = self._make_flow()
        attempts = []

        async def test_connection(api):
            attempts.append((api.protocol, api.verify_ssl, api.allow_insecure))
            if api.protocol == "https" and not api.verify_ssl:
                raise self.config_flow_module.TwoNInsecureAuthRefusedError("refused")
            return False

        submitted = {"host": "intercom.local", "username": "user", "password": "secret"}
        with patch.object(FakeAPI, "async_test_connection", test_connection):
            result = await flow.async_step_user(dict(submitted))
        self.assertEqual(attempts, [
            ("https", True, False), ("https", False, False), ("http", False, False),
        ])
        self.assertEqual(result["step_id"], "user")
        self.assertEqual(result["errors"], {"base": "basic_auth_refused"})
        self.assertEqual(
            {marker.key for marker in result["data_schema"].schema},
            {"host", "username", "password"},
        )
        self.assertEqual(_form_default(result, "host"), "intercom.local")
        self.assertTrue(all(api.closed for api in FakeAPI.instances))
        self.assertEqual(flow._data, {})

        # A new submission must not inherit the preceding attempt's refusal.
        FakeAPI.connection_result = False
        result = await flow.async_step_user(dict(submitted))
        self.assertEqual(result["errors"], {"base": "cannot_connect"})

    async def test_user_step_later_success_takes_precedence_over_refusal(self) -> None:
        flow = self._make_flow()

        async def test_connection(api):
            if api.protocol == "https" and not api.verify_ssl:
                raise self.config_flow_module.TwoNInsecureAuthRefusedError("refused")
            return api.protocol == "http"

        with patch.object(FakeAPI, "async_test_connection", test_connection):
            result = await flow.async_step_user({
                "host": "intercom.local", "username": "user", "password": "secret",
            })
        self.assertEqual(result["step_id"], "device")
        self.assertEqual(result["errors"], {})
        self.assertEqual(flow._data["protocol"], "http")
        self.assertTrue(all(api.closed for api in FakeAPI.instances))

    async def test_reauth_basic_refusal_is_not_invalid_credentials(self) -> None:
        for protocol in ("http", "https"):
            with self.subTest(protocol=protocol):
                entry = FakeConfigEntry("entry-1", {
                    "host": "intercom.local", "username": "user", "password": "old",
                    "port": 443 if protocol == "https" else 80,
                    "protocol": protocol, "verify_ssl": False,
                })
                hass = FakeHass([entry])
                flow = self._make_flow(hass)
                flow.context = {"entry_id": entry.entry_id}
                await flow.async_step_reauth(entry.data)
                with patch.object(
                    FakeAPI, "async_test_connection",
                    side_effect=self.config_flow_module.TwoNInsecureAuthRefusedError("refused"),
                ):
                    result = await flow.async_step_reauth_confirm({
                        "username": "user", "password": "new",
                    })
                self.assertEqual(result["errors"], {"base": "basic_auth_refused"})
                self.assertEqual(entry.data["password"], "old")
                self.assertEqual(hass.config_entries.update_calls, [])
                self.assertEqual(hass.config_entries.reload_calls, [])
                self.assertTrue(FakeAPI.instances[-1].closed)

    async def test_reconfigure_basic_refusal_then_explicit_opt_in(self) -> None:
        for protocol in ("http", "https"):
            with self.subTest(protocol=protocol):
                entry = FakeConfigEntry("entry-1", {
                    "host": "intercom.local", "username": "user", "password": "secret",
                    "port": 443 if protocol == "https" else 80,
                    "protocol": protocol, "verify_ssl": False,
                }, options={"scan_interval": 120})
                hass = FakeHass([entry])
                flow = self._make_flow(hass)
                flow.context = {"entry_id": entry.entry_id}

                async def test_connection(api):
                    if not api.allow_insecure:
                        raise self.config_flow_module.TwoNInsecureAuthRefusedError("refused")
                    return True

                with patch.object(FakeAPI, "async_test_connection", test_connection):
                    result = await flow.async_step_reconfigure({
                        **entry.data, "allow_insecure": False,
                    })
                    self.assertEqual(result["errors"], {"base": "basic_auth_refused"})
                    self.assertEqual(hass.config_entries.update_calls, [])
                    self.assertEqual(hass.config_entries.reload_calls, [])
                    self.assertTrue(FakeAPI.instances[-1].closed)

                    result = await flow.async_step_reconfigure({
                        **entry.data, "allow_insecure": True,
                    })
                    self.assertEqual(result["reason"], "reconfigure_successful")
                    self.assertEqual(entry.options, {
                        "scan_interval": 120, "allow_insecure": True,
                    })
                    self.assertNotIn("allow_insecure", entry.data)

                    flow = self._make_flow(hass)
                    flow.context = {"entry_id": entry.entry_id}
                    await flow.async_step_reauth(entry.data)
                    result = await flow.async_step_reauth_confirm({
                        "username": "user", "password": "new",
                    })
                    self.assertEqual(result["reason"], "reauth_successful")
                    self.assertTrue(FakeAPI.instances[-1].allow_insecure)
                    self.assertTrue(FakeAPI.instances[-1].closed)

    async def test_user_step_stores_normalized_mac_separately_from_serial(self) -> None:
        flow = self._make_flow()
        with patch.object(FakeAPI, "system_info", {
            "serialNumber": "SN-123456", "macAddr": "00:11:22:aa:bb:cc",
        }):
            await flow.async_step_user(
                {"host": "192.0.2.20", "username": "user", "password": "secret"}
            )
        result = await flow.async_step_device({"name": "Front door"})
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["mac_address"], "001122AABBCC")
        self.assertEqual(result["data"]["serial_number"], "SN-123456")
        self.assertEqual(flow._unique_id, "SN-123456")

    async def test_reauth_keeps_mac_address(self) -> None:
        entry = FakeConfigEntry("entry-1", {
            "host": "192.0.2.20", "username": "user", "password": "old",
            "mac_address": "001122AABBCC", "serial_number": "SN-123456",
        })
        flow = self._make_flow(FakeHass([entry]))
        flow.context = {"entry_id": entry.entry_id}
        await flow.async_step_reauth(entry.data)
        result = await flow.async_step_reauth_confirm(
            {"username": "user", "password": "new"}
        )
        self.assertEqual(result["reason"], "reauth_successful")
        self.assertEqual(entry.data["mac_address"], "001122AABBCC")
        self.assertEqual(entry.data["serial_number"], "SN-123456")
        self.assertNotIn("mac_address", entry.options)

    async def test_reconfigure_keeps_mac_address(self) -> None:
        entry = FakeConfigEntry("entry-1", {
            "host": "192.0.2.20", "username": "user", "password": "secret",
            "mac_address": "001122AABBCC", "serial_number": "SN-123456",
        })
        flow = self._make_flow(FakeHass([entry]))
        flow.context = {"entry_id": entry.entry_id}
        result = await flow.async_step_reconfigure({
            "host": "192.0.2.21", "username": "user", "password": "secret",
            "protocol": "https", "port": 443, "verify_ssl": True,
        })
        self.assertEqual(result["reason"], "reconfigure_successful")
        self.assertEqual(entry.data["host"], "192.0.2.21")
        self.assertEqual(entry.data["mac_address"], "001122AABBCC")
        self.assertEqual(entry.data["serial_number"], "SN-123456")
        self.assertNotIn("mac_address", entry.options)

    async def test_reauth_confirm_with_valid_credentials_updates_and_aborts(
        self,
    ) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {
                "host": "192.0.2.20",
                "port": 443,
                "protocol": "https",
                "username": "homeassistant",
                "password": "old-secret",
                "verify_ssl": False,
            },
        )
        hass = FakeHass([entry])
        flow = self._make_flow(hass)
        flow.context = {"entry_id": entry.entry_id}

        # async_step_reauth pulls the existing entry data, then forwards
        # to the confirmation step which renders the form.
        first = await flow.async_step_reauth(entry.data)
        self.assertEqual(first["type"], "form")
        self.assertEqual(first["step_id"], "reauth_confirm")
        # The flow exposes the host as a description placeholder so the user
        # knows which device they're updating credentials for.
        self.assertEqual(
            first["description_placeholders"].get("host"), "192.0.2.20"
        )

        # Submit valid creds → entry is updated, reload kicked off, aborted
        # with reauth_successful.
        result = await flow.async_step_reauth_confirm(
            {"username": "homeassistant", "password": "new-secret"}
        )
        self.assertEqual(result["type"], "abort")
        self.assertEqual(result["reason"], "reauth_successful")
        self.assertEqual(
            hass.config_entries.update_calls,
            [
                (
                    "entry-1",
                    {
                        "host": "192.0.2.20",
                        "port": 443,
                        "protocol": "https",
                        "username": "homeassistant",
                        "password": "new-secret",
                        "verify_ssl": False,
                    },
                )
            ],
        )
        self.assertEqual(hass.config_entries.reload_calls, ["entry-1"])

    async def test_reauth_confirm_with_bad_credentials_shows_invalid_auth(
        self,
    ) -> None:
        FakeAPI.connection_result = False
        entry = FakeConfigEntry(
            "entry-1",
            {
                "host": "192.0.2.20",
                "port": 443,
                "protocol": "https",
                "username": "homeassistant",
                "password": "old",
                "verify_ssl": False,
            },
        )
        hass = FakeHass([entry])
        flow = self._make_flow(hass)
        flow.context = {"entry_id": entry.entry_id}

        await flow.async_step_reauth(entry.data)
        result = await flow.async_step_reauth_confirm(
            {"username": "homeassistant", "password": "still-wrong"}
        )
        # No update, no reload, form re-rendered with invalid_auth.
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"], {"base": "invalid_auth"})
        self.assertEqual(hass.config_entries.update_calls, [])
        self.assertEqual(hass.config_entries.reload_calls, [])

    async def test_reconfigure_with_valid_credentials_updates_and_aborts(
        self,
    ) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {
                "host": "192.0.2.20",
                "port": 443,
                "protocol": "https",
                "username": "homeassistant",
                "password": "secret",
                "verify_ssl": False,
            },
        )
        hass = FakeHass([entry])
        flow = self._make_flow(hass)
        flow.context = {"entry_id": entry.entry_id}

        # First call (no input) renders the form prefilled with entry data.
        first = await flow.async_step_reconfigure(None)
        self.assertEqual(first["type"], "form")
        self.assertEqual(first["step_id"], "reconfigure")

        # Submit a changed host; flow validates and updates the entry.
        result = await flow.async_step_reconfigure(
            {
                "host": "192.0.2.21",
                "port": 443,
                "protocol": "https",
                "username": "homeassistant",
                "password": "secret",
                "verify_ssl": False,
            }
        )
        self.assertEqual(result["type"], "abort")
        self.assertEqual(result["reason"], "reconfigure_successful")
        self.assertEqual(len(hass.config_entries.update_calls), 1)
        updated_entry_id, updated_data = hass.config_entries.update_calls[0]
        self.assertEqual(updated_entry_id, "entry-1")
        self.assertEqual(updated_data["host"], "192.0.2.21")
        self.assertEqual(hass.config_entries.reload_calls, ["entry-1"])

    async def test_reconfigure_with_failed_connection_does_not_update(
        self,
    ) -> None:
        FakeAPI.connection_result = False
        entry = FakeConfigEntry(
            "entry-1",
            {
                "host": "192.0.2.20",
                "port": 443,
                "protocol": "https",
                "username": "homeassistant",
                "password": "secret",
                "verify_ssl": False,
            },
        )
        hass = FakeHass([entry])
        flow = self._make_flow(hass)
        flow.context = {"entry_id": entry.entry_id}

        await flow.async_step_reconfigure(None)
        result = await flow.async_step_reconfigure(
            {
                "host": "192.0.2.99",
                "port": 443,
                "protocol": "https",
                "username": "homeassistant",
                "password": "secret",
                "verify_ssl": False,
            }
        )
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"], {"base": "cannot_connect"})
        self.assertEqual(hass.config_entries.update_calls, [])
        self.assertEqual(hass.config_entries.reload_calls, [])

    async def test_reconfigure_stores_and_forwards_insecure_opt_in(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {
                "host": "192.0.2.20", "port": 80, "protocol": "http",
                "username": "user", "password": "pass", "verify_ssl": False,
            },
            options={"scan_interval": 120},
        )
        flow = self._make_flow(FakeHass([entry]))
        flow.context = {"entry_id": entry.entry_id}

        for allow_insecure in (True, False):
            with self.subTest(allow_insecure=allow_insecure):
                result = await flow.async_step_reconfigure(
                    {**entry.data, "allow_insecure": allow_insecure}
                )
                self.assertEqual(result["reason"], "reconfigure_successful")
                self.assertEqual(FakeAPI.instances[-1].allow_insecure, allow_insecure)
                self.assertNotIn("allow_insecure", entry.data)
                self.assertEqual(entry.options, {
                    "scan_interval": 120, "allow_insecure": allow_insecure,
                })
                form = await flow.async_step_reconfigure(None)
                defaults = {
                    key.key: key.default for key in form["data_schema"].schema
                }
                self.assertEqual(defaults["allow_insecure"], allow_insecure)

    async def test_reauth_preserves_insecure_opt_in(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {
                "host": "192.0.2.20", "port": 80, "protocol": "http",
                "username": "user", "password": "old", "verify_ssl": False,
            },
            options={"allow_insecure": True},
        )
        flow = self._make_flow(FakeHass([entry]))
        flow.context = {"entry_id": entry.entry_id}
        await flow.async_step_reauth(entry.data)
        result = await flow.async_step_reauth_confirm(
            {"username": "user", "password": "new"}
        )
        self.assertEqual(result["reason"], "reauth_successful")
        self.assertTrue(FakeAPI.instances[-1].allow_insecure)
        self.assertEqual(entry.options, {"allow_insecure": True})
        self.assertNotIn("allow_insecure", entry.data)

    # --- Device step tests ---

    async def test_device_step_no_relays_creates_entry(self) -> None:
        flow = self._make_flow()
        flow._data = {
            "host": "192.0.2.20",
            "port": 443,
            "protocol": "https",
            "username": "user",
            "password": "pass",
            "verify_ssl": False,
            "serial_number": "SN-123456",
        }
        result = await flow.async_step_device(
            {
                "name": "My Intercom",
                "enable_camera": True,
                "enable_doorbell": True,
                "relay_count": 0,
                "called_id": "__all__",
            }
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["title"], "My Intercom")

    async def test_device_step_creates_entry_directly(self) -> None:
        """Device step creates entry immediately — no relay steps."""
        flow = self._make_flow()
        flow._data = {
            "host": "192.0.2.20",
            "port": 443,
            "protocol": "https",
            "username": "user",
            "password": "pass",
            "verify_ssl": False,
            "serial_number": "SN-123456",
        }
        result = await flow.async_step_device(
            {
                "name": "Intercom",
                "enable_camera": True,
                "enable_doorbell": True,
                "called_id": "__all__",
            }
        )
        self.assertEqual(result["type"], "create_entry")

    async def test_device_step_renders_form_when_no_input(self) -> None:
        flow = self._make_flow()
        flow._data = {
            "host": "192.0.2.20",
            "port": 443,
            "username": "user",
            "password": "pass",
        }
        result = await flow.async_step_device(None)
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "device")

    # --- Unique ID uses serial ---

    async def test_unique_id_uses_serial_number(self) -> None:
        FakeAPI.system_info = {"serialNumber": "SERIAL-ABC"}
        flow = self._make_flow()
        await flow.async_step_user(
            {
                "host": "192.0.2.20",
                "port": 443,
                "protocol": "https",
                "username": "user",
                "password": "pass",
                "verify_ssl": False,
            }
        )
        self.assertEqual(flow._data.get("serial_number"), "SERIAL-ABC")

    async def test_unique_id_falls_back_to_mac(self) -> None:
        FakeAPI.system_info = {"macAddr": "AA:BB:CC:DD:EE:FF"}
        flow = self._make_flow()
        await flow.async_step_user(
            {
                "host": "192.0.2.20",
                "port": 443,
                "protocol": "https",
                "username": "user",
                "password": "pass",
                "verify_ssl": False,
            }
        )
        self.assertEqual(flow._data.get("serial_number"), "AA:BB:CC:DD:EE:FF")

    async def test_unique_id_falls_back_to_host_when_no_serial(self) -> None:
        FakeAPI.system_info = {}
        flow = self._make_flow()
        flow._data = {
            "host": "192.0.2.20",
            "port": 443,
            "protocol": "https",
            "username": "user",
            "password": "pass",
            "verify_ssl": False,
        }
        # Complete the device step to trigger _async_create_entry
        result = await flow.async_step_device(
            {
                "name": "Intercom",
                "enable_camera": False,
                "enable_doorbell": False,
                "relay_count": 0,
            }
        )
        self.assertEqual(result["type"], "create_entry")
        # The unique id should have been set; since no serial, it uses host
        self.assertIsNotNone(flow._unique_id)

    # --- User step edge cases ---

    async def test_user_step_shows_form_when_no_input(self) -> None:
        flow = self._make_flow()
        result = await flow.async_step_user(None)
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "user")

    async def test_user_step_exception_shows_connect_error(self) -> None:
        """An exception during connection test should show cannot_connect."""
        config_flow_mod = self.config_flow_module

        class ExplodingAPI(FakeAPI):
            async def async_test_connection(self):
                raise RuntimeError("boom")

        original = config_flow_mod.TwoNIntercomAPI
        config_flow_mod.TwoNIntercomAPI = ExplodingAPI
        try:
            flow = self._make_flow()
            result = await flow.async_step_user(
                {
                    "host": "192.0.2.20",
                    "port": 443,
                    "protocol": "https",
                    "username": "user",
                    "password": "pass",
                    "verify_ssl": False,
                }
            )
            self.assertEqual(result["type"], "form")
            self.assertEqual(result["errors"], {"base": "cannot_connect"})
        finally:
            config_flow_mod.TwoNIntercomAPI = original

    # --- Reauth reads only entry.data, not options ---

    async def test_reauth_does_not_merge_options(self) -> None:
        """Reauth should only use entry.data, not entry.options."""
        entry = FakeConfigEntry(
            "entry-1",
            {
                "host": "192.0.2.20",
                "port": 443,
                "protocol": "https",
                "username": "homeassistant",
                "password": "old",
                "verify_ssl": False,
            },
            options={"host": "stale-option-host"},
        )
        hass = FakeHass([entry])
        flow = self._make_flow(hass)
        flow.context = {"entry_id": entry.entry_id}

        await flow.async_step_reauth(entry.data)
        # The flow's _data should come from entry.data, not merged with options
        self.assertEqual(flow._data["host"], "192.0.2.20")

    # --- Duplicate detection tests ---

    async def test_duplicate_host_aborts_even_with_different_unique_id(self) -> None:
        """Adding a device with the same host as an existing entry should abort.

        This catches the case where an old entry uses a host-based unique_id
        and a new entry would get a serial-based unique_id.
        """
        existing = FakeConfigEntry(
            "old-entry",
            {"host": "192.0.2.20", "name": "IP Verso"},
        )
        hass = FakeHass([existing])
        flow = self._make_flow(hass)
        flow._data = {
            "host": "192.0.2.20",
            "port": 443,
            "protocol": "https",
            "username": "user",
            "password": "pass",
            "verify_ssl": False,
            "serial_number": "SN-NEW-SERIAL",
        }
        result = await flow.async_step_device(
            {
                "name": "My Intercom",
                "enable_camera": True,
                "enable_doorbell": True,
                "relay_count": 0,
                "called_id": "__all__",
            }
        )
        self.assertEqual(result["type"], "abort")
        self.assertEqual(result["reason"], "already_configured")

    async def test_user_step_shows_next_device_step_shows_submit(self) -> None:
        """Setup flow: user step is followed by device, so it shows Next."""
        flow = self._make_flow()
        result = await flow.async_step_user(None)
        self.assertEqual(result["step_id"], "user")
        self.assertIs(result["last_step"], False)
        self.assertNotIn(
            "go_back", {marker.key for marker in result["data_schema"].schema}
        )

        result = await flow.async_step_user(
            {"host": "192.0.2.20", "username": "u", "password": "p"}
        )
        self.assertEqual(result["step_id"], "device")
        self.assertIs(result["last_step"], True)
        self.assertNotIn(
            "go_back", {marker.key for marker in result["data_schema"].schema}
        )

    async def test_device_step_finishes_setup_without_rechecking_connection(self) -> None:
        """The device step saves setup instead of returning to connection."""
        flow = self._make_flow()
        await flow.async_step_user(
            {"host": "192.0.2.20", "username": "homeassistant", "password": "secret"}
        )
        instances_after_connect = len(FakeAPI.instances)

        result = await flow.async_step_device(
            {
                "name": "Front door",
                "enable_camera": True,
                "enable_doorbell": True,
            }
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["name"], "Front door")
        self.assertEqual(result["data"]["host"], "192.0.2.20")
        self.assertEqual(result["data"]["username"], "homeassistant")
        self.assertEqual(result["data"]["password"], "secret")
        self.assertNotIn("go_back", result["data"])
        self.assertEqual(len(FakeAPI.instances), instances_after_connect)

    async def test_restarting_setup_for_other_host_uses_new_device_identity(
        self,
    ) -> None:
        """A fresh flow does not inherit a discarded flow's device identity."""
        original_info = FakeAPI.system_info
        try:
            FakeAPI.system_info = {"serialNumber": "SN-FIRST", "variant": "IP Verso"}
            flow = self._make_flow()
            await flow.async_step_user(
                {"host": "192.0.2.20", "username": "u", "password": "p"}
            )
            self.assertEqual(flow._data["serial_number"], "SN-FIRST")
            self.assertEqual(flow._default_device_name, "IP Verso SN-FIRST")

            flow = self._make_flow()
            result = await flow.async_step_user(None)
            self.assertEqual(result["step_id"], "user")
            self.assertEqual(_form_default(result, "host"), "")
            self.assertEqual(flow._data, {})

            FakeAPI.system_info = {}
            result = await flow.async_step_user(
                {"host": "192.0.2.21", "username": "u", "password": "p"}
            )
            self.assertEqual(result["step_id"], "device")
            self.assertNotIn("serial_number", flow._data)
            self.assertIsNone(flow._default_device_name)

            result = await flow.async_step_device(
                {
                    "name": "Front door",
                    "enable_camera": False,
                    "enable_doorbell": True,
                }
            )
            self.assertEqual(result["type"], "create_entry")
            self.assertEqual(flow._unique_id, "192.0.2.21")
            self.assertNotIn("serial_number", result["data"])
        finally:
            FakeAPI.system_info = original_info

    async def test_duplicate_serial_aborts_even_with_different_host(self) -> None:
        """Adding a device with the same serial but different host should abort."""
        existing = FakeConfigEntry(
            "old-entry",
            {"host": "192.0.2.99", "serial_number": "SN-123456"},
        )
        hass = FakeHass([existing])
        flow = self._make_flow(hass)
        flow._data = {
            "host": "192.0.2.20",
            "port": 443,
            "protocol": "https",
            "username": "user",
            "password": "pass",
            "verify_ssl": False,
            "serial_number": "SN-123456",
        }
        result = await flow.async_step_device(
            {
                "name": "My Intercom",
                "enable_camera": True,
                "enable_doorbell": True,
                "relay_count": 0,
                "called_id": "__all__",
            }
        )
        self.assertEqual(result["type"], "abort")
        self.assertEqual(result["reason"], "already_configured")

    # --- SSDP discovery ---

    def _make_ssdp_info(
        self,
        *,
        mac: str = "7C1EB3000000",
        host: str = "192.0.2.60",
        friendly_name: str | None = "Control4 DS2 Door Station",
        via_location: bool = False,
    ):
        SsdpServiceInfo = sys.modules[
            "homeassistant.helpers.service_info.ssdp"
        ].SsdpServiceInfo
        upnp: dict[str, str] = {}
        if mac:
            upnp["serialNumber"] = mac
        if friendly_name:
            upnp["friendlyName"] = friendly_name
        ssdp_location = None
        if via_location:
            ssdp_location = f"http://{host}/ssdp_server/description.xml"
        else:
            upnp["presentationURL"] = f"http://{host}"
        return SsdpServiceInfo(upnp=upnp, ssdp_location=ssdp_location)

    async def test_ssdp_new_device_advances_to_user_step(self) -> None:
        flow = self._make_flow()
        result = await flow.async_step_ssdp(self._make_ssdp_info())
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "user")
        self.assertEqual(flow._discovered_host, "192.0.2.60")
        self.assertEqual(_form_default(result, "host"), "192.0.2.60")
        self.assertEqual(flow.context["title_placeholders"], {
            "name": "Control4 DS2 Door Station", "host": "192.0.2.60",
        })
        result = await flow.async_step_user({
            "host": "192.0.2.60", "username": "user", "password": "secret",
        })
        self.assertEqual(result["step_id"], "device")
        self.assertEqual(_form_default(result, "name"), "Control4 DS2 Door Station")
        result = await flow.async_step_device({"name": "Control4 DS2 Door Station"})
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(flow._unique_id, FakeAPI.system_info["serialNumber"])

    async def test_ssdp_without_friendly_name_uses_api_default(self) -> None:
        flow = self._make_flow()
        result = await flow.async_step_ssdp(self._make_ssdp_info(friendly_name=None))
        self.assertEqual(result["step_id"], "user")
        result = await flow.async_step_user({
            "host": "192.0.2.60", "username": "user", "password": "secret",
        })
        self.assertEqual(_form_default(result, "name"), "2N Intercom SN-123456")

    async def test_ssdp_extracts_host_from_location_when_no_presentation_url(
        self,
    ) -> None:
        flow = self._make_flow()
        result = await flow.async_step_ssdp(
            self._make_ssdp_info(via_location=True)
        )
        self.assertEqual(result["type"], "form")
        self.assertEqual(flow._discovered_host, "192.0.2.60")

    async def test_ssdp_aborts_without_mac(self) -> None:
        for mac in ("", " ", ":-", "not-a-mac", "00112233445", "00112233445Z"):
            with self.subTest(mac=mac):
                flow = self._make_flow()
                result = await flow.async_step_ssdp(self._make_ssdp_info(mac=mac))
                self.assertEqual(result["type"], "abort")
                self.assertEqual(result["reason"], "no_mac")
                self.assertEqual(flow.hass.config_entries.update_calls, [])

    async def test_ssdp_aborts_without_usable_host(self) -> None:
        SsdpServiceInfo = sys.modules[
            "homeassistant.helpers.service_info.ssdp"
        ].SsdpServiceInfo
        for url in (None, "", "no-host", "http://", "http://[", "http://bad host"):
            with self.subTest(url=url):
                flow = self._make_flow()
                result = await flow.async_step_ssdp(SsdpServiceInfo(
                    upnp={"serialNumber": "001122334455", "presentationURL": url},
                    ssdp_location=url,
                ))
                self.assertEqual(result["type"], "abort")
                self.assertEqual(result["reason"], "no_host")
                self.assertEqual(flow.hass.config_entries.update_calls, [])

    async def test_ssdp_malformed_presentation_url_falls_back_to_location(self) -> None:
        info = self._make_ssdp_info(via_location=True)
        info.upnp["presentationURL"] = "http://["
        result = await self._make_flow().async_step_ssdp(info)
        self.assertEqual(_form_default(result, "host"), "192.0.2.60")

    def test_ssdp_manifest_and_translations(self) -> None:
        integration = REPO_ROOT / "custom_components" / "2n_intercom"
        manifest = json.loads((integration / "manifest.json").read_text())
        self.assertIn({"manufacturer": "2N, part of Axis group"}, manifest["ssdp"])
        for file in (
            integration / "strings.json",
            *(integration / "translations" / f"{language}.json" for language in ("en", "de", "cs")),
        ):
            with self.subTest(file=file.name):
                config = json.loads(file.read_text())["config"]
                self.assertEqual(config["flow_title"], "{name} ({host})")
                self.assertTrue(config["abort"]["no_host"])
                self.assertTrue(config["abort"]["no_mac"])
                self.assertNotIn("cannot_connect", config["abort"])

    async def test_ssdp_updates_host_for_already_configured_device(self) -> None:
        """Different MAC formatting (colons vs bare) must still match."""
        entry = FakeConfigEntry(
            "entry-1",
            {
                "host": "192.0.2.50",
                "mac_address": "7C1EB3000000",
                "username": "root",
                "password": "secret",
                "serial_number": "SN-123456",
                "protocol": "https",
                "port": 443,
                "verify_ssl": True,
            },
            options={"scan_interval": 120},
        )
        entry.unique_id = "SN-123456"
        old_data = dict(entry.data)
        hass = FakeHass([entry])
        flow = self._make_flow(hass)
        with patch.object(FakeAPI, "system_info", {
            "macAddr": "7c:1e:b3:00:00:00", "serialNumber": " SN-123456 ",
        }), self.assertLogs(self.config_flow_module._LOGGER, level="INFO") as logs:
            result = await flow.async_step_ssdp(
                self._make_ssdp_info(mac="7c-1e-b3-00-00-00", host="192.0.2.60")
            )
        await asyncio.sleep(0)  # let the scheduled reload task run
        self.assertEqual(result["type"], "abort")
        self.assertEqual(result["reason"], "already_configured")
        self.assertEqual(entry.data["host"], "192.0.2.60")
        self.assertEqual(hass.config_entries.reload_calls, [entry.entry_id])
        self.assertEqual(hass.config_entries.update_calls, [
            (entry.entry_id, {**old_data, "host": "192.0.2.60"}),
        ])
        self.assertEqual(entry.options, {"scan_interval": 120})
        self.assertEqual(entry.unique_id, "SN-123456")
        self.assertEqual(len(FakeAPI.instances), 1)
        api = FakeAPI.instances[0]
        self.assertEqual((api.host, api.port, api.protocol), ("192.0.2.60", 443, "https"))
        self.assertEqual((api.username, api.password), ("root", "secret"))
        self.assertTrue(api.verify_ssl)
        self.assertTrue(api.allow_basic_fallback)
        self.assertTrue(api.closed)
        self.assertEqual([record.getMessage() for record in logs.records], [
            "2N intercom Front door moved from 192.0.2.50 to 192.0.2.60 "
            "(SSDP); updating the entry",
        ])
        self.assertEqual(logs.records[0].levelno, logging.INFO)
        for private_value in ("root", "secret", "7C1EB3000000", "7c-1e-b3-00-00-00"):
            self.assertNotIn(private_value, logs.records[0].getMessage())
        with self.assertNoLogs(self.config_flow_module._LOGGER, level="INFO"):
            repeated = await self._make_flow(hass).async_step_ssdp(
                self._make_ssdp_info(mac="7c:1e:b3:00:00:00")
            )
        await asyncio.sleep(0)
        self.assertEqual(repeated["reason"], "already_configured")
        self.assertEqual(hass.config_entries.reload_calls, [entry.entry_id])
        self.assertEqual(len(hass.config_entries.update_calls), 1)
        self.assertEqual(len(FakeAPI.instances), 1)

    def _make_ssdp_entry(self, entry_id="entry-1"):
        entry = FakeConfigEntry(
            entry_id,
            {
                "host": "192.0.2.50",
                "mac_address": "7c-1e-b3-00-00-00",
                "serial_number": "SN-123456",
                "username": "api-user",
                "password": "test-secret",
                "protocol": "https",
                "port": 8443,
                "verify_ssl": False,
            },
        )
        entry.unique_id = "SN-123456"
        return entry

    async def test_ssdp_rejects_unverifiable_hosts_without_changing_entry(self) -> None:
        module = self.config_flow_module
        for reply in (
            module.TwoNConnectionError("test-secret api-user unreachable"),
            module.TwoNAuthenticationError("test-secret api-user rejected"),
            module.TwoNAPIError("test-secret api-user invalid JSON"),
            {"macAddr": "001122334455", "serialNumber": "SN-123456"},
            {"macAddr": "7C1EB3000000", "serialNumber": "SN-OTHER"},
            {"serialNumber": "SN-123456"},
            {"macAddr": "7C1EB3000000"},
            {},
            None,
            [],
        ):
            with self.subTest(reply=reply):
                entry = self._make_ssdp_entry()
                old_data = dict(entry.data)
                hass = FakeHass([entry])
                lookup = AsyncMock()
                if isinstance(reply, Exception):
                    lookup.side_effect = reply
                else:
                    lookup.return_value = reply
                with patch.object(FakeAPI, "async_get_system_info", lookup), (
                    self.assertLogs(module._LOGGER, level="WARNING")
                ) as logs:
                    result = await self._make_flow(hass).async_step_ssdp(
                        self._make_ssdp_info()
                    )
                await asyncio.sleep(0)
                self.assertEqual(result["reason"], "already_configured")
                self.assertEqual(entry.data, old_data)
                self.assertEqual(entry.unique_id, "SN-123456")
                self.assertEqual(hass.config_entries.update_calls, [])
                self.assertEqual(hass.config_entries.reload_calls, [])
                lookup.assert_awaited_once_with(log_errors=False)
                self.assertTrue(FakeAPI.instances[-1].closed)
                self.assertEqual(len(logs.records), 1)
                self.assertEqual(logs.records[0].levelno, logging.WARNING)
                for value in ("api-user", "test-secret", "SN-123456", "7C1EB3000000"):
                    self.assertNotIn(value, logs.records[0].getMessage())

    async def test_ssdp_warning_is_once_per_host_per_entry_across_flows(self) -> None:
        first = self._make_ssdp_entry()
        second = self._make_ssdp_entry("entry-2")
        hass = FakeHass([first])
        lookup = AsyncMock(side_effect=self.config_flow_module.TwoNConnectionError())
        with patch.object(FakeAPI, "async_get_system_info", lookup), (
            self.assertLogs(self.config_flow_module._LOGGER, level="WARNING")
        ) as logs:
            for entry in (first, second):
                hass.config_entries._entries = {entry.entry_id: entry}
                for host in ("192.0.2.60", "192.0.2.61", "192.0.2.60", "192.0.2.61"):
                    await self._make_flow(hass).async_step_ssdp(
                        self._make_ssdp_info(host=host)
                    )
                    # Warning memory must not depend on reloadable runtime_data.
                    entry.runtime_data = object()
        self.assertEqual(len(logs.records), 4)
        self.assertEqual(lookup.await_count, 8)
        for host in ("192.0.2.60", "192.0.2.61"):
            self.assertEqual(sum(host in record.getMessage() for record in logs.records), 2)
        self.assertEqual(hass.config_entries.update_calls, [])
        self.assertEqual(hass.config_entries.reload_calls, [])
        self.assertTrue(all(api.closed for api in FakeAPI.instances))

    async def test_ssdp_verification_preserves_saved_transport_and_auth_settings(self) -> None:
        for protocol, verify_ssl, opt_in, legacy_opt_in in (
            ("https", False, False, True),
            ("https", False, True, False),
            ("https", True, False, False),
            ("http", False, True, False),
            ("http", True, True, False),
            ("http", False, None, True),
        ):
            with self.subTest(protocol=protocol, verify_ssl=verify_ssl, opt_in=opt_in):
                entry = self._make_ssdp_entry()
                entry.data.update(
                    protocol=protocol, verify_ssl=verify_ssl, allow_insecure=legacy_opt_in
                )
                if opt_in is not None:
                    entry.options["allow_insecure"] = opt_in
                hass = FakeHass([entry])
                lookup = AsyncMock(return_value={
                    "macAddr": "7C1EB3000000", "serialNumber": "SN-123456",
                })
                with patch.object(FakeAPI, "async_get_system_info", lookup):
                    await self._make_flow(hass).async_step_ssdp(self._make_ssdp_info())
                await asyncio.sleep(0)
                api = FakeAPI.instances[-1]
                self.assertEqual((api.host, api.port), ("192.0.2.60", 8443))
                self.assertEqual((api.username, api.password), ("api-user", "test-secret"))
                self.assertEqual((api.protocol, api.verify_ssl), (protocol, verify_ssl))
                self.assertEqual(
                    api.allow_insecure, legacy_opt_in if opt_in is None else opt_in
                )
                self.assertEqual(
                    api.allow_basic_fallback, protocol == "https" and verify_ssl
                )
                self.assertTrue(api.closed)
                self.assertEqual(hass.config_entries.reload_calls, [entry.entry_id])

    async def test_ssdp_accepts_matching_mac_for_legacy_unique_ids(self) -> None:
        for unique_id in ("7c:1e:b3:00:00:00", "192.0.2.40", None):
            with self.subTest(unique_id=unique_id):
                entry = self._make_ssdp_entry()
                entry.unique_id = unique_id
                if unique_id != "7c:1e:b3:00:00:00":
                    entry.data.pop("serial_number")
                hass = FakeHass([entry])
                with patch.object(FakeAPI, "system_info", {"macAddr": "7C1EB3000000"}):
                    await self._make_flow(hass).async_step_ssdp(self._make_ssdp_info())
                await asyncio.sleep(0)
                self.assertEqual(entry.data["host"], "192.0.2.60")
                self.assertEqual(entry.unique_id, unique_id)
                self.assertEqual(hass.config_entries.reload_calls, [entry.entry_id])

    async def test_ssdp_unverified_basic_challenge_never_receives_credentials(self) -> None:
        for protocol in ("https", "http"):
            for allow_insecure in (False, True):
                with self.subTest(protocol=protocol, allow_insecure=allow_insecure):
                    entry = self._make_ssdp_entry()
                    entry.data["protocol"] = protocol
                    entry.options["allow_insecure"] = allow_insecure
                    hass = FakeHass([entry])
                    calls = []
                    clients = []

                    @asynccontextmanager
                    async def request(method, url, **kwargs):
                        calls.append((method, url, kwargs))
                        yield types.SimpleNamespace(
                            status=401, headers={"WWW-Authenticate": "Basic realm=device"},
                        )

                    def create_api(**kwargs):
                        api = self.discovery_api_type(**kwargs)
                        api._session = types.SimpleNamespace(
                            closed=False, request=request, close=AsyncMock(),
                        )
                        clients.append(api)
                        return api

                    api_logger = logging.getLogger(self.discovery_api_type.__module__)
                    with patch.object(self.config_flow_module, "TwoNIntercomAPI", create_api), (
                        self.assertNoLogs(api_logger)
                    ), self.assertLogs(
                        self.config_flow_module._LOGGER, level="WARNING"
                    ) as logs:
                        for _ in range(2):
                            result = await self._make_flow(hass).async_step_ssdp(
                                self._make_ssdp_info()
                            )
                            self.assertEqual(result["reason"], "already_configured")
                    await asyncio.sleep(0)
                    self.assertEqual(len(logs.records), 1)
                    self.assertEqual(len(calls), 2)
                    for method, url, kwargs in calls:
                        self.assertEqual(method, "GET")
                        self.assertEqual(url, f"{protocol}://192.0.2.60:8443/api/system/info")
                        self.assertNotIn("auth", kwargs)
                    self.assertTrue(all(api._session is None for api in clients))
                    self.assertEqual(entry.data["host"], "192.0.2.50")
                    self.assertEqual(hass.config_entries.update_calls, [])
                    self.assertEqual(hass.config_entries.reload_calls, [])
                    for private_value in ("api-user", "test-secret"):
                        self.assertNotIn(private_value, logs.output[0])

    async def test_ssdp_retries_previously_rejected_host(self) -> None:
        entry = self._make_ssdp_entry()
        hass = FakeHass([entry])
        lookup = AsyncMock(side_effect=[
            self.config_flow_module.TwoNConnectionError(),
            {"macAddr": "7C1EB3000000", "serialNumber": "SN-123456"},
        ])
        with patch.object(FakeAPI, "async_get_system_info", lookup), (
            self.assertLogs(self.config_flow_module._LOGGER, level="WARNING")
        ) as logs:
            for _ in range(2):
                await self._make_flow(hass).async_step_ssdp(self._make_ssdp_info())
        await asyncio.sleep(0)
        self.assertEqual(len(logs.records), 1)
        self.assertEqual(lookup.await_count, 2)
        self.assertEqual(entry.data["host"], "192.0.2.60")
        self.assertEqual(len(hass.config_entries.update_calls), 1)
        self.assertEqual(hass.config_entries.reload_calls, [entry.entry_id])

    async def test_ssdp_concurrent_matching_announcements_reload_once(self) -> None:
        entry = self._make_ssdp_entry()
        hass = FakeHass([entry])
        both_started = asyncio.Event()
        started = 0

        async def lookup(*, log_errors):
            nonlocal started
            started += 1
            if started == 2:
                both_started.set()
            await both_started.wait()
            return {"macAddr": "7C1EB3000000", "serialNumber": "SN-123456"}

        with patch.object(FakeAPI, "async_get_system_info", side_effect=lookup):
            await asyncio.gather(*(
                self._make_flow(hass).async_step_ssdp(self._make_ssdp_info())
                for _ in range(2)
            ))
        await asyncio.sleep(0)
        self.assertEqual(len(hass.config_entries.update_calls), 1)
        self.assertEqual(hass.config_entries.reload_calls, [entry.entry_id])
        self.assertTrue(all(api.closed for api in FakeAPI.instances))

    async def test_ssdp_no_op_when_host_unchanged(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {
                "host": "192.0.2.60",
                "mac_address": "7C1EB3000000",
                "username": "root",
                "password": "secret",
            },
        )
        hass = FakeHass([entry])
        flow = self._make_flow(hass)
        result = await flow.async_step_ssdp(
            self._make_ssdp_info(mac="7C1EB3000000", host="192.0.2.60")
        )
        self.assertEqual(result["type"], "abort")
        self.assertEqual(result["reason"], "already_configured")
        await asyncio.sleep(0)
        self.assertEqual(hass.config_entries.update_calls, [])
        self.assertEqual(hass.config_entries.reload_calls, [])
        self.assertEqual(FakeAPI.instances, [])


class OptionsFlowTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the options flow."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config_flow_module = load_config_flow_module()
        cls.directory_api_type = cls.config_flow_module.TwoNIntercomAPI
        cls.config_flow_module.TwoNIntercomAPI = FakeAPI

    def setUp(self) -> None:
        FakeAPI.instances = []
        FakeAPI.connection_result = True
        FakeAPI.system_info = {"serialNumber": "SN-123"}

    def _make_options_flow(
        self, entry: FakeConfigEntry, hass: FakeHass | None = None
    ):
        flow = self.config_flow_module.TwoNIntercomOptionsFlow(entry)
        flow.config_entry = entry
        flow.hass = hass or FakeHass([entry])
        return flow

    async def test_init_redirects_to_device_step(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {
                "host": "192.0.2.20",
                "port": 443,
                "username": "user",
                "password": "pass",
            },
        )
        flow = self._make_options_flow(entry)
        result = await flow.async_step_init(None)
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "device")

    async def test_firmware_channel_default_selector_and_saved_option(self) -> None:
        for channel in ("active_track", "lts", "beta"):
            with self.subTest(channel=channel):
                entry = FakeConfigEntry(
                    "entry-1",
                    {"host": "example.invalid"},
                    options={} if channel == "active_track" else {"firmware_channel": channel},
                )
                flow = self._make_options_flow(entry)
                form = await flow.async_step_init()
                marker, field = next(
                    (marker, field)
                    for marker, field in form["data_schema"].schema.items()
                    if marker.key == "firmware_channel"
                )
                self.assertEqual(marker.default, channel)
                self.assertEqual(field.config.options, ["active_track", "lts", "beta"])
                self.assertEqual(field.config.translation_key, "firmware_channel")
                self.assertFalse(field.config.custom_value)
                result = await flow.async_step_device({
                    "name": "Intercom", "enable_camera": False,
                    "enable_doorbell": True, "firmware_channel": channel,
                })
                self.assertEqual(result["type"], "create_entry")
                self.assertEqual(result["data"]["firmware_channel"], channel)
                self.assertEqual(entry.data, {"host": "example.invalid"})

    async def test_ring_on_keypress_defaults_off_and_is_saved(self) -> None:
        for saved, expected_default in (
            ({}, False), ({"ring_on_keypress": True}, True),
        ):
            with self.subTest(saved=saved):
                entry = FakeConfigEntry(
                    "entry-1", {"host": "example.invalid"}, options=dict(saved)
                )
                flow = self._make_options_flow(entry)
                form = await flow.async_step_init()
                marker = next(
                    marker
                    for marker in form["data_schema"].schema
                    if marker.key == "ring_on_keypress"
                )
                self.assertEqual(marker.default, expected_default)
                result = await flow.async_step_device({
                    "name": "Intercom", "enable_camera": False,
                    "enable_doorbell": True,
                    "ring_on_keypress": not expected_default,
                })
                self.assertEqual(result["type"], "create_entry")
                self.assertEqual(
                    result["data"]["ring_on_keypress"], not expected_default
                )
                self.assertEqual(entry.data, {"host": "example.invalid"})

    def _grant_user_marker(self, form):
        for marker, field in form["data_schema"].schema.items():
            if marker.key == "grant_access_user":
                return marker, field
        self.fail("grant_access_user field missing")

    async def test_device_step_offers_directory_users_for_grant_access(self) -> None:
        directory = {
            "series": "1",
            "users": [
                {"uuid": "AAAA-1", "name": "Alice", "callPos": [{"peer": "sip:1@x"}]},
                {"uuid": "BBBB-2", "name": ""},
                {"name": "No uuid"},
            ],
        }

        async def get_directory(_self, *, raise_on_device_error=False):
            self.assertTrue(raise_on_device_error)
            return directory

        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
            options={"grant_access_user": "aaaa-1"},
        )
        flow = self._make_options_flow(entry)
        original = FakeAPI.async_get_directory
        FakeAPI.async_get_directory = get_directory
        try:
            form = await flow.async_step_device(None)
        finally:
            FakeAPI.async_get_directory = original

        self.assertEqual(len(FakeAPI.instances), 1, "directory must be queried once")
        marker, field = self._grant_user_marker(form)
        self.assertIsInstance(marker, sys.modules["voluptuous"].Optional)
        self.assertEqual(marker.description, {"suggested_value": "aaaa-1"})
        self.assertFalse(field.config.custom_value)
        self.assertEqual(field.config.mode, "dropdown")
        self.assertEqual(
            field.config.options,
            [
                {"label": "Alice", "value": "aaaa-1"},
                {"label": "BBBB-2 (no name)", "value": "BBBB-2"},
            ],
        )
        called_field = next(
            field for marker, field in form["data_schema"].schema.items()
            if marker.key == "called_id"
        )
        self.assertTrue(called_field.config.custom_value)
        self.assertEqual(called_field.config.mode, "dropdown")
        self.assertIn({"label": "sip:1@x", "value": "sip:1@x"}, called_field.config.options)
        self.assertEqual(form["errors"], {})
        self.assertTrue(FakeAPI.instances[0].closed)

    async def test_device_step_preserves_selected_grant_user_case_on_save(self) -> None:
        for stored in ("aaaa-1", "AaAa-1", "AAAA-1"):
            with self.subTest(stored=stored):
                entry = FakeConfigEntry(
                    "entry-1", {"host": "192.0.2.20"},
                    options={"grant_access_user": stored},
                )
                flow = self._make_options_flow(entry)
                with patch.object(
                    FakeAPI, "async_get_directory", new_callable=AsyncMock,
                    return_value={"users": [{"uuid": "AAAA-1", "name": "Alice"}]},
                ):
                    form = await flow.async_step_device(None)
                    marker, field = self._grant_user_marker(form)
                    suggested = marker.description["suggested_value"]
                    self.assertEqual(suggested, stored)
                    self.assertEqual(field.config.options, [
                        {"label": "Alice", "value": suggested},
                    ])
                    result = await flow.async_step_device({
                        "name": "Intercom", "enable_camera": False,
                        "enable_doorbell": True, "scan_interval": 60,
                        "grant_access_user": suggested,
                    })
                self.assertEqual(result["type"], "create_entry")
                self.assertEqual(result["data"]["grant_access_user"], stored)
                self.assertNotIn("grant_access_user", entry.data)

    async def test_device_step_keeps_unknown_stored_grant_user_selectable(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
            options={"grant_access_user": "CCCC-3"},
        )
        flow = self._make_options_flow(entry)
        form = await flow.async_step_device(None)
        marker, field = self._grant_user_marker(form)
        self.assertEqual(marker.description, {"suggested_value": "CCCC-3"})
        self.assertEqual(field.config.options, [
            {"label": "Unknown user (CCCC-3)", "value": "CCCC-3"},
        ])
        self.assertEqual(form["errors"], {})
        result = await flow.async_step_device({
            "name": "Intercom", "enable_camera": False,
            "enable_doorbell": True, "scan_interval": 60,
            "grant_access_user": marker.description["suggested_value"],
        })
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["grant_access_user"], "CCCC-3")

    async def test_device_step_uses_localized_directory_fallback_labels(self) -> None:
        for language, unnamed, unknown in (
            ("en", "BBBB-2 (no name)", "Unknown user (CCCC-3)"),
            ("de", "BBBB-2 (ohne Namen)", "Unbekannter Benutzer (CCCC-3)"),
            ("cs", "BBBB-2 (bez jména)", "Neznámý uživatel (CCCC-3)"),
        ):
            with self.subTest(language=language):
                entry = FakeConfigEntry(
                    "entry-1", {"host": "192.0.2.20"},
                    options={"grant_access_user": "CCCC-3"},
                )
                hass = FakeHass([entry])
                hass.config.language = language
                flow = self._make_options_flow(entry, hass)
                with patch.object(
                    FakeAPI, "async_get_directory", new_callable=AsyncMock,
                    return_value={"users": [{"uuid": "BBBB-2", "name": ""}]},
                ):
                    form = await flow.async_step_device(None)
                _marker, field = self._grant_user_marker(form)
                self.assertEqual(field.config.options, [
                    {"label": unnamed, "value": "BBBB-2"},
                    {"label": unknown, "value": "CCCC-3"},
                ])

    async def test_directory_failure_warns_once_and_allows_saving_stored_user(self) -> None:
        class Response:
            status = 200

            def raise_for_status(self):
                pass

            async def json(self):
                return {
                    "success": False,
                    "error": {"code": 10, "description": "insufficient privileges"},
                }

        for failure in (TimeoutError, RuntimeError, None):
            with self.subTest(failure=failure):
                @asynccontextmanager
                async def request(_api, *_args, **_kwargs):
                    if failure is not None:
                        raise failure("directory lookup failed")
                    yield Response()

                entry = FakeConfigEntry(
                    "entry-1",
                    {"host": "192.0.2.20", "username": "test-user", "password": "test-secret"},
                    options={"grant_access_user": "cccc-3"},
                )
                flow = self._make_options_flow(entry)
                with (
                    patch.object(
                        self.config_flow_module, "TwoNIntercomAPI", self.directory_api_type
                    ),
                    patch.object(self.directory_api_type, "_async_request", request),
                ):
                    with self.assertLogs("custom_components.2n_intercom", "WARNING") as logs:
                        form = await flow.async_step_device(None)
                    self.assertEqual(form["errors"], {"base": "directory_unavailable"})
                    marker, field = self._grant_user_marker(form)
                    self.assertEqual(marker.description, {"suggested_value": "cccc-3"})
                    self.assertEqual(field.config.options, [
                        {"label": "Unknown user (cccc-3)", "value": "cccc-3"},
                    ])
                    self.assertEqual(len(logs.records), 1)
                    warning = logs.records[0]
                    self.assertEqual(warning.levelno, logging.WARNING)
                    self.assertIn("host=192.0.2.20", warning.getMessage())
                    self.assertNotIn("test-user", warning.getMessage())
                    self.assertNotIn("test-secret", warning.getMessage())
                    self.assertIsNone(warning.exc_info)
                    with self.assertLogs("custom_components.2n_intercom", "WARNING") as saved_logs:
                        result = await flow.async_step_device({
                            "name": "Intercom", "enable_camera": False,
                            "enable_doorbell": True, "scan_interval": 60,
                            "grant_access_user": marker.description["suggested_value"],
                        })
                    self.assertEqual(len(saved_logs.records), 1)
                    self.assertEqual(result["type"], "create_entry")
                    self.assertEqual(result["data"]["grant_access_user"], "cccc-3")

    async def test_device_step_without_stored_grant_user(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
        )
        flow = self._make_options_flow(entry)
        form = await flow.async_step_device(None)
        marker, field = self._grant_user_marker(form)
        self.assertEqual(marker.description, {"suggested_value": None})
        self.assertEqual(field.config.options, [])

    async def test_device_step_saves_trimmed_grant_user(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
        )
        flow = self._make_options_flow(entry)
        result = await flow.async_step_device({
            "name": "Intercom", "enable_camera": False,
            "enable_doorbell": True, "scan_interval": 60,
            "grant_access_user": "  AAAA-1 ",
        })
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["grant_access_user"], "AAAA-1")

    async def test_device_step_clearing_grant_user_removes_it(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
            options={"grant_access_user": "AAAA-1"},
        )
        for submitted in ({"grant_access_user": ""}, {"grant_access_user": None}, {}):
            flow = self._make_options_flow(entry)
            result = await flow.async_step_device({
                "name": "Intercom", "enable_camera": False,
                "enable_doorbell": True, "scan_interval": 60,
                **submitted,
            })
            self.assertEqual(result["type"], "create_entry")
            self.assertNotIn("grant_access_user", result["data"], submitted)

    async def test_device_step_no_camera_no_relays_creates_entry(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
        )
        flow = self._make_options_flow(entry)
        result = await flow.async_step_device(
            {
                "name": "Updated",
                "enable_camera": False,
                "enable_doorbell": True,
                "scan_interval": 10,
                "relay_count": 0,
                "door_type": "door",
            }
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["name"], "Updated")
        self.assertEqual(result["data"]["scan_interval"], 10)

    async def test_options_without_detected_relays_preserve_saved_overrides(self) -> None:
        for camera_enabled in (False, True):
            for caps in (None, {}, {"switches": []}):
                with self.subTest(camera=camera_enabled, caps=caps):
                    saved_relays = [
                        {
                            "relay_number": 3,
                            "relay_name": "Gate",
                            "relay_device_type": "gate",
                            "relay_pulse_duration": 15000,
                        },
                        {
                            "relay_number": 1,
                            "relay_name": "Door",
                            "relay_device_type": "door",
                            "relay_pulse_duration": 2500,
                        },
                    ]
                    entry = FakeConfigEntry(
                        "entry-1",
                        {
                            "host": "192.0.2.20", "port": 443,
                            "username": "u", "password": "p",
                        },
                        options={"relays": deepcopy(saved_relays)},
                    )
                    original_data = dict(entry.data)
                    if caps is not None:
                        entry.runtime_data = types.SimpleNamespace(
                            coordinator=types.SimpleNamespace(switch_caps=caps)
                        )
                    flow = self._make_options_flow(entry)
                    form = await flow.async_step_init(None)
                    self.assertEqual(form["step_id"], "device")
                    device_input = {
                        "name": "Updated",
                        "enable_camera": camera_enabled,
                        "enable_doorbell": True,
                        "scan_interval": 42,
                    }
                    result = await flow.async_step_device(dict(device_input))
                    expected = {
                        **device_input,
                        "relays": saved_relays,
                        "allow_insecure": False,
                    }
                    if camera_enabled:
                        self.assertEqual(result["step_id"], "camera")
                        camera_input = {
                            "live_view_mode": "mjpeg",
                            "camera_source": "internal",
                            "mjpeg_width": 640,
                            "mjpeg_height": 480,
                            "mjpeg_fps": 5,
                        }
                        result = await flow.async_step_camera(dict(camera_input))
                        expected.update(camera_input)

                    self.assertEqual(result["type"], "create_entry")
                    self.assertEqual(result["data"], expected)
                    self.assertEqual(entry.options, {"relays": saved_relays})
                    self.assertEqual(entry.data, original_data)

    async def test_options_merge_shown_relays_with_unshown_saved_overrides(self) -> None:
        saved_relays = [
            {
                "relay_number": 1,
                "relay_name": "Gate",
                "relay_device_type": "gate",
                "relay_pulse_duration": 15000,
            },
            {
                "relay_number": 3,
                "relay_name": "Door",
                "relay_device_type": "door",
                "relay_pulse_duration": 2500,
            },
            {
                "relay_number": 5,
                "relay_name": "Side Gate",
                "relay_device_type": "gate",
                "relay_pulse_duration": 10000,
            },
        ]
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
            options={"relays": deepcopy(saved_relays)},
        )
        entry.runtime_data = _make_runtime([
            {"switch": 3, "enabled": True, "switchOnDuration": 5},
            {"switch": 5, "enabled": False},
            {"switch": 7, "enabled": True, "switchOnDuration": 4},
        ])
        flow = self._make_options_flow(entry)
        device_input = {
            "name": "Updated", "enable_camera": False,
            "enable_doorbell": True, "scan_interval": 42,
        }
        result = await flow.async_step_device(dict(device_input))
        self.assertEqual(result["step_id"], "relay")
        for key, value in saved_relays[1].items():
            self.assertEqual(_form_default(result, key), value)
        updated_relay = {
            "relay_number": 3,
            "relay_name": "Updated Gate",
            "relay_device_type": "gate",
            "relay_pulse_duration": 12000,
        }
        result = await flow.async_step_relay(dict(updated_relay))
        self.assertEqual(result["step_id"], "relay")
        new_relay = {
            "relay_number": 7,
            "relay_name": "Relay 7",
            "relay_device_type": "door",
            "relay_pulse_duration": 4000,
        }
        for key, value in new_relay.items():
            self.assertEqual(_form_default(result, key), value)
        self.assertEqual(entry.options, {"relays": saved_relays})
        self.assertNotIn("relays", flow._data)

        result = await flow.async_step_relay(dict(new_relay))

        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"], {
            **device_input,
            "relays": [
                saved_relays[0], updated_relay, saved_relays[2], new_relay,
            ],
            "allow_insecure": False,
        })
        self.assertEqual(entry.options, {"relays": saved_relays})

    async def test_saved_gate_remains_cover_after_empty_caps_options_and_reload(self) -> None:
        from test_cover import load_cover_module
        from test_switch import (
            FakeConfigEntry as PlatformConfigEntry,
            FakeCoordinator,
            load_switch_module,
        )

        cover_module = load_cover_module()
        switch_module = load_switch_module()
        gate = {
            "relay_number": 2,
            "relay_name": "Gate",
            "relay_device_type": "gate",
            "relay_pulse_duration": 15000,
        }
        entry = PlatformConfigEntry(
            "entry-1",
            {
                "name": "Intercom", "host": "192.0.2.20", "port": 443,
                "username": "u", "password": "p",
            },
            options={"relays": [gate]},
        )
        entry.runtime_data = types.SimpleNamespace(coordinator=FakeCoordinator())
        hass = FakeHass([entry])
        flow = self._make_options_flow(entry, hass)
        result = await flow.async_step_device({
            "name": "Intercom", "enable_camera": False,
            "enable_doorbell": True, "scan_interval": 60,
        })
        self.assertEqual(result["type"], "create_entry")
        hass.config_entries.async_update_entry(entry, options=result["data"])

        coordinator = FakeCoordinator(switch_caps={
            "switches": [
                {"switch": 1, "enabled": True, "switchOnDuration": 5},
                {"switch": 2, "enabled": True, "switchOnDuration": 15},
            ],
        })
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)
        covers = []
        switches = []
        await cover_module.async_setup_entry(
            hass, entry,
            lambda entities, update_before_add=False: covers.extend(entities),
        )
        await switch_module.async_setup_entry(
            hass, entry,
            lambda entities, update_before_add=False: switches.extend(entities),
        )

        self.assertEqual([cover._attr_unique_id for cover in covers], [
            "entry-1_cover_2",
        ])
        self.assertIsInstance(covers[0], cover_module.TwoNIntercomCover)
        self.assertEqual(covers[0]._attr_device_class, "gate")
        self.assertEqual(covers[0]._attr_name, gate["relay_name"])
        self.assertEqual(covers[0]._pulse_duration, gate["relay_pulse_duration"])
        self.assertEqual([switch._attr_unique_id for switch in switches], [
            "entry-1_switch_1",
        ])

    async def test_device_step_with_camera_advances_to_camera(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
        )
        flow = self._make_options_flow(entry)
        result = await flow.async_step_device(
            {
                "name": "Intercom",
                "enable_camera": True,
                "enable_doorbell": True,
                "scan_interval": 5,
                "relay_count": 0,
                "door_type": "door",
            }
        )
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "camera")

    async def test_options_preserve_insecure_opt_in_for_directory_and_save(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {
                "host": "192.0.2.20", "port": 80, "protocol": "http",
                "username": "user", "password": "pass",
            },
            options={"allow_insecure": True, "host": "stale.example"},
        )
        flow = self._make_options_flow(entry)
        result = await flow.async_step_device({
            "name": "Intercom", "enable_camera": False,
            "enable_doorbell": True, "scan_interval": 60,
        })
        self.assertTrue(FakeAPI.instances[-1].allow_insecure)
        self.assertEqual(FakeAPI.instances[-1].host, "192.0.2.20")
        self.assertEqual(result["type"], "create_entry")
        self.assertTrue(result["data"]["allow_insecure"])
        self.assertNotIn("host", result["data"])

    async def test_camera_step_no_relays_creates_entry(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
        )
        flow = self._make_options_flow(entry)
        flow._data = {
            "name": "Intercom",
            "enable_camera": True,
            "relay_count": 0,
        }
        result = await flow.async_step_camera(
            {
                "live_view_mode": "auto",
                "camera_source": "internal",
                "mjpeg_width": 640,
                "mjpeg_height": 480,
                "mjpeg_fps": 5,
            }
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["live_view_mode"], "auto")
        self.assertEqual(result["data"]["mjpeg_width"], 640)

    async def test_camera_step_coerces_floats_to_ints(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
        )
        flow = self._make_options_flow(entry)
        flow._data = {"relay_count": 0}
        result = await flow.async_step_camera(
            {
                "live_view_mode": "mjpeg",
                "camera_source": "internal",
                "mjpeg_width": 640.0,
                "mjpeg_height": 480.0,
                "mjpeg_fps": 10.0,
            }
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertIsInstance(result["data"]["mjpeg_width"], int)
        self.assertIsInstance(result["data"]["mjpeg_fps"], int)

    async def test_camera_step_renders_form_when_no_input(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
        )
        flow = self._make_options_flow(entry)
        flow._data = {}
        result = await flow.async_step_camera(None)
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "camera")

    async def test_device_step_with_detected_relays_advances_to_relay(self) -> None:
        """When coordinator reports enabled relays, options flow shows relay step."""
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
        )
        # Simulate runtime_data with a coordinator that has switch_caps
        runtime = type("RT", (), {
            "coordinator": type("C", (), {
                "switch_caps": {
                    "switches": [
                        {"switch": 1, "enabled": True, "switchOnDuration": 5},
                    ]
                }
            })(),
        })()
        entry.runtime_data = runtime
        flow = self._make_options_flow(entry)
        result = await flow.async_step_device(
            {
                "name": "Intercom",
                "enable_camera": False,
                "enable_doorbell": True,
                "scan_interval": 5,
            }
        )
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "relay")

    async def test_options_relay_creates_entry(self) -> None:
        """Relay step with combined fields creates entry directly."""
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
        )
        flow = self._make_options_flow(entry)
        flow._data = {"enable_camera": False}
        flow._relay_inputs = {}
        flow._detected_relays = [
            {"switch": 1, "enabled": True, "switchOnDuration": 5},
        ]

        result = await flow.async_step_relay(
            {
                "relay_number": 1,
                "relay_name": "Door",
                "relay_device_type": "door",
                "relay_pulse_duration": 3000,
            },
            relay_index=0,
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(len(result["data"]["relays"]), 1)
        self.assertEqual(result["data"]["relays"][0]["relay_pulse_duration"], 3000)

    async def test_options_relay_renders_form(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
        )
        flow = self._make_options_flow(entry)
        flow._data = {}
        flow._relay_inputs = {}
        flow._detected_relays = [
            {"switch": 1, "enabled": True, "switchOnDuration": 5},
        ]
        result = await flow.async_step_relay(None, relay_index=0)
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "relay")

    async def test_options_multiple_relays(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
        )
        flow = self._make_options_flow(entry)
        flow._data = {"enable_camera": False}
        flow._relay_inputs = {}
        flow._detected_relays = [
            {"switch": 1, "enabled": True, "switchOnDuration": 5},
            {"switch": 2, "enabled": True, "switchOnDuration": 15},
        ]

        # First relay — should advance to next relay form
        result = await flow.async_step_relay(
            {
                "relay_number": 1,
                "relay_name": "Door",
                "relay_device_type": "door",
                "relay_pulse_duration": 2000,
            },
            relay_index=0,
        )
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "relay")

        # Second relay — should create entry
        result = await flow.async_step_relay(
            {
                "relay_number": 2,
                "relay_name": "Gate",
                "relay_device_type": "gate",
                "relay_pulse_duration": 15000,
            },
            relay_index=1,
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(len(result["data"]["relays"]), 2)

    async def test_scan_interval_coerced_to_int(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
        )
        flow = self._make_options_flow(entry)
        result = await flow.async_step_device(
            {
                "name": "I",
                "enable_camera": False,
                "enable_doorbell": False,
                "scan_interval": 10.0,  # NumberSelector returns float
            }
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertIsInstance(result["data"]["scan_interval"], int)

    async def test_options_does_not_store_connection_settings(self) -> None:
        """Options flow output must not contain connection fields."""
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
        )
        flow = self._make_options_flow(entry)
        result = await flow.async_step_device(
            {
                "name": "Updated",
                "enable_camera": False,
                "enable_doorbell": True,
                "scan_interval": 5,
            }
        )
        self.assertEqual(result["type"], "create_entry")
        # Options should not contain connection fields
        self.assertNotIn("host", result["data"])
        self.assertNotIn("port", result["data"])
        self.assertNotIn("username", result["data"])
        self.assertNotIn("password", result["data"])

    async def test_device_step_defaults_from_options(self) -> None:
        """Device step should show current options as defaults."""
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
            options={"name": "Custom Name", "scan_interval": 15},
        )
        flow = self._make_options_flow(entry)
        result = await flow.async_step_device(None)
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "device")


class OptionsFlowNavigationTests(unittest.IsolatedAsyncioTestCase):
    """Forward-only navigation with Next/Submit labels and final-step saving."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config_flow_module = load_config_flow_module()
        cls.config_flow_module.TwoNIntercomAPI = FakeAPI

    def setUp(self) -> None:
        FakeAPI.instances = []
        FakeAPI.connection_result = True
        FakeAPI.system_info = {"serialNumber": "SN-123"}

    def _make_options_flow(self, entry: FakeConfigEntry):
        flow = self.config_flow_module.TwoNIntercomOptionsFlow(entry)
        flow.config_entry = entry
        flow.hass = FakeHass([entry])
        return flow

    def _make_entry(self, options: dict | None = None) -> FakeConfigEntry:
        return FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
            options=options,
        )

    # ---------------------------------------------------------- last_step

    async def test_device_step_is_last_when_camera_off_and_no_relays(self) -> None:
        entry = self._make_entry(options={"enable_camera": False})
        flow = self._make_options_flow(entry)
        result = await flow.async_step_device(None)
        self.assertEqual(result["step_id"], "device")
        self.assertIs(result["last_step"], True)

    async def test_device_step_not_last_when_camera_enabled(self) -> None:
        entry = self._make_entry(options={"enable_camera": True})
        flow = self._make_options_flow(entry)
        result = await flow.async_step_device(None)
        self.assertIs(result["last_step"], False)

    async def test_device_step_not_last_when_relays_detected(self) -> None:
        entry = self._make_entry(options={"enable_camera": False})
        entry.runtime_data = _make_runtime(
            [{"switch": 1, "enabled": True, "switchOnDuration": 5}]
        )
        flow = self._make_options_flow(entry)
        result = await flow.async_step_device(None)
        self.assertIs(result["last_step"], False)

    async def test_camera_step_last_step_depends_on_relays(self) -> None:
        entry = self._make_entry()
        flow = self._make_options_flow(entry)
        flow._detected_relays = []
        result = await flow.async_step_camera(None)
        self.assertIs(result["last_step"], True)

        flow = self._make_options_flow(entry)
        flow._detected_relays = [
            {"switch": 1, "enabled": True, "switchOnDuration": 5}
        ]
        result = await flow.async_step_camera(None)
        self.assertIs(result["last_step"], False)

    async def test_relay_step_last_step_matrix(self) -> None:
        entry = self._make_entry()
        flow = self._make_options_flow(entry)
        flow._detected_relays = [
            {"switch": 1, "enabled": True, "switchOnDuration": 5},
            {"switch": 2, "enabled": True, "switchOnDuration": 15},
        ]
        first = await flow.async_step_relay(None, relay_index=0)
        self.assertIs(first["last_step"], False)
        second = await flow.async_step_relay(None, relay_index=1)
        self.assertIs(second["last_step"], True)

        flow = self._make_options_flow(entry)
        flow._detected_relays = [
            {"switch": 1, "enabled": True, "switchOnDuration": 5}
        ]
        only = await flow.async_step_relay(None, relay_index=0)
        self.assertIs(only["last_step"], True)

    async def test_forward_only_flow_saves_all_values_only_on_final_step(self) -> None:
        for camera_enabled in (False, True):
            for relay_count in (0, 1, 2):
                with self.subTest(camera=camera_enabled, relays=relay_count):
                    saved_options = {
                        "name": "Saved name",
                        "enable_camera": camera_enabled,
                        "scan_interval": 60,
                    }
                    entry = self._make_entry(options=dict(saved_options))
                    entry.runtime_data = _make_runtime(
                        [
                            {"switch": number, "enabled": True, "switchOnDuration": 5}
                            for number in (1, 3)[:relay_count]
                        ]
                    )
                    flow = self._make_options_flow(entry)
                    device_input = {
                        "name": "Gatehouse",
                        "enable_camera": camera_enabled,
                        "enable_doorbell": True,
                        "scan_interval": 42,
                    }
                    camera_input = {
                        "live_view_mode": "mjpeg",
                        "camera_source": "internal",
                        "mjpeg_width": 800,
                        "mjpeg_height": 600,
                        "mjpeg_fps": 5,
                    }
                    relay_inputs = [
                        {
                            "relay_number": number,
                            "relay_name": f"Custom relay {number}",
                            "relay_device_type": "door",
                            "relay_pulse_duration": 2500,
                        }
                        for number in (1, 3)[:relay_count]
                    ]
                    steps = [("device", device_input)]
                    if camera_enabled:
                        steps.append(("camera", camera_input))
                    steps.extend(("relay", relay) for relay in relay_inputs)

                    with patch.object(
                        flow, "async_create_entry", wraps=flow.async_create_entry
                    ) as create_entry:
                        result = await flow.async_step_init(None)
                        for index, (step_id, payload) in enumerate(steps):
                            self.assertEqual(result["type"], "form")
                            self.assertEqual(result["step_id"], step_id)
                            self.assertIs(
                                result["last_step"], index == len(steps) - 1
                            )
                            self.assertNotIn(
                                "go_back",
                                {marker.key for marker in result["data_schema"].schema},
                            )
                            if step_id == "relay":
                                self.assertEqual(
                                    _form_default(result, "relay_number"),
                                    payload["relay_number"],
                                )
                            create_entry.assert_not_called()
                            self.assertEqual(entry.options, saved_options)
                            result = await getattr(flow, f"async_step_{step_id}")(
                                dict(payload)
                            )

                        self.assertEqual(result["type"], "create_entry")
                        create_entry.assert_called_once()

                    expected = {
                        **device_input,
                        "relays": relay_inputs,
                        "allow_insecure": False,
                    }
                    if camera_enabled:
                        expected.update(camera_input)
                    self.assertEqual(result["data"], expected)

    async def test_restarting_options_discards_unsaved_draft(self) -> None:
        saved_options = {
            "name": "Saved name",
            "enable_camera": True,
            "scan_interval": 60,
            "mjpeg_width": 640,
        }
        entry = self._make_entry(options=dict(saved_options))
        entry.runtime_data = _make_runtime([{"switch": 1, "enabled": True}])
        flow = self._make_options_flow(entry)
        await flow.async_step_device(
            {
                "name": "Unsaved name",
                "enable_camera": True,
                "enable_doorbell": True,
                "scan_interval": 42,
            }
        )
        result = await flow.async_step_camera(
            {
                "live_view_mode": "mjpeg",
                "camera_source": "internal",
                "mjpeg_width": 800,
                "mjpeg_height": 600,
                "mjpeg_fps": 5,
            }
        )
        self.assertEqual(result["step_id"], "relay")
        self.assertEqual(entry.options, saved_options)

        restarted_flow = self._make_options_flow(entry)
        result = await restarted_flow.async_step_init(None)
        self.assertEqual(result["step_id"], "device")
        self.assertEqual(_form_default(result, "name"), "Saved name")
        self.assertEqual(_form_default(result, "scan_interval"), 60)
        result = await restarted_flow.async_step_device(
            {
                "name": "Saved name",
                "enable_camera": True,
                "enable_doorbell": True,
                "scan_interval": 60,
            }
        )
        self.assertEqual(result["step_id"], "camera")
        self.assertEqual(_form_default(result, "mjpeg_width"), 640)
        self.assertEqual(entry.options, saved_options)


class OptionsFlowRtspCredentialsTests(unittest.IsolatedAsyncioTestCase):
    """TASK-15: RTSP password masking and keep/clear behaviour."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config_flow_module = load_config_flow_module()
        cls.config_flow_module.TwoNIntercomAPI = FakeAPI

    def setUp(self) -> None:
        FakeAPI.instances = []
        FakeAPI.connection_result = True
        FakeAPI.system_info = {"serialNumber": "SN-123"}

    def _make_options_flow(self, entry: FakeConfigEntry):
        flow = self.config_flow_module.TwoNIntercomOptionsFlow(entry)
        flow.config_entry = entry
        flow.hass = FakeHass([entry])
        return flow

    @staticmethod
    def _camera_input(**overrides):
        data = {
            "live_view_mode": "auto",
            "camera_source": "internal",
            "mjpeg_width": 640,
            "mjpeg_height": 480,
            "mjpeg_fps": 5,
        }
        data.update(overrides)
        return data

    async def test_rtsp_password_field_is_masked_and_not_prefilled(self) -> None:
        """The RTSP password uses a password-type selector and the stored
        value is never suggested back into the form."""
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
            options={"rtsp_username": "stream", "rtsp_password": "topsecret"},
        )
        flow = self._make_options_flow(entry)
        result = await flow.async_step_camera(None)
        self.assertEqual(result["step_id"], "camera")

        marker = _form_field_marker(result, "rtsp_password")
        field = result["data_schema"].schema[marker]
        selector_module = sys.modules["homeassistant.helpers.selector"]
        self.assertIsInstance(field, selector_module.TextSelector)
        self.assertEqual(field.config.type, "password")
        # No suggested_value -> the stored password is not rendered.
        description = getattr(marker, "description", None) or {}
        self.assertNotIn("suggested_value", description)

        # The username is not secret and stays pre-filled.
        self.assertEqual(
            _form_field_marker(result, "rtsp_username").description[
                "suggested_value"
            ],
            "stream",
        )

    async def test_empty_password_keeps_stored_password(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
            options={"rtsp_username": "stream", "rtsp_password": "topsecret"},
        )
        flow = self._make_options_flow(entry)
        result = await flow.async_step_camera(
            self._camera_input(rtsp_username="stream", rtsp_password="")
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["rtsp_username"], "stream")
        self.assertEqual(result["data"]["rtsp_password"], "topsecret")

    async def test_new_password_replaces_stored_password(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
            options={"rtsp_username": "stream", "rtsp_password": "topsecret"},
        )
        flow = self._make_options_flow(entry)
        result = await flow.async_step_camera(
            self._camera_input(rtsp_username="stream", rtsp_password="newpass")
        )
        self.assertEqual(result["data"]["rtsp_password"], "newpass")

    async def test_clearing_username_removes_credential_pair(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
            options={"rtsp_username": "stream", "rtsp_password": "topsecret"},
        )
        flow = self._make_options_flow(entry)
        result = await flow.async_step_camera(
            self._camera_input(rtsp_username="", rtsp_password="")
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertNotIn("rtsp_username", result["data"])
        self.assertNotIn("rtsp_password", result["data"])

    async def test_no_rtsp_credentials_stays_empty(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "192.0.2.20", "port": 443, "username": "u", "password": "p"},
        )
        flow = self._make_options_flow(entry)
        result = await flow.async_step_camera(self._camera_input())
        self.assertEqual(result["type"], "create_entry")
        self.assertNotIn("rtsp_username", result["data"])
        self.assertNotIn("rtsp_password", result["data"])


class ConfigFlowHelperTests(unittest.IsolatedAsyncioTestCase):
    """Tests for config_flow helper functions."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config_flow_module = load_config_flow_module()

    def test_all_calls_label_english(self) -> None:
        self.assertEqual(self.config_flow_module._all_calls_label("en"), "All calls")

    def test_all_calls_label_czech(self) -> None:
        self.assertEqual(self.config_flow_module._all_calls_label("cs"), "Vsechny hovory")

    async def test_async_get_called_peers_empty_on_failure(self) -> None:
        result = await self.config_flow_module._async_get_called_peers({
            "host": "192.0.2.99",
            "port": 443,
            "protocol": "https",
        })
        self.assertEqual(result, [])

    async def test_async_get_called_peers_with_dict_result(self) -> None:
        """Test _async_get_called_peers with a directory that returns users."""
        # We need to patch TwoNIntercomAPI to return test data
        original_api = self.config_flow_module.TwoNIntercomAPI

        class FakeAPI:
            def __init__(self, **kwargs):
                pass

            async def async_get_directory(self, *, raise_on_device_error=False):
                return [
                    {
                        "name": "John",
                        "callPos": [{"peer": "sip:100@device"}],
                    }
                ]

            async def async_close(self):
                pass

        self.config_flow_module.TwoNIntercomAPI = FakeAPI
        try:
            result = await self.config_flow_module._async_get_called_peers({
                "host": "192.0.2.20",
                "port": 443,
                "protocol": "https",
            })
            self.assertEqual(result, ["sip:100@device"])
        finally:
            self.config_flow_module.TwoNIntercomAPI = original_api

    async def test_async_get_called_peers_dict_directory_with_users(self) -> None:
        """When directory returns a dict with 'users' key."""
        original_api = self.config_flow_module.TwoNIntercomAPI

        class FakeAPI:
            def __init__(self, **kwargs):
                pass

            async def async_get_directory(self, *, raise_on_device_error=False):
                return {
                    "users": [
                        {"name": "Jane", "callPos": [{"peer": "sip:200@device"}]}
                    ]
                }

            async def async_close(self):
                pass

        self.config_flow_module.TwoNIntercomAPI = FakeAPI
        try:
            result = await self.config_flow_module._async_get_called_peers({
                "host": "192.0.2.20",
            })
            self.assertEqual(result, ["sip:200@device"])
        finally:
            self.config_flow_module.TwoNIntercomAPI = original_api

    async def test_async_get_called_peers_dict_directory_with_result(self) -> None:
        """When directory returns a dict with 'result' key containing users."""
        original_api = self.config_flow_module.TwoNIntercomAPI

        class FakeAPI:
            def __init__(self, **kwargs):
                pass

            async def async_get_directory(self, *, raise_on_device_error=False):
                return {
                    "result": {
                        "users": [
                            {"name": "Bob", "callPos": [{"peer": "sip:300@device"}]}
                        ]
                    }
                }

            async def async_close(self):
                pass

        self.config_flow_module.TwoNIntercomAPI = FakeAPI
        try:
            result = await self.config_flow_module._async_get_called_peers({
                "host": "192.0.2.20",
            })
            self.assertEqual(result, ["sip:300@device"])
        finally:
            self.config_flow_module.TwoNIntercomAPI = original_api

    async def test_async_get_called_peers_dict_directory_result_list(self) -> None:
        """When directory result is a list."""
        original_api = self.config_flow_module.TwoNIntercomAPI

        class FakeAPI:
            def __init__(self, **kwargs):
                pass

            async def async_get_directory(self, *, raise_on_device_error=False):
                return {
                    "result": [
                        {"name": "Alice", "callPos": [{"peer": "sip:400@device"}]}
                    ]
                }

            async def async_close(self):
                pass

        self.config_flow_module.TwoNIntercomAPI = FakeAPI
        try:
            result = await self.config_flow_module._async_get_called_peers({
                "host": "192.0.2.20",
            })
            self.assertEqual(result, ["sip:400@device"])
        finally:
            self.config_flow_module.TwoNIntercomAPI = original_api

    async def test_async_get_called_peers_list_with_users_key(self) -> None:
        """When directory returns list entries containing 'users' key."""
        original_api = self.config_flow_module.TwoNIntercomAPI

        class FakeAPI:
            def __init__(self, **kwargs):
                pass

            async def async_get_directory(self, *, raise_on_device_error=False):
                return [
                    {
                        "users": [
                            {"name": "Dave", "callPos": [{"peer": "sip:500@device"}]}
                        ]
                    }
                ]

            async def async_close(self):
                pass

        self.config_flow_module.TwoNIntercomAPI = FakeAPI
        try:
            result = await self.config_flow_module._async_get_called_peers({
                "host": "192.0.2.20",
            })
            self.assertEqual(result, ["sip:500@device"])
        finally:
            self.config_flow_module.TwoNIntercomAPI = original_api


class ConfigFlowErrorStringsTests(unittest.TestCase):
    """Every error key the config flow can show has a translated string."""

    def test_config_error_keys_are_translated(self) -> None:
        import json
        import re

        source = CONFIG_FLOW_PATH.read_text(encoding="utf-8")
        config_source, options_source = source.split("class TwoNIntercomOptionsFlow", 1)
        error_pattern = r'errors\["base"\]\s*=\s*"([a-z_]+)"'
        used = set(re.findall(error_pattern, config_source))
        options_used = set(re.findall(error_pattern, options_source))
        self.assertIn("invalid_auth", used)
        self.assertIn("directory_unavailable", options_used)

        integration_dir = CONFIG_FLOW_PATH.parent
        for name in (
            "strings.json",
            "translations/en.json",
            "translations/cs.json",
            "translations/de.json",
        ):
            with self.subTest(file=name):
                strings = json.loads(
                    (integration_dir / name).read_text(encoding="utf-8")
                )
                self.assertLessEqual(used, set(strings["config"]["error"]))
                self.assertLessEqual(options_used, set(strings["options"]["error"]))


if __name__ == "__main__":
    unittest.main()
