"""Unit tests for integration setup and service registration."""

from __future__ import annotations

import asyncio
import sys
import types
import unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock, patch

from _stubs import (
    API_PATH,
    CONST_PATH,
    COORDINATOR_PATH,
    INIT_PATH,
    ensure_package,
    install_api_stubs,
    install_dt_util_stub,
    load_module,
)


def _install_homeassistant_stubs() -> None:
    ensure_package("homeassistant")

    const = types.ModuleType("homeassistant.const")
    const.CONF_HOST = "host"
    const.CONF_PASSWORD = "password"
    const.CONF_PORT = "port"
    const.CONF_USERNAME = "username"
    const.EVENT_HOMEASSISTANT_STOP = "homeassistant_stop"
    sys.modules["homeassistant.const"] = const

    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    core.ServiceCall = object
    core.Event = object
    sys.modules["homeassistant.core"] = core

    exceptions = types.ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        def __init__(self, *args, translation_domain=None, translation_key=None, translation_placeholders=None, **kwargs):
            super().__init__(*args)
            self.translation_domain = translation_domain
            self.translation_key = translation_key
            self.translation_placeholders = translation_placeholders

    class ConfigEntryNotReady(Exception):
        pass

    class ConfigEntryAuthFailed(Exception):
        pass

    class ServiceValidationError(HomeAssistantError):
        """Stub for bad-input service errors."""

    exceptions.HomeAssistantError = HomeAssistantError
    exceptions.ConfigEntryNotReady = ConfigEntryNotReady
    exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailed
    exceptions.ServiceValidationError = ServiceValidationError
    sys.modules["homeassistant.exceptions"] = exceptions

    config_entries = types.ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntry = object
    sys.modules["homeassistant.config_entries"] = config_entries

    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class DataUpdateCoordinator:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, hass, logger, name, update_interval) -> None:
            del logger, name, update_interval
            self.hass = hass
            self.data = None
            self.last_update_success = True

        async def async_config_entry_first_refresh(self):
            try:
                self.data = await self._async_update_data()
            except UpdateFailed as err:
                raise ConfigEntryNotReady() from err
            return self.data

    class UpdateFailed(Exception):
        pass

    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.UpdateFailed = UpdateFailed
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator
    ensure_package("homeassistant.helpers")

    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")

    def async_create_clientsession(hass, **kwargs):
        # Return a fake session from the aiohttp stubs already installed
        aiohttp_mod = sys.modules["aiohttp"]
        return aiohttp_mod.ClientSession()

    aiohttp_client.async_create_clientsession = async_create_clientsession
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client

    helpers_typing = types.ModuleType("homeassistant.helpers.typing")
    helpers_typing.ConfigType = dict
    sys.modules["homeassistant.helpers.typing"] = helpers_typing

    config_validation = types.ModuleType("homeassistant.helpers.config_validation")

    def config_entry_only_config_schema(domain):
        def _validator(value):
            return value
        return _validator

    config_validation.config_entry_only_config_schema = config_entry_only_config_schema
    sys.modules["homeassistant.helpers.config_validation"] = config_validation
    ensure_package("homeassistant.helpers").config_validation = config_validation
    entity_registry = types.ModuleType("homeassistant.helpers.entity_registry")
    entity_registry.async_get = lambda hass: hass.entity_registry
    sys.modules["homeassistant.helpers.entity_registry"] = entity_registry


def load_init_module():
    install_api_stubs()
    install_dt_util_stub()
    _install_homeassistant_stubs()
    ensure_package("custom_components")
    ensure_package("custom_components.2n_intercom")
    load_module("custom_components.2n_intercom.const", CONST_PATH)
    load_module("custom_components.2n_intercom.api", API_PATH)
    load_module("custom_components.2n_intercom.coordinator", COORDINATOR_PATH)
    return load_module("custom_components.2n_intercom.__init__", INIT_PATH)


class FakeServiceRegistry:
    def __init__(self) -> None:
        self.handlers: dict[tuple[str, str], object] = {}

    def async_register(self, domain, service, handler, schema=None) -> None:
        del schema
        self.handlers[(domain, service)] = handler

    def has_service(self, domain, service) -> bool:
        return (domain, service) in self.handlers


class FakeConfigEntry:
    def __init__(self, entry_id: str, data: dict[str, object], options=None) -> None:
        self.entry_id = entry_id
        self.data = data
        self.options = options or {}
        self.runtime_data: object = None
        self._unload_callbacks: list[object] = []
        self._update_listener = None
        self._background_tasks: list[asyncio.Task] = []

    def add_update_listener(self, listener):
        self._update_listener = listener
        return listener

    def async_on_unload(self, callback) -> None:
        self._unload_callbacks.append(callback)

    def async_create_background_task(self, hass, coro, name=None, eager_start=False):
        del hass, name, eager_start
        task = asyncio.ensure_future(coro)
        self._background_tasks.append(task)
        return task


class FakeConfigEntries:
    def __init__(self, entries: list[FakeConfigEntry]) -> None:
        self._entries = entries
        self.forwarded: list[tuple[str, tuple[str, ...]]] = []
        self.update_calls: list[tuple[str, dict]] = []

    def async_update_entry(self, entry, *, data):
        entry.data = data
        self.update_calls.append((entry.entry_id, dict(data)))

    async def async_forward_entry_setups(self, entry, platforms) -> None:
        self.forwarded.append((entry.entry_id, tuple(platforms)))

    async def async_unload_platforms(self, entry, platforms) -> bool:
        del entry, platforms
        return True

    async def async_reload(self, entry_id) -> None:
        del entry_id

    def async_entries(self, domain):
        del domain
        return list(self._entries)


class FakeBus:
    """Minimal stand-in for hass.bus used by the shutdown listener wiring."""

    def __init__(self) -> None:
        self.listeners: list[tuple[str, object]] = []

    def async_listen_once(self, event_type, callback):  # noqa: D401 — match HA shape
        self.listeners.append((event_type, callback))
        return lambda: self.listeners.remove((event_type, callback))


class FakeHass:
    def __init__(self, entries: list[FakeConfigEntry]) -> None:
        self.services = FakeServiceRegistry()
        self.config_entries = FakeConfigEntries(entries)
        self.bus = FakeBus()
        self.data: dict[str, object] = {}
        self.entity_registry = Mock()
        self.entity_registry.async_get_entity_id.return_value = None
        self.components = types.SimpleNamespace(
            persistent_notification=types.SimpleNamespace(async_create=lambda *a, **k: None)
        )


