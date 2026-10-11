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

import sys
import types
import unittest
import json

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


def _form_values(result):
    return {
        field.key: (
            field.description["suggested_value"]
            if field.description and "suggested_value" in field.description
            else field.default
        )
        for field in result["data_schema"].schema
    }


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

    selector_module.SelectSelector = SelectSelector
    selector_module.SelectSelectorConfig = SelectSelectorConfig
    selector_module.SelectSelectorMode = SelectSelectorMode
    selector_module.SelectOptionDict = SelectOptionDict
    selector_module.NumberSelector = NumberSelector
    selector_module.NumberSelectorConfig = NumberSelectorConfig
    selector_module.NumberSelectorMode = NumberSelectorMode
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
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.protocol = protocol
        self.verify_ssl = verify_ssl
        self.closed = False
        FakeAPI.instances.append(self)

    async def async_test_connection(self) -> bool:
        return FakeAPI.connection_result

    async def async_get_system_info(self) -> dict:
        return FakeAPI.system_info

    async def async_get_directory(self):
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

    def async_update_entry(self, entry, *, data=None, **_kwargs):
        if data is not None:
            entry.data = data
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
        # Every API the flow opens is also closed — no resource leaks.
        self.assertGreaterEqual(len(FakeAPI.instances), 1)
        self.assertTrue(all(instance.closed for instance in FakeAPI.instances))

    async def test_setup_back_preserves_device_draft_and_connection_fields(self) -> None:
        flow = self._make_flow()
        result = await flow.async_step_user()
        self.assertFalse(result["last_step"])
        result = await flow.async_step_user({
            "host": "192.0.2.20", "username": "user", "password": "original",
        })
        self.assertTrue(result["last_step"])
        device = {
            **_form_values(result),
            "name": "Front door",
            "enable_camera": False,
            "called_id": "101",
            "go_back": True,
        }
        result = await flow.async_step_device(device)
        self.assertEqual(result["step_id"], "user")
        connection = _form_values(result)
        self.assertEqual(connection["host"], "192.0.2.20")
        self.assertEqual(connection["password"], "original")
        self.assertNotIn("go_back", flow._data)
        self.assertTrue(device["go_back"])

        result = await flow.async_step_user({**connection, "password": "updated"})
        values = _form_values(result)
        self.assertEqual(values["name"], "Front door")
        self.assertFalse(values["enable_camera"])
        self.assertEqual(values["called_id"], "101")
        self.assertFalse(values["go_back"])
        result = await flow.async_step_device(values)
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["password"], "updated")
        self.assertNotIn("go_back", result["data"])

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

    def _entry_with_relays(self, camera=True):
        entry = FakeConfigEntry(
            "entry-1",
            {
                "host": "192.0.2.20", "port": 443, "username": "user",
                "password": "secret", "enable_camera": camera,
            },
            options={"name": "Saved name", "scan_interval": 60},
        )
        entry.runtime_data = types.SimpleNamespace(
            coordinator=types.SimpleNamespace(switch_caps={
                "switches": [
                    {"switch": 1, "enabled": True, "switchOnDuration": 2},
                    {"switch": 3, "enabled": True, "switchOnDuration": 15},
                ],
            }),
        )
        return entry

    async def test_backtracking_preserves_all_drafts_without_duplicate_relays(self) -> None:
        entry = self._entry_with_relays()
        original_options = dict(entry.options)
        flow = self._make_options_flow(entry)
        device = await flow.async_step_init()
        self.assertFalse(device["last_step"])
        camera = await flow.async_step_device({
            **_form_values(device), "name": "New name", "scan_interval": 30,
        })
        self.assertFalse(camera["last_step"])
        relay1 = await flow.async_step_camera({
            **_form_values(camera), "mjpeg_fps": 5,
            "rtsp_username": "stream", "rtsp_password": "stream secret",
        })
        self.assertFalse(relay1["last_step"])
        relay2 = await flow.async_step_relay({
            **_form_values(relay1), "relay_name": "Door",
        })
        self.assertTrue(relay2["last_step"])
        self.assertEqual(_form_values(relay2)["relay_number"], 3)
        relay1 = await flow.async_step_relay({
            **_form_values(relay2), "relay_name": "Gate", "go_back": True,
        })
        self.assertEqual(_form_values(relay1)["relay_name"], "Door")
        self.assertFalse(_form_values(relay1)["go_back"])
        camera = await flow.async_step_relay({
            **_form_values(relay1), "relay_name": "Front door", "go_back": True,
        })
        self.assertEqual(camera["step_id"], "camera")
        self.assertEqual(_form_values(camera)["mjpeg_fps"], 5)
        self.assertEqual(_form_values(camera)["rtsp_password"], "stream secret")
        device = await flow.async_step_camera({
            **_form_values(camera), "mjpeg_width": 640, "go_back": True,
        })
        self.assertEqual(_form_values(device)["name"], "New name")
        self.assertEqual(_form_values(device)["scan_interval"], 30)
        self.assertNotIn("go_back", _form_values(device))
        self.assertEqual(entry.options, original_options)

        camera = await flow.async_step_device(_form_values(device))
        self.assertEqual(_form_values(camera)["mjpeg_width"], 640)
        self.assertFalse(_form_values(camera)["go_back"])
        relay1 = await flow.async_step_camera(_form_values(camera))
        self.assertEqual(_form_values(relay1)["relay_name"], "Front door")
        relay2 = await flow.async_step_relay(_form_values(relay1))
        self.assertEqual(_form_values(relay2)["relay_name"], "Gate")
        self.assertTrue(relay2["last_step"])
        result = await flow.async_step_relay(_form_values(relay2))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["name"], "New name")
        self.assertEqual(result["data"]["mjpeg_fps"], 5)
        self.assertEqual(result["data"]["rtsp_password"], "stream secret")
        self.assertEqual(
            [relay["relay_number"] for relay in result["data"]["relays"]], [1, 3]
        )
        self.assertNotIn("go_back", result["data"])
        self.assertTrue(all("go_back" not in r for r in result["data"]["relays"]))
        self.assertEqual(entry.options, original_options)
        self.assertEqual(flow.hass.config_entries.reload_calls, [])

    async def test_first_relay_returns_to_device_when_camera_disabled(self) -> None:
        flow = self._make_options_flow(self._entry_with_relays(camera=False))
        device = await flow.async_step_init()
        relay = await flow.async_step_device(_form_values(device))
        self.assertEqual(relay["step_id"], "relay")
        device = await flow.async_step_relay({
            **_form_values(relay), "relay_name": "Draft relay", "go_back": True,
        })
        self.assertEqual(device["step_id"], "device")
        relay = await flow.async_step_device(_form_values(device))
        self.assertEqual(_form_values(relay)["relay_name"], "Draft relay")

    async def test_disabling_camera_after_going_back_keeps_camera_preferences(self) -> None:
        entry = self._entry_with_relays()
        entry.options.update({"rtsp_username": "old", "rtsp_password": "old secret"})
        flow = self._make_options_flow(entry)
        device = await flow.async_step_init()
        camera = await flow.async_step_device(_form_values(device))
        device = await flow.async_step_camera({
            **_form_values(camera), "mjpeg_fps": 7, "go_back": True,
        })
        relay = await flow.async_step_device({
            **_form_values(device), "enable_camera": False,
        })
        device = await flow.async_step_relay({
            **_form_values(relay), "go_back": True,
        })
        self.assertEqual(device["step_id"], "device")
        relay = await flow.async_step_device(_form_values(device))
        relay = await flow.async_step_relay(_form_values(relay))
        result = await flow.async_step_relay(_form_values(relay))
        self.assertFalse(result["data"]["enable_camera"])
        self.assertEqual(result["data"]["mjpeg_fps"], 7)
        self.assertEqual(result["data"]["rtsp_password"], "old secret")

    async def test_last_camera_step_can_go_back_and_clear_rtsp_credentials(self) -> None:
        entry = self._entry_with_relays()
        entry.runtime_data = None
        entry.options.update({"rtsp_username": "old", "rtsp_password": "old secret"})
        flow = self._make_options_flow(entry)
        device = await flow.async_step_init()
        camera = await flow.async_step_device(_form_values(device))
        self.assertTrue(camera["last_step"])
        values = _form_values(camera)
        values.pop("rtsp_username")
        values.pop("rtsp_password")
        values["go_back"] = True
        device = await flow.async_step_camera(values)
        self.assertEqual(device["step_id"], "device")
        camera = await flow.async_step_device(_form_values(device))
        self.assertEqual(_form_values(camera)["rtsp_password"], "")
        result = await flow.async_step_camera(_form_values(camera))
        self.assertEqual(result["data"]["rtsp_username"], "")
        self.assertEqual(result["data"]["rtsp_password"], "")

    async def test_skipped_steps_keep_saved_settings_but_not_legacy_credentials(self) -> None:
        entry = self._entry_with_relays(camera=False)
        entry.runtime_data = None
        saved_relays = [{
            "relay_number": 1, "relay_name": "Door",
            "relay_device_type": "door", "relay_pulse_duration": 2500,
        }]
        entry.options.update({
            "rtsp_username": "stream", "rtsp_password": "stream secret",
            "mjpeg_fps": 7, "relays": saved_relays,
            "host": "old-host", "password": "old-password", "go_back": True,
        })
        flow = self._make_options_flow(entry)
        device = await flow.async_step_init()
        result = await flow.async_step_device(_form_values(device))
        self.assertEqual(result["data"]["relays"], saved_relays)
        self.assertEqual(result["data"]["rtsp_password"], "stream secret")
        self.assertEqual(result["data"]["mjpeg_fps"], 7)
        for key in ("host", "password", "go_back"):
            self.assertNotIn(key, result["data"])

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
        flow._relays = []
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
        flow._relays = []
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
        flow._relays = []
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


