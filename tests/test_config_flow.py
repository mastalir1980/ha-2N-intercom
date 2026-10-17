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

from contextlib import asynccontextmanager
import logging
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from _stubs import (
    API_PATH,
    CONFIG_FLOW_PATH,
    CONST_PATH,
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


def load_config_flow_module():
    install_api_stubs()
    _install_voluptuous_stub()
    _install_homeassistant_stubs()
    ensure_package("custom_components")
    ensure_package("custom_components.2n_intercom")
    load_module("custom_components.2n_intercom.const", CONST_PATH)
    load_module("custom_components.2n_intercom.api", API_PATH)
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
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.protocol = protocol
        self.verify_ssl = verify_ssl
        self.allow_insecure = allow_insecure
        self.closed = False
        FakeAPI.instances.append(self)

    async def async_test_connection(self) -> bool:
        return FakeAPI.connection_result

    async def async_get_system_info(self) -> dict:
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

    async def async_add_executor_job(self, func, *args):
        return func(*args)


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
        cls.config_flow_module.TwoNIntercomAPI = FakeAPI

    def setUp(self) -> None:
        FakeAPI.instances = []
        FakeAPI.connection_result = True

    def _make_flow(self, hass: FakeHass | None = None):
        flow = self.config_flow_module.TwoNIntercomConfigFlow()
        flow.hass = hass or FakeHass([])
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
        self.assertTrue(field.config.custom_value)
        self.assertEqual(
            field.config.options,
            [
                {"label": "Alice", "value": "aaaa-1"},
                {"label": "BBBB-2 (no name)", "value": "BBBB-2"},
            ],
        )
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