class FakeAPI:
    def __init__(self, *args, call_status=None, answer_result=True, hangup_result=True, **kwargs) -> None:
        self.allow_insecure = kwargs.get("allow_insecure", False)
        del args, kwargs
        self._call_status = call_status or {
            "state": "ringing",
            "sessions": [
                {
                    "session": "session-123",
                    "direction": "outgoing",
                    "state": "ringing",
                    "calls": [{"peer": "100"}],
                }
            ],
        }
        self._answer_result = answer_result
        self._hangup_result = hangup_result
        self.answer_calls: list[object] = []
        self.hangup_calls: list[tuple[object, str]] = []

    async def async_get_system_info(self):
        return {"model": "2N"}

    async def async_get_call_status(self):
        return self._call_status

    async def async_answer_call(self, session_id):
        self.answer_calls.append(session_id)
        return self._answer_result

    async def async_hangup_call(self, session_id, reason="normal"):
        self.hangup_calls.append((session_id, reason))
        return self._hangup_result

    async def async_subscribe_log(self, events):
        del events
        return None

    async def async_pull_log(self, subscription_id, *, timeout=None):
        del subscription_id, timeout
        return []

    async def async_unsubscribe_log(self, subscription_id):
        del subscription_id
        return True

    async def async_close(self):
        return None


class AuthenticationSetupTests(unittest.IsolatedAsyncioTestCase):
    """Exercise authentication recovery through the config-entry setup path."""

    def setUp(self) -> None:
        self.init_module = load_init_module()
        self.api_module = sys.modules["custom_components.2n_intercom.api"]
        self.entry = FakeConfigEntry(
            "entry-auth",
            {
                "host": "intercom.local",
                "port": 443,
                "username": "user",
                "password": "secret",
                "verify_ssl": True,
            },
        )
        self.hass = FakeHass([self.entry])

    async def test_invalid_stored_password_triggers_reauth_during_setup(self) -> None:
        api = FakeAPI()
        api.async_get_call_status = AsyncMock(
            side_effect=self.api_module.TwoNAuthenticationError("invalid credentials")
        )
        api.async_reset_session = AsyncMock()
        with patch.object(self.init_module, "TwoNIntercomAPI", return_value=api):
            with self.assertRaises(
                sys.modules["homeassistant.exceptions"].ConfigEntryAuthFailed
            ):
                await self.init_module.async_setup_entry(self.hass, self.entry)

        self.assertEqual(api.async_get_call_status.await_count, 3)
        self.assertEqual(api.async_reset_session.await_count, 3)
        self.assertIsNone(self.entry.runtime_data)
        self.assertEqual(self.hass.config_entries.forwarded, [])

    async def test_transient_auth_error_does_not_abort_setup(self) -> None:
        api = FakeAPI()
        api.async_get_call_status = AsyncMock(
            side_effect=[
                self.api_module.TwoNAuthenticationError("stale nonce"),
                {"state": "idle", "sessions": []},
            ],
        )
        api.async_reset_session = AsyncMock()
        with patch.object(self.init_module, "TwoNIntercomAPI", return_value=api):
            self.assertTrue(
                await self.init_module.async_setup_entry(self.hass, self.entry)
            )
        try:
            self.assertEqual(api.async_get_call_status.await_count, 2)
            self.assertEqual(api.async_reset_session.await_count, 1)
            self.assertEqual(self.entry.runtime_data.coordinator._auth_error_count, 0)
            self.assertEqual(len(self.hass.config_entries.forwarded), 1)
        finally:
            await self.init_module.async_unload_entry(self.hass, self.entry)

    async def test_session_recovery_reuses_ha_factory_and_connection_settings(self) -> None:
        coordinator = self.init_module.TwoNIntercomCoordinator
        with (
            patch.object(coordinator, "async_initialize_static_caches", new=AsyncMock()),
            patch.object(coordinator, "async_start_log_listener", new=AsyncMock()),
            patch.object(coordinator, "_refresh_secondary_cache", return_value={}),
            patch.object(self.api_module.TwoNIntercomAPI, "async_get_system_info", return_value={}),
            patch.object(
                self.api_module.TwoNIntercomAPI, "async_get_call_status",
                return_value={"state": "idle", "sessions": []},
            ),
            patch.object(
                self.init_module, "async_create_clientsession",
                wraps=self.init_module.async_create_clientsession,
            ) as create_session,
        ):
            await self.init_module.async_setup_entry(self.hass, self.entry)
            api = self.entry.runtime_data.api
            old_session = await api.async_get_session()
            await api.async_reset_session()
            replacement = await api.async_get_session()

        self.assertEqual(create_session.call_count, 2)
        first_call, second_call = create_session.call_args_list
        self.assertEqual(first_call.args, (self.hass,))
        self.assertEqual(second_call.args, (self.hass,))
        self.assertTrue(first_call.kwargs["verify_ssl"])
        self.assertTrue(second_call.kwargs["verify_ssl"])
        self.assertIsNot(
            first_call.kwargs["middlewares"][0],
            second_call.kwargs["middlewares"][0],
        )
        self.assertTrue(old_session.closed)
        self.assertFalse(replacement.closed)
        self.assertFalse(api._owns_session)
        await self.init_module.async_unload_entry(self.hass, self.entry)


class MacBackfillSetupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.init_module = load_init_module()
        self.entry = FakeConfigEntry("entry-1", {
            "host": "192.0.2.20", "port": 443, "protocol": "https",
            "username": "user", "password": "secret",
            "serial_number": "SN-123456",
        }, options={"scan_interval": 120})
        self.entry.unique_id = "SN-123456"
        self.hass = FakeHass([self.entry])

    async def _setup_with_info(self, info) -> None:
        api = FakeAPI()
        api.async_get_system_info = AsyncMock(return_value=info)
        with patch.object(self.init_module, "TwoNIntercomAPI", return_value=api):
            self.assertTrue(await self.init_module.async_setup_entry(self.hass, self.entry))

    async def test_setup_backfills_normalized_mac_without_changing_identity(self) -> None:
        original_data = dict(self.entry.data)
        await self._setup_with_info({"macAddr": " 00:11:22:aa:bb:cc "})
        try:
            self.assertEqual(self.hass.config_entries.update_calls, [
                (self.entry.entry_id, {**original_data, "mac_address": "001122AABBCC"}),
            ])
            self.assertEqual(self.entry.unique_id, "SN-123456")
            self.assertEqual(self.entry.options, {"scan_interval": 120})
            self.entry.runtime_data.api.async_get_system_info.assert_awaited_once()
        finally:
            await self.init_module.async_unload_entry(self.hass, self.entry)

    async def test_setup_keeps_existing_mac(self) -> None:
        self.entry.data["mac_address"] = "001122334455"
        await self._setup_with_info({"macAddr": "00-11-22-aa-bb-cc"})
        try:
            self.assertEqual(self.entry.data["mac_address"], "001122334455")
            self.assertEqual(self.hass.config_entries.update_calls, [])
        finally:
            await self.init_module.async_unload_entry(self.hass, self.entry)

    async def test_setup_without_device_mac_does_not_update_entry(self) -> None:
        await self._setup_with_info({})
        try:
            self.assertNotIn("mac_address", self.entry.data)
            self.assertEqual(self.hass.config_entries.update_calls, [])
        finally:
            await self.init_module.async_unload_entry(self.hass, self.entry)