class FlowTranslationTests(unittest.TestCase):
    def test_navigation_and_http_api_forms_have_translations(self) -> None:
        component = CONFIG_FLOW_PATH.parent
        source = json.loads((component / "strings.json").read_text())
        for language in ("en", "cs", "de"):
            with self.subTest(language=language):
                translated = json.loads(
                    (component / "translations" / f"{language}.json").read_text()
                )
                for section, steps in (
                    ("config", ("user", "device", "reconfigure", "reauth_confirm")),
                    ("options", ("device", "camera", "relay")),
                ):
                    for step in steps:
                        expected = source[section]["step"][step]
                        actual = translated[section]["step"][step]
                        self.assertEqual(set(actual["data"]), set(expected["data"]))
                        self.assertTrue(actual["title"])
                        self.assertTrue(actual["description"])
                        # A static submit label would override HA's Next/Submit choice.
                        self.assertNotIn("submit", actual)
                self.assertIn(
                    "{host}", translated["config"]["step"]["reauth_confirm"]["description"]
                )
                self.assertIn("invalid_auth", translated["config"]["error"])
                for section, step in (
                    ("config", "device"), ("options", "camera"), ("options", "relay"),
                ):
                    self.assertTrue(
                        translated[section]["step"][step]["data_description"]["go_back"]
                    )


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

            async def async_get_directory(self):
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

            async def async_get_directory(self):
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

            async def async_get_directory(self):
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

            async def async_get_directory(self):
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

            async def async_get_directory(self):
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


if __name__ == "__main__":
    unittest.main()