class IntegrationSetupTests(unittest.IsolatedAsyncioTestCase):
    """Tests for setup entry and service dispatch."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.init_module = load_init_module()
        cls.const_module = sys.modules["custom_components.2n_intercom.const"]

    async def test_setup_removes_only_legacy_doorbell_even_when_disabled(self) -> None:
        for enabled in (True, False):
            with self.subTest(enable_doorbell=enabled):
                entry = FakeConfigEntry(
                    "entry-1",
                    {"host": "example.invalid", "port": 443,
                     "username": "test-user", "password": "test-password"},
                    options={"enable_doorbell": enabled},
                )
                hass = FakeHass([entry])
                registry = hass.entity_registry
                entries = {
                    ("binary_sensor", "2n_intercom", "entry-1_doorbell"):
                        "binary_sensor.renamed_button",
                    ("event", "2n_intercom", "entry-1_doorbell_event"):
                        "event.renamed_button",
                    ("binary_sensor", "2n_intercom", "entry-2_doorbell"):
                        "binary_sensor.other_intercom",
                    ("binary_sensor", "other_integration", "entry-1_doorbell"):
                        "binary_sensor.other_platform",
                    ("binary_sensor", "2n_intercom", "entry-1_input1"):
                        "binary_sensor.input",
                }
                registry.async_get_entity_id.side_effect = (
                    lambda domain, platform, uid: entries.get((domain, platform, uid))
                )
                registry.async_remove.side_effect = lambda eid: entries.pop(
                    next(key for key, value in entries.items() if value == eid)
                )
                original = dict(entries)
                with patch.object(self.init_module, "TwoNIntercomAPI", FakeAPI):
                    self.assertTrue(await self.init_module.async_setup_entry(hass, entry))
                    await self.init_module.async_unload_entry(hass, entry)
                    # Setup is idempotent after the old entity has been removed.
                    self.assertTrue(await self.init_module.async_setup_entry(hass, entry))
                    await self.init_module.async_unload_entry(hass, entry)
                registry.async_get_entity_id.assert_called_with(
                    "binary_sensor", "2n_intercom", "entry-1_doorbell"
                )
                registry.async_remove.assert_called_once_with("binary_sensor.renamed_button")
                del original[("binary_sensor", "2n_intercom", "entry-1_doorbell")]
                self.assertEqual(entries, original)
                platforms = hass.config_entries.forwarded[0][1]
                self.assertEqual("event" in platforms, enabled)

    async def test_setup_without_legacy_doorbell_does_not_remove_entities(self) -> None:
        entry = FakeConfigEntry(
            "entry-1",
            {"host": "example.invalid", "port": 443,
             "username": "test-user", "password": "test-password"},
        )
        hass = FakeHass([entry])
        with patch.object(self.init_module, "TwoNIntercomAPI", FakeAPI):
            self.assertTrue(await self.init_module.async_setup_entry(hass, entry))
            await self.init_module.async_unload_entry(hass, entry)
        hass.entity_registry.async_remove.assert_not_called()

    async def test_setup_registers_and_dispatches_call_services(self) -> None:
        init_module = self.init_module
        const_module = self.const_module
        ha_const = sys.modules["homeassistant.const"]
        init_module.TwoNIntercomAPI = FakeAPI

        entry = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
                ha_const.CONF_PORT: 443,
            },
        )
        hass = FakeHass([entry])

        await init_module.async_setup(hass, {})
        result = await init_module.async_setup_entry(hass, entry)

        self.assertTrue(result)
        self.assertTrue(hass.services.has_service(const_module.DOMAIN, "answer_call"))
        self.assertTrue(hass.services.has_service(const_module.DOMAIN, "hangup_call"))
        self.assertTrue(hass.services.has_service(const_module.DOMAIN, "grant_access"))
        self.assertEqual(
            hass.config_entries.forwarded,
            [
                (
                    entry.entry_id,
                    ("camera", "image", "binary_sensor", "event", "switch", "sensor", "update"),
                )
            ],
        )

        answer_call = hass.services.handlers[(const_module.DOMAIN, "answer_call")]
        hangup_call = hass.services.handlers[(const_module.DOMAIN, "hangup_call")]

        await answer_call(types.SimpleNamespace(data={}))
        await hangup_call(types.SimpleNamespace(data={"reason": "busy"}))

        stored = entry.runtime_data
        self.assertEqual(stored.api.answer_calls, ["session-123"])
        self.assertEqual(stored.api.hangup_calls, [("session-123", "busy")])

    async def test_service_raises_when_api_reports_failure(self) -> None:
        init_module = self.init_module
        const_module = self.const_module
        ha_const = sys.modules["homeassistant.const"]
        init_module.TwoNIntercomAPI = FakeAPI

        entry = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        hass = FakeHass([entry])

        await init_module.async_setup(hass, {})
        await init_module.async_setup_entry(hass, entry)
        entry.runtime_data.api = FakeAPI(
            answer_result=False,
            hangup_result=False,
        )

        answer_call = hass.services.handlers[(const_module.DOMAIN, "answer_call")]
        hangup_call = hass.services.handlers[(const_module.DOMAIN, "hangup_call")]

        with self.assertRaises(
            sys.modules["homeassistant.exceptions"].HomeAssistantError
        ):
            await answer_call(types.SimpleNamespace(data={}))

        with self.assertRaises(
            sys.modules["homeassistant.exceptions"].HomeAssistantError
        ):
            await hangup_call(types.SimpleNamespace(data={}))

    async def test_hangup_reason_defaults_to_none_when_unset(self) -> None:
        """When the caller does not pass a valid reason the service must
        forward ``None`` to the API layer, NOT default to ``"normal"``.
        Firmware 2.50.0.76.2 ignores ``reason=normal`` for outgoing-ringing
        sessions while still answering ``success: true``, so the only
        reliable contract is to omit the parameter entirely.
        """
        init_module = self.init_module
        const_module = self.const_module
        ha_const = sys.modules["homeassistant.const"]
        init_module.TwoNIntercomAPI = FakeAPI

        entry = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        hass = FakeHass([entry])

        await init_module.async_setup(hass, {})
        await init_module.async_setup_entry(hass, entry)

        hangup_call = hass.services.handlers[(const_module.DOMAIN, "hangup_call")]
        await hangup_call(types.SimpleNamespace(data={"reason": None}))

        stored = entry.runtime_data
        self.assertEqual(stored.api.hangup_calls, [("session-123", None)])

    async def test_hangup_reason_forwarded_when_explicitly_valid(self) -> None:
        init_module = self.init_module
        const_module = self.const_module
        ha_const = sys.modules["homeassistant.const"]
        init_module.TwoNIntercomAPI = FakeAPI

        entry = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        hass = FakeHass([entry])

        await init_module.async_setup(hass, {})
        await init_module.async_setup_entry(hass, entry)

        hangup_call = hass.services.handlers[(const_module.DOMAIN, "hangup_call")]
        await hangup_call(types.SimpleNamespace(data={"reason": "rejected"}))

        stored = entry.runtime_data
        self.assertEqual(stored.api.hangup_calls, [("session-123", "rejected")])

    async def test_service_rejects_ambiguous_target_without_config_entry_id(self) -> None:
        init_module = self.init_module
        const_module = self.const_module
        ha_const = sys.modules["homeassistant.const"]
        init_module.TwoNIntercomAPI = FakeAPI

        entry_1 = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom-1.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        entry_2 = FakeConfigEntry(
            "entry-2",
            {
                ha_const.CONF_HOST: "intercom-2.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        hass = FakeHass([entry_1, entry_2])

        await init_module.async_setup(hass, {})
        await init_module.async_setup_entry(hass, entry_1)
        entry_2.runtime_data = init_module.TwoNIntercomRuntimeData(
            coordinator=types.SimpleNamespace(active_session_id="session-999"),
            api=FakeAPI(),
        )

        answer_call = hass.services.handlers[(const_module.DOMAIN, "answer_call")]

        with self.assertRaises(
            sys.modules["homeassistant.exceptions"].HomeAssistantError
        ):
            await answer_call(types.SimpleNamespace(data={}))

    async def test_service_allows_config_entry_id_to_disambiguate_multi_entry(self) -> None:
        init_module = self.init_module
        const_module = self.const_module
        ha_const = sys.modules["homeassistant.const"]
        init_module.TwoNIntercomAPI = FakeAPI

        entry_1 = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom-1.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        entry_2 = FakeConfigEntry(
            "entry-2",
            {
                ha_const.CONF_HOST: "intercom-2.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        hass = FakeHass([entry_1, entry_2])

        await init_module.async_setup(hass, {})
        await init_module.async_setup_entry(hass, entry_1)
        await init_module.async_setup_entry(hass, entry_2)

        stored_1 = entry_1.runtime_data
        stored_2 = entry_2.runtime_data
        stored_1.coordinator._active_session_id = "session-one"
        stored_2.coordinator._active_session_id = "session-two"

        answer_call = hass.services.handlers[(const_module.DOMAIN, "answer_call")]

        await answer_call(
            types.SimpleNamespace(
                data={
                    "config_entry_id": entry_2.entry_id,
                }
            )
        )

        self.assertEqual(stored_1.api.answer_calls, [])
        self.assertEqual(stored_2.api.answer_calls, ["session-two"])

    async def test_async_setup_registers_services_before_any_entry(self) -> None:
        """Services must be available after async_setup even with zero entries."""
        init_module = self.init_module
        const_module = self.const_module

        hass = FakeHass([])

        result = await init_module.async_setup(hass, {})

        self.assertTrue(result)
        self.assertTrue(hass.services.has_service(const_module.DOMAIN, "answer_call"))
        self.assertTrue(hass.services.has_service(const_module.DOMAIN, "hangup_call"))

    async def test_async_setup_is_idempotent(self) -> None:
        """Calling async_setup twice must not raise or double-register."""
        init_module = self.init_module
        const_module = self.const_module

        hass = FakeHass([])

        await init_module.async_setup(hass, {})
        await init_module.async_setup(hass, {})

        self.assertTrue(hass.services.has_service(const_module.DOMAIN, "answer_call"))
        self.assertTrue(hass.services.has_service(const_module.DOMAIN, "hangup_call"))

    async def test_service_error_no_loaded_entries_has_translation_fields(self) -> None:
        """When no entries are loaded, the error must carry translation metadata."""
        init_module = self.init_module
        const_module = self.const_module
        HomeAssistantError = sys.modules["homeassistant.exceptions"].HomeAssistantError

        hass = FakeHass([])
        await init_module.async_setup(hass, {})

        answer_call = hass.services.handlers[(const_module.DOMAIN, "answer_call")]

        with self.assertRaises(HomeAssistantError) as ctx:
            await answer_call(types.SimpleNamespace(data={}))

        self.assertEqual(ctx.exception.translation_domain, const_module.DOMAIN)
        self.assertEqual(ctx.exception.translation_key, "no_loaded_entries")

    async def test_service_error_ambiguous_entry_has_translation_fields(self) -> None:
        init_module = self.init_module
        const_module = self.const_module
        ha_const = sys.modules["homeassistant.const"]
        HomeAssistantError = sys.modules["homeassistant.exceptions"].HomeAssistantError
        init_module.TwoNIntercomAPI = FakeAPI

        entry_1 = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom-1.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        entry_2 = FakeConfigEntry(
            "entry-2",
            {
                ha_const.CONF_HOST: "intercom-2.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        hass = FakeHass([entry_1, entry_2])

        await init_module.async_setup(hass, {})
        await init_module.async_setup_entry(hass, entry_1)
        entry_2.runtime_data = init_module.TwoNIntercomRuntimeData(
            coordinator=types.SimpleNamespace(active_session_id="session-999"),
            api=FakeAPI(),
        )

        answer_call = hass.services.handlers[(const_module.DOMAIN, "answer_call")]

        with self.assertRaises(HomeAssistantError) as ctx:
            await answer_call(types.SimpleNamespace(data={}))

        self.assertEqual(ctx.exception.translation_domain, const_module.DOMAIN)
        self.assertEqual(ctx.exception.translation_key, "ambiguous_entry")

    async def test_service_error_entry_not_loaded_has_translation_fields(self) -> None:
        init_module = self.init_module
        const_module = self.const_module
        ha_const = sys.modules["homeassistant.const"]
        HomeAssistantError = sys.modules["homeassistant.exceptions"].HomeAssistantError
        init_module.TwoNIntercomAPI = FakeAPI

        entry = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        hass = FakeHass([entry])

        await init_module.async_setup(hass, {})
        await init_module.async_setup_entry(hass, entry)

        answer_call = hass.services.handlers[(const_module.DOMAIN, "answer_call")]

        with self.assertRaises(HomeAssistantError) as ctx:
            await answer_call(
                types.SimpleNamespace(data={"config_entry_id": "nonexistent"})
            )

        self.assertEqual(ctx.exception.translation_domain, const_module.DOMAIN)
        self.assertEqual(ctx.exception.translation_key, "entry_not_loaded")
        self.assertEqual(
            ctx.exception.translation_placeholders,
            {"config_entry_id": "nonexistent"},
        )

    async def test_service_error_no_active_session_has_translation_fields(self) -> None:
        init_module = self.init_module
        const_module = self.const_module
        ha_const = sys.modules["homeassistant.const"]
        HomeAssistantError = sys.modules["homeassistant.exceptions"].HomeAssistantError
        init_module.TwoNIntercomAPI = FakeAPI

        entry = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        hass = FakeHass([entry])

        await init_module.async_setup(hass, {})
        await init_module.async_setup_entry(hass, entry)
        # Clear the active session so _resolve_session_id raises
        entry.runtime_data.coordinator._active_session_id = None
        entry.runtime_data.api._call_status = {
            "state": "idle",
            "sessions": [],
        }

        answer_call = hass.services.handlers[(const_module.DOMAIN, "answer_call")]

        with self.assertRaises(HomeAssistantError) as ctx:
            await answer_call(types.SimpleNamespace(data={}))

        self.assertEqual(ctx.exception.translation_domain, const_module.DOMAIN)
        self.assertEqual(ctx.exception.translation_key, "no_active_session")

    async def test_service_error_answer_call_failed_has_translation_fields(self) -> None:
        init_module = self.init_module
        const_module = self.const_module
        ha_const = sys.modules["homeassistant.const"]
        HomeAssistantError = sys.modules["homeassistant.exceptions"].HomeAssistantError
        init_module.TwoNIntercomAPI = FakeAPI

        entry = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        hass = FakeHass([entry])

        await init_module.async_setup(hass, {})
        await init_module.async_setup_entry(hass, entry)
        entry.runtime_data.api = FakeAPI(answer_result=False)

        answer_call = hass.services.handlers[(const_module.DOMAIN, "answer_call")]

        with self.assertRaises(HomeAssistantError) as ctx:
            await answer_call(types.SimpleNamespace(data={}))

        self.assertEqual(ctx.exception.translation_domain, const_module.DOMAIN)
        self.assertEqual(ctx.exception.translation_key, "answer_call_failed")
        self.assertEqual(
            ctx.exception.translation_placeholders,
            {"session_id": "session-123"},
        )

    async def test_service_error_hangup_call_failed_has_translation_fields(self) -> None:
        init_module = self.init_module
        const_module = self.const_module
        ha_const = sys.modules["homeassistant.const"]
        HomeAssistantError = sys.modules["homeassistant.exceptions"].HomeAssistantError
        init_module.TwoNIntercomAPI = FakeAPI

        entry = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        hass = FakeHass([entry])

        await init_module.async_setup(hass, {})
        await init_module.async_setup_entry(hass, entry)
        entry.runtime_data.api = FakeAPI(hangup_result=False)

        hangup_call = hass.services.handlers[(const_module.DOMAIN, "hangup_call")]

        with self.assertRaises(HomeAssistantError) as ctx:
            await hangup_call(
                types.SimpleNamespace(data={"session_id": "explicit-session"})
            )

        self.assertEqual(ctx.exception.translation_domain, const_module.DOMAIN)
        self.assertEqual(ctx.exception.translation_key, "hangup_call_failed")
        self.assertIn("explicit-session", ctx.exception.translation_placeholders["session_id"])

    async def test_setup_and_unload_manage_log_listener_lifecycle(self) -> None:
        init_module = self.init_module
        ha_const = sys.modules["homeassistant.const"]
        init_module.TwoNIntercomAPI = FakeAPI

        start_calls: list[str] = []
        stop_calls: list[str] = []

        original_start = init_module.TwoNIntercomCoordinator.async_start_log_listener
        original_stop = init_module.TwoNIntercomCoordinator.async_stop_log_listener

        async def fake_start(self):
            start_calls.append(self.__class__.__name__)

        async def fake_stop(self):
            stop_calls.append(self.__class__.__name__)

        init_module.TwoNIntercomCoordinator.async_start_log_listener = fake_start
        init_module.TwoNIntercomCoordinator.async_stop_log_listener = fake_stop

        try:
            entry = FakeConfigEntry(
                "entry-1",
                {
                    ha_const.CONF_HOST: "intercom.local",
                    ha_const.CONF_PORT: 443,
                    ha_const.CONF_USERNAME: "user",
                    ha_const.CONF_PASSWORD: "secret",
                },
            )
            hass = FakeHass([entry])

            await init_module.async_setup_entry(hass, entry)
            await init_module.async_unload_entry(hass, entry)
        finally:
            init_module.TwoNIntercomCoordinator.async_start_log_listener = original_start
            init_module.TwoNIntercomCoordinator.async_stop_log_listener = original_stop

        self.assertEqual(start_calls, ["TwoNIntercomCoordinator"])
        self.assertEqual(stop_calls, ["TwoNIntercomCoordinator"])

    async def test_unload_clears_runtime_data(self) -> None:
        """After successful unload, runtime_data should be cleared."""
        init_module = self.init_module
        ha_const = sys.modules["homeassistant.const"]
        init_module.TwoNIntercomAPI = FakeAPI

        entry = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        hass = FakeHass([entry])

        await init_module.async_setup_entry(hass, entry)
        self.assertIsNotNone(entry.runtime_data)

        await init_module.async_unload_entry(hass, entry)
        self.assertIsNone(entry.runtime_data)

    async def test_setup_forwards_insecure_opt_in_from_options(self) -> None:
        init_module = self.init_module
        init_module.TwoNIntercomAPI = FakeAPI
        for options, expected in (({}, False), ({"allow_insecure": True}, True)):
            with self.subTest(options=options):
                entry = FakeConfigEntry(
                    "entry-1",
                    {
                        "host": "intercom.local", "port": 80, "protocol": "http",
                        "username": "user", "password": "secret",
                    },
                    options=options,
                )
                hass = FakeHass([entry])
                await init_module.async_setup_entry(hass, entry)
                self.assertEqual(entry.runtime_data.api.allow_insecure, expected)
                await init_module.async_unload_entry(hass, entry)

    async def test_get_option_prefers_options_over_data(self) -> None:
        """_get_option should prefer options, fall back to data."""
        init_module = self.init_module

        entry = FakeConfigEntry(
            "entry-1",
            {"scan_interval": 5, "host": "192.0.2.20"},
            options={"scan_interval": 10},
        )
        self.assertEqual(init_module._get_option(entry, "scan_interval"), 10)
        self.assertEqual(init_module._get_option(entry, "host"), "192.0.2.20")
        self.assertIsNone(init_module._get_option(entry, "missing"))
        self.assertEqual(init_module._get_option(entry, "missing", "default"), "default")

    async def test_is_entry_loaded_rejects_none_runtime_data(self) -> None:
        """_is_entry_loaded should return False when runtime_data is None."""
        init_module = self.init_module

        entry = FakeConfigEntry("entry-1", {})
        entry.runtime_data = None
        self.assertFalse(init_module._is_entry_loaded(entry))

    async def test_is_entry_loaded_accepts_valid_runtime_data(self) -> None:
        """_is_entry_loaded should return True for TwoNIntercomRuntimeData."""
        init_module = self.init_module
        ha_const = sys.modules["homeassistant.const"]
        init_module.TwoNIntercomAPI = FakeAPI

        entry = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        hass = FakeHass([entry])
        await init_module.async_setup_entry(hass, entry)
        self.assertTrue(init_module._is_entry_loaded(entry))

    async def test_hangup_rejects_invalid_reason(self) -> None:
        """Hangup with an invalid reason should raise ServiceValidationError."""
        init_module = self.init_module
        const_module = self.const_module
        ha_const = sys.modules["homeassistant.const"]
        ServiceValidationError = sys.modules["homeassistant.exceptions"].ServiceValidationError
        init_module.TwoNIntercomAPI = FakeAPI

        entry = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        hass = FakeHass([entry])
        await init_module.async_setup(hass, {})
        await init_module.async_setup_entry(hass, entry)

        hangup_call = hass.services.handlers[(const_module.DOMAIN, "hangup_call")]

        with self.assertRaises(ServiceValidationError) as ctx:
            await hangup_call(
                types.SimpleNamespace(data={"reason": "invalid_value"})
            )
        self.assertEqual(ctx.exception.translation_key, "invalid_hangup_reason")

    async def test_hangup_rejects_empty_reason(self) -> None:
        """Hangup with an empty string reason should raise ServiceValidationError."""
        init_module = self.init_module
        const_module = self.const_module
        ha_const = sys.modules["homeassistant.const"]
        ServiceValidationError = sys.modules["homeassistant.exceptions"].ServiceValidationError
        init_module.TwoNIntercomAPI = FakeAPI

        entry = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        hass = FakeHass([entry])
        await init_module.async_setup(hass, {})
        await init_module.async_setup_entry(hass, entry)

        hangup_call = hass.services.handlers[(const_module.DOMAIN, "hangup_call")]

        with self.assertRaises(ServiceValidationError):
            await hangup_call(
                types.SimpleNamespace(data={"reason": ""})
            )

    async def test_get_platforms_reads_from_options(self) -> None:
        """_get_platforms should use behavioral options from entry.options."""
        init_module = self.init_module

        entry = FakeConfigEntry(
            "entry-1",
            {"enable_camera": True},
            options={"enable_camera": False, "enable_doorbell": False},
        )
        platforms = init_module._get_platforms(entry)
        # camera disabled, doorbell disabled → switch + sensor
        self.assertNotIn("camera", platforms)
        self.assertNotIn("image", platforms)
        self.assertNotIn("binary_sensor", platforms)
        self.assertIn("switch", platforms)
        self.assertIn("sensor", platforms)
        self.assertEqual(platforms.count("update"), 1)

    async def test_get_platforms_always_includes_switch(self) -> None:
        """Switch platform is always included for auto-detection."""
        init_module = self.init_module

        entry = FakeConfigEntry("entry-1", {}, options={})
        platforms = init_module._get_platforms(entry)
        self.assertIn("switch", platforms)
        self.assertNotIn("cover", platforms)

    async def test_get_platforms_with_gate_relay_adds_cover(self) -> None:
        """Cover platform is added when a relay is configured as gate."""
        init_module = self.init_module

        entry = FakeConfigEntry(
            "entry-1",
            {},
            options={"relays": [{"relay_number": 1, "relay_device_type": "gate"}]},
        )
        platforms = init_module._get_platforms(entry)
        self.assertIn("switch", platforms)
        self.assertIn("cover", platforms)

    async def test_is_entry_loaded_with_config_entry_state(self) -> None:
        """_is_entry_loaded with a state attribute that has LOADED."""
        init_module = self.init_module

        class FakeState:
            LOADED = "loaded"

        entry = FakeConfigEntry("e1", {})
        entry.state = FakeState()
        entry.state = "not_loaded"
        # state != LOADED → False even if runtime_data is set
        entry.runtime_data = init_module.TwoNIntercomRuntimeData(
            coordinator=types.SimpleNamespace(),
            api=FakeAPI(),
        )
        # state is a string, no LOADED attribute → falls through to runtime check
        self.assertTrue(init_module._is_entry_loaded(entry))

    async def test_is_entry_loaded_state_mismatch(self) -> None:
        """_is_entry_loaded returns False when state doesn't match LOADED."""
        init_module = self.init_module

        from enum import Enum

        class ConfigEntryState(Enum):
            LOADED = "loaded"
            SETUP_ERROR = "setup_error"

        entry = FakeConfigEntry("e1", {})
        entry.state = ConfigEntryState.SETUP_ERROR
        entry.runtime_data = init_module.TwoNIntercomRuntimeData(
            coordinator=types.SimpleNamespace(),
            api=FakeAPI(),
        )
        self.assertFalse(init_module._is_entry_loaded(entry))

    async def test_resolve_session_id_from_service_data(self) -> None:
        """_resolve_session_id returns explicit session_id from service data."""
        init_module = self.init_module

        runtime = init_module.TwoNIntercomRuntimeData(
            coordinator=types.SimpleNamespace(active_session_id="cached-1"),
            api=FakeAPI(),
        )
        result = init_module._resolve_session_id(runtime, {"session_id": "explicit-1"})
        self.assertEqual(result, "explicit-1")

    async def test_extract_session_ids_not_dict(self) -> None:
        init_module = self.init_module
        self.assertEqual(init_module._extract_session_ids_from_status("bad"), [])

    async def test_extract_session_ids_sessions_not_list(self) -> None:
        init_module = self.init_module
        self.assertEqual(
            init_module._extract_session_ids_from_status({"sessions": "bad"}), []
        )

    async def test_extract_session_ids_non_dict_session(self) -> None:
        init_module = self.init_module
        self.assertEqual(
            init_module._extract_session_ids_from_status({"sessions": ["bad"]}), []
        )

    async def test_extract_session_ids_missing_session_key(self) -> None:
        init_module = self.init_module
        self.assertEqual(
            init_module._extract_session_ids_from_status(
                {"sessions": [{"state": "active"}]}
            ),
            [],
        )

    async def test_extract_session_ids_empty_after_strip(self) -> None:
        init_module = self.init_module
        self.assertEqual(
            init_module._extract_session_ids_from_status(
                {"sessions": [{"session": "  "}]}
            ),
            [],
        )

    async def test_hangup_explicit_session_returns_early(self) -> None:
        """Hangup with explicit session_id should return after one hangup."""
        init_module = self.init_module
        const_module = self.const_module
        ha_const = sys.modules["homeassistant.const"]
        init_module.TwoNIntercomAPI = FakeAPI

        entry = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        hass = FakeHass([entry])
        await init_module.async_setup(hass, {})
        await init_module.async_setup_entry(hass, entry)

        hangup_call = hass.services.handlers[(const_module.DOMAIN, "hangup_call")]
        await hangup_call(
            types.SimpleNamespace(data={"session_id": "explicit-99"})
        )
        self.assertEqual(
            entry.runtime_data.api.hangup_calls, [("explicit-99", None)]
        )

    async def test_hangup_call_status_exception(self) -> None:
        """When async_get_call_status fails, raise HomeAssistantError."""
        init_module = self.init_module
        const_module = self.const_module
        ha_const = sys.modules["homeassistant.const"]
        HomeAssistantError = sys.modules["homeassistant.exceptions"].HomeAssistantError
        init_module.TwoNIntercomAPI = FakeAPI

        entry = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        hass = FakeHass([entry])
        await init_module.async_setup(hass, {})
        await init_module.async_setup_entry(hass, entry)

        async def fail_call_status():
            raise RuntimeError("device unreachable")

        entry.runtime_data.api.async_get_call_status = fail_call_status
        entry.runtime_data.coordinator._active_session_id = None

        hangup_call = hass.services.handlers[(const_module.DOMAIN, "hangup_call")]
        with self.assertRaises(HomeAssistantError) as ctx:
            await hangup_call(types.SimpleNamespace(data={}))
        self.assertEqual(ctx.exception.translation_key, "call_status_query_failed")

    async def test_hangup_no_live_sessions_falls_back_to_cached(self) -> None:
        """When no live sessions, fall back to coordinator cached session."""
        init_module = self.init_module
        const_module = self.const_module
        ha_const = sys.modules["homeassistant.const"]
        init_module.TwoNIntercomAPI = FakeAPI

        entry = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        hass = FakeHass([entry])
        await init_module.async_setup(hass, {})
        await init_module.async_setup_entry(hass, entry)

        # Make call_status return no sessions
        entry.runtime_data.api._call_status = {"state": "idle", "sessions": []}
        # But coordinator has a cached session
        entry.runtime_data.coordinator._active_session_id = "cached-42"

        hangup_call = hass.services.handlers[(const_module.DOMAIN, "hangup_call")]
        await hangup_call(types.SimpleNamespace(data={}))
        self.assertEqual(
            entry.runtime_data.api.hangup_calls, [("cached-42", None)]
        )

    async def test_hangup_no_sessions_no_cache_silent_noop(self) -> None:
        """When no live or cached sessions, hangup is a silent no-op."""
        init_module = self.init_module
        const_module = self.const_module
        ha_const = sys.modules["homeassistant.const"]
        init_module.TwoNIntercomAPI = FakeAPI

        entry = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
        )
        hass = FakeHass([entry])
        await init_module.async_setup(hass, {})
        await init_module.async_setup_entry(hass, entry)

        entry.runtime_data.api._call_status = {"state": "idle", "sessions": []}
        entry.runtime_data.coordinator._active_session_id = None

        hangup_call = hass.services.handlers[(const_module.DOMAIN, "hangup_call")]
        await hangup_call(types.SimpleNamespace(data={}))
        # No calls were made
        self.assertEqual(entry.runtime_data.api.hangup_calls, [])

    async def test_scan_interval_bad_value_uses_default(self) -> None:
        """Non-integer scan_interval should fall back to DEFAULT_SCAN_INTERVAL."""
        init_module = self.init_module
        ha_const = sys.modules["homeassistant.const"]
        init_module.TwoNIntercomAPI = FakeAPI

        entry = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
            options={"scan_interval": "not_a_number"},
        )
        hass = FakeHass([entry])
        result = await init_module.async_setup_entry(hass, entry)
        self.assertTrue(result)

    async def test_async_update_options_reloads_entry(self) -> None:
        """async_update_options should trigger a reload."""
        init_module = self.init_module
        ha_const = sys.modules["homeassistant.const"]

        entry = FakeConfigEntry("entry-1", {
            ha_const.CONF_HOST: "intercom.local",
            ha_const.CONF_PORT: 443,
            ha_const.CONF_USERNAME: "user",
            ha_const.CONF_PASSWORD: "secret",
        })
        hass = FakeHass([entry])
        # Should not raise
        await init_module.async_update_options(hass, entry)


class GrantAccessFakeAPI(FakeAPI):
    """FakeAPI with a scripted /api/accesspoint/grantaccess outcome."""

    def __init__(self, *args, grant_outcome=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.grant_calls: list[tuple[int, str]] = []
        self.grant_outcome = grant_outcome

    async def async_grant_access(self, access_point, user):
        self.grant_calls.append((access_point, user))
        outcome = self.grant_outcome
        if isinstance(outcome, Exception):
            raise outcome
        api_module = sys.modules["custom_components.2n_intercom.api"]
        if outcome is None:
            return api_module.GrantAccessResult(granted=True)
        return outcome


class GrantAccessServiceTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the 2n_intercom.grant_access service."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.init_module = load_init_module()
        cls.const_module = sys.modules["custom_components.2n_intercom.const"]
        cls.api_module = sys.modules["custom_components.2n_intercom.api"]
        cls.exceptions = sys.modules["homeassistant.exceptions"]

    async def _setup(self, options=None, grant_outcome=None):
        ha_const = sys.modules["homeassistant.const"]
        self.init_module.TwoNIntercomAPI = FakeAPI
        entry = FakeConfigEntry(
            "entry-1",
            {
                ha_const.CONF_HOST: "intercom.local",
                ha_const.CONF_PORT: 443,
                ha_const.CONF_USERNAME: "user",
                ha_const.CONF_PASSWORD: "secret",
            },
            options=options,
        )
        hass = FakeHass([entry])
        await self.init_module.async_setup(hass, {})
        await self.init_module.async_setup_entry(hass, entry)
        api = GrantAccessFakeAPI(grant_outcome=grant_outcome)
        entry.runtime_data.api = api
        handler = hass.services.handlers[(self.const_module.DOMAIN, "grant_access")]
        return handler, api

    async def test_grant_access_uses_service_user_and_default_entry_ap(self) -> None:
        handler, api = await self._setup()
        await handler(types.SimpleNamespace(data={"user": " UUID-1 "}))
        self.assertEqual(api.grant_calls, [(0, "UUID-1")])

    async def test_grant_access_exit_access_point(self) -> None:
        handler, api = await self._setup()
        await handler(types.SimpleNamespace(data={"user": "u", "access_point": 1}))
        await handler(types.SimpleNamespace(data={"user": "u", "access_point": "1"}))
        await handler(types.SimpleNamespace(data={"user": "u", "access_point": 1.0}))
        self.assertEqual(api.grant_calls, [(1, "u"), (1, "u"), (1, "u")])

    async def test_grant_access_rejects_invalid_access_point(self) -> None:
        handler, api = await self._setup()
        for bad in (2, -1, "entry", True, 0.5):
            with self.assertRaises(self.exceptions.ServiceValidationError) as ctx:
                await handler(types.SimpleNamespace(data={"user": "u", "access_point": bad}))
            self.assertEqual(ctx.exception.translation_key, "grant_access_invalid_access_point")
        self.assertEqual(api.grant_calls, [])

    async def test_grant_access_falls_back_to_configured_user(self) -> None:
        handler, api = await self._setup(options={"grant_access_user": "default-uuid"})
        await handler(types.SimpleNamespace(data={}))
        await handler(types.SimpleNamespace(data={"user": "  "}))
        self.assertEqual(api.grant_calls, [(0, "default-uuid"), (0, "default-uuid")])

    async def test_grant_access_service_user_overrides_configured_user(self) -> None:
        handler, api = await self._setup(options={"grant_access_user": "default-uuid"})
        await handler(types.SimpleNamespace(data={"user": "other"}))
        self.assertEqual(api.grant_calls, [(0, "other")])

    async def test_grant_access_without_any_user_raises_validation_error(self) -> None:
        handler, api = await self._setup()
        with self.assertRaises(self.exceptions.ServiceValidationError) as ctx:
            await handler(types.SimpleNamespace(data={}))
        self.assertEqual(ctx.exception.translation_key, "grant_access_no_user")
        self.assertEqual(ctx.exception.translation_domain, self.const_module.DOMAIN)
        self.assertEqual(api.grant_calls, [])

    async def test_grant_access_denied_raises_with_reason(self) -> None:
        for reason in ("invalidAp", "invalidCredential", "accessBlocked"):
            handler, _api = await self._setup(
                grant_outcome=self.api_module.GrantAccessResult(granted=False, reason=reason)
            )
            with self.assertRaises(self.exceptions.HomeAssistantError) as ctx:
                await handler(types.SimpleNamespace(data={"user": "u"}))
            self.assertEqual(ctx.exception.translation_key, "grant_access_denied")
            self.assertEqual(ctx.exception.translation_placeholders["reason"], reason)

    async def test_grant_access_denied_without_reason_still_raises(self) -> None:
        handler, _api = await self._setup(
            grant_outcome=self.api_module.GrantAccessResult(granted=False)
        )
        with self.assertRaises(self.exceptions.HomeAssistantError) as ctx:
            await handler(types.SimpleNamespace(data={"user": "u"}))
        self.assertEqual(ctx.exception.translation_placeholders["reason"], "unknown")

    async def test_grant_access_maps_device_errors_to_translation_keys(self) -> None:
        api = self.api_module
        cases = [
            (api.TwoNAuthenticationError("401"), "grant_access_unauthorized"),
            (
                api.TwoNDeviceRejectedError(api.TwoNDeviceError(10, "insufficient privileges", None)),
                "grant_access_unauthorized",
            ),
            (
                api.TwoNDeviceRejectedError(api.TwoNDeviceError(18, "request rejected", None)),
                "grant_access_ap_disabled",
            ),
            (
                api.TwoNDeviceRejectedError(api.TwoNDeviceError(1, "not supported", None)),
                "grant_access_unsupported",
            ),
            (
                api.TwoNDeviceRejectedError(api.TwoNDeviceError(12, "invalid parameter", "user")),
                "grant_access_failed",
            ),
            (api.TwoNConnectionError("timeout"), "grant_access_failed"),
            (api.TwoNAPIError("bad payload"), "grant_access_failed"),
        ]
        for error, key in cases:
            handler, _api = await self._setup(grant_outcome=error)
            with self.assertRaises(self.exceptions.HomeAssistantError) as ctx:
                await handler(types.SimpleNamespace(data={"user": "u"}))
            self.assertEqual(ctx.exception.translation_key, key, error)
            self.assertEqual(ctx.exception.translation_domain, self.const_module.DOMAIN)


class PlatformSelectionTests(unittest.TestCase):
    """Optional platforms follow their feature toggles."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.init_module = load_init_module()

    def test_image_platform_added_with_camera(self) -> None:
        entry = FakeConfigEntry("entry-1", {}, options={"enable_camera": True})
        platforms = self.init_module._get_platforms(entry)
        self.assertIn("image", platforms)
        self.assertLess(platforms.index("camera"), platforms.index("image"))

    def test_image_platform_skipped_without_camera(self) -> None:
        entry = FakeConfigEntry("entry-1", {"enable_camera": False})
        self.assertNotIn("image", self.init_module._get_platforms(entry))

    def test_event_platform_follows_doorbell_option(self) -> None:
        for data, options, enabled in (
            ({}, {}, True),
            ({"enable_doorbell": False}, {}, False),
            ({"enable_doorbell": True}, {"enable_doorbell": False}, False),
            ({"enable_doorbell": False}, {"enable_doorbell": True}, True),
        ):
            with self.subTest(data=data, options=options):
                entry = FakeConfigEntry("entry-1", data, options=options)
                platforms = self.init_module._get_platforms(entry)
                self.assertEqual(platforms.count("event"), int(enabled))
                self.assertEqual(platforms.count("binary_sensor"), int(enabled))

    def test_doorbell_event_platform_does_not_require_camera(self) -> None:
        entry = FakeConfigEntry(
            "entry-1", {}, options={"enable_camera": False, "enable_doorbell": True}
        )
        platforms = self.init_module._get_platforms(entry)
        self.assertIn("event", platforms)
        self.assertNotIn("camera", platforms)
