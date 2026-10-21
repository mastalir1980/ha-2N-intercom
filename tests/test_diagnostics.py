"""Unit tests for diagnostics output."""

from __future__ import annotations

import sys
import types
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone

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

DIAGNOSTICS_PATH = (
    __import__("pathlib").Path(__file__).resolve().parents[1]
    / "custom_components"
    / "2n_intercom"
    / "diagnostics.py"
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
        pass

    class ConfigEntryNotReady(Exception):
        pass

    exceptions.HomeAssistantError = HomeAssistantError
    exceptions.ConfigEntryNotReady = ConfigEntryNotReady
    sys.modules["homeassistant.exceptions"] = exceptions

    config_entries = types.ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntry = object
    sys.modules["homeassistant.config_entries"] = config_entries

    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class DataUpdateCoordinator:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, hass, logger, name, update_interval) -> None:
            self.hass = hass
            self.data = None
            self.last_update_success = True
            self.update_interval = update_interval

        async def async_config_entry_first_refresh(self):
            self.data = await self._async_update_data()
            return self.data

    class UpdateFailed(Exception):
        pass

    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.UpdateFailed = UpdateFailed
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator
    ensure_package("homeassistant.helpers")

    # Stub the diagnostics module with async_redact_data
    diagnostics_module = types.ModuleType("homeassistant.components.diagnostics")

    def async_redact_data(data, to_redact):
        """Recursively redact dictionaries and lists, like the HA helper."""
        if isinstance(data, dict):
            return {
                k: (
                    "**REDACTED**" if k in to_redact and v is not None and v != ""
                    else async_redact_data(v, to_redact)
                )
                for k, v in data.items()
            }
        if isinstance(data, list):
            return [async_redact_data(value, to_redact) for value in data]
        return data

    diagnostics_module.REDACTED = "**REDACTED**"
    diagnostics_module.async_redact_data = async_redact_data
    sys.modules["homeassistant.components.diagnostics"] = diagnostics_module
    ensure_package("homeassistant.components")

    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    aiohttp_client.async_create_clientsession = lambda hass, **kwargs: None
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client

    helpers_typing = types.ModuleType("homeassistant.helpers.typing")
    helpers_typing.ConfigType = dict
    sys.modules["homeassistant.helpers.typing"] = helpers_typing


def load_diagnostics_module():
    install_api_stubs()
    install_dt_util_stub()
    _install_homeassistant_stubs()
    ensure_package("custom_components")
    ensure_package("custom_components.2n_intercom")
    load_module("custom_components.2n_intercom.const", CONST_PATH)
    load_module("custom_components.2n_intercom.api", API_PATH)
    load_module("custom_components.2n_intercom.coordinator", COORDINATOR_PATH)
    return load_module("custom_components.2n_intercom.diagnostics", DIAGNOSTICS_PATH)


class FakeCoordinator:
    def __init__(self) -> None:
        self.last_update_success = True
        self.update_interval = timedelta(seconds=5)
        self.system_info = {
            "variant": "2N IP Intercom",
            "serialNumber": "SN-TEST-123456",
            "macAddr": "00:11:22:AA:BB:CC",
            "swVersion": "3.1.0",
            "hwVersion": "test-hw",
            "firmwarePackage": "hip-test",
            "buildType": "release",
            "deviceName": "2N IP Intercom",
        }
        self.phone_status = {
            "accounts": [
                {
                    "account": 1,
                    "accountType": "general",
                    "enabled": True,
                    "sipNumber": "sip:test-account@example.invalid",
                    "registrationEnabled": True,
                    "registered": True,
                    "registerTime": 1721138562,
                },
                {
                    "account": 2,
                    "accountType": "general",
                    "enabled": False,
                    "sipNumber": "",
                    "registrationEnabled": False,
                    "registered": False,
                },
                {
                    "account": 3,
                    "accountType": "local",
                    "enabled": True,
                    "sipNumber": "2NIPIntercom-SN-TEST-123456",
                },
            ],
        }
        self.switch_caps = {}
        self.switch_status = {}
        self.io_caps = {}
        self.io_status = {}
        self.active_session_id = "session-abc"
        self.call_state = "ringing"
        self.ring_active = True
        self.called_peer = "sip:test-peer@example.invalid"
        self.caller_info = {"name": "Test Caller", "number": "test-caller-number"}
        self.system_caps = {"motionDetection": "inactive,licensed"}
        self.motion_detection_available = False
        self.motion_detected = False
        self.last_motion_time = None
        self.log_caps = None
        self.subscribed_log_events = ()
        self.last_access_event = None
        self.ring_snapshot = None
        self.ring_snapshot_time = None

    @property
    def camera_transport_info(self):
        api_module = sys.modules["custom_components.2n_intercom.api"]
        return api_module.CameraTransportInfo(
            resolved=True,
            selected_mode="mjpeg",
        )


class FakeConfigEntry:
    def __init__(self) -> None:
        self.title = "Front Door Intercom"
        self.data = {
            "host": "192.0.2.20",
            "port": 443,
            "username": "admin",
            "password": "super-secret",
            "serial_number": "SN-TEST-123456",
        }
        self.options = {"scan_interval": 5}
        self.runtime_data = None


class DiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    """Tests for diagnostics output shape and credential redaction."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.diag_module = load_diagnostics_module()

    async def test_diagnostics_returns_expected_top_level_keys(self) -> None:
        diag_module = self.diag_module
        coordinator_module = sys.modules["custom_components.2n_intercom.coordinator"]

        coordinator = FakeCoordinator()
        entry = FakeConfigEntry()
        entry.runtime_data = coordinator_module.TwoNIntercomRuntimeData(
            coordinator=coordinator,
            api=types.SimpleNamespace(),
            loaded_platforms=["camera", "binary_sensor", "lock", "sensor"],
        )

        result = await diag_module.async_get_config_entry_diagnostics(None, entry)

        self.assertIn("entry", result)
        self.assertIn("coordinator", result)
        self.assertIn("device", result)
        self.assertIn("call_state", result)
        self.assertIn("camera_transport", result)

    async def test_diagnostics_redacts_credentials(self) -> None:
        diag_module = self.diag_module
        coordinator_module = sys.modules["custom_components.2n_intercom.coordinator"]

        coordinator = FakeCoordinator()
        entry = FakeConfigEntry()
        entry.runtime_data = coordinator_module.TwoNIntercomRuntimeData(
            coordinator=coordinator,
            api=types.SimpleNamespace(),
            loaded_platforms=["camera"],
        )

        result = await diag_module.async_get_config_entry_diagnostics(None, entry)

        entry_data = result["entry"]["data"]
        self.assertEqual(entry_data["username"], "**REDACTED**")
        self.assertEqual(entry_data["password"], "**REDACTED**")
        # Host and port must NOT be redacted
        self.assertEqual(entry_data["host"], "192.0.2.20")
        self.assertEqual(entry_data["port"], 443)

    async def test_diagnostics_redacts_entry_mac_address(self) -> None:
        coordinator_module = sys.modules["custom_components.2n_intercom.coordinator"]
        entry = FakeConfigEntry()
        entry.data["mac_address"] = "001122AABBCC"
        entry.runtime_data = coordinator_module.TwoNIntercomRuntimeData(
            coordinator=FakeCoordinator(),
            api=types.SimpleNamespace(),
            loaded_platforms=["camera"],
        )

        result = await self.diag_module.async_get_config_entry_diagnostics(None, entry)

        self.assertEqual(result["entry"]["data"]["mac_address"], "**REDACTED**")
        self.assertNotIn("001122AABBCC", repr(result))
        self.assertEqual(entry.data["mac_address"], "001122AABBCC")

    async def test_diagnostics_redacts_serial_in_entry_and_free_text(self) -> None:
        coordinator_module = sys.modules["custom_components.2n_intercom.coordinator"]
        for serial_source in ("entry", "system_info", "both", "neither"):
            with self.subTest(serial_source=serial_source):
                coordinator = FakeCoordinator()
                entry = FakeConfigEntry()
                serial = entry.data["serial_number"]
                entry.title = f"2N IP Intercom {serial} (v1.5.0)"
                entry.data["name"] = entry.title
                entry.options["name"] = entry.title
                if serial_source in {"system_info", "neither"}:
                    entry.data.pop("serial_number")
                if serial_source in {"entry", "neither"}:
                    coordinator.system_info.pop("serialNumber")
                if serial_source == "neither":
                    entry.title = "Front Door Intercom"
                    entry.data["name"] = entry.title
                    entry.options["name"] = entry.title
                    coordinator.phone_status = {}
                else:
                    coordinator.system_info["deviceName"] = entry.title
                original_data = deepcopy(entry.data)
                entry.runtime_data = coordinator_module.TwoNIntercomRuntimeData(
                    coordinator=coordinator, api=types.SimpleNamespace(),
                )

                result = await self.diag_module.async_get_config_entry_diagnostics(None, entry)

                expected_title = (
                    "Front Door Intercom" if serial_source == "neither"
                    else "2N IP Intercom **REDACTED** (v1.5.0)"
                )
                self.assertEqual(result["entry"]["title"], expected_title)
                self.assertEqual(result["entry"]["data"]["name"], expected_title)
                self.assertEqual(result["entry"]["options"]["name"], expected_title)
                self.assertNotIn(serial, repr(result))
                if "serial_number" in entry.data:
                    self.assertEqual(result["entry"]["data"]["serial_number"], "**REDACTED**")
                self.assertEqual(entry.data, original_data)

    async def test_diagnostics_redacts_system_identifiers_without_mutating_cache(self) -> None:
        coordinator_module = sys.modules["custom_components.2n_intercom.coordinator"]
        coordinator = FakeCoordinator()
        coordinator.system_info["deviceName"] = "2N SN-TEST-123456 00:11:22:aa:bb:cc"
        entry = FakeConfigEntry()
        entry.options["nested"] = [{
            "serialNumber": "SN-NESTED",
            "macAddr": "00:11:22:33:44:55",
            "serial_number": "SN-OPTION",
            "mac_address": "001122334455",
            "name": "SN-TEST-123456 00:11:22:aa:bb:cc",
        }]
        original_system_info = deepcopy(coordinator.system_info)
        original_options = deepcopy(entry.options)
        entry.runtime_data = coordinator_module.TwoNIntercomRuntimeData(
            coordinator=coordinator, api=types.SimpleNamespace(),
        )

        result = await self.diag_module.async_get_config_entry_diagnostics(None, entry)

        info = result["device"]["system_info"]
        for key in ("serialNumber", "macAddr"):
            self.assertEqual(info[key], "**REDACTED**")
            self.assertNotIn(original_system_info[key], repr(result))
        for key in ("variant", "swVersion", "hwVersion", "firmwarePackage", "buildType"):
            self.assertEqual(info[key], original_system_info[key])
        self.assertEqual(info["deviceName"], "2N **REDACTED** **REDACTED**")
        nested = result["entry"]["options"]["nested"][0]
        for key in ("serialNumber", "macAddr", "serial_number", "mac_address"):
            self.assertEqual(nested[key], "**REDACTED**")
        self.assertEqual(nested["name"], "**REDACTED** **REDACTED**")
        self.assertEqual(result["device"]["system_caps"], coordinator.system_caps)
        self.assertEqual(coordinator.system_info, original_system_info)
        self.assertEqual(entry.options, original_options)

    async def test_diagnostics_redacts_phone_identities_preserving_registration(self) -> None:
        coordinator_module = sys.modules["custom_components.2n_intercom.coordinator"]
        coordinator = FakeCoordinator()
        account = coordinator.phone_status["accounts"][0]
        account.update({
            "username": "test-sip-user",
            "accountName": "Test Account",
            "registrar": {
                "address": "registrar.example.invalid",
                "identity": "test-registrar-identity",
                "state": "registered",
            },
            "additionalIdentities": ["test-alias", {"uri": "sip:alias@example.invalid"}],
        })
        coordinator.phone_status["accounts"][1]["state"] = "unregistered"
        original_status = deepcopy(coordinator.phone_status)
        entry = FakeConfigEntry()
        entry.runtime_data = coordinator_module.TwoNIntercomRuntimeData(
            coordinator=coordinator, api=types.SimpleNamespace(),
        )

        result = await self.diag_module.async_get_config_entry_diagnostics(None, entry)

        accounts = result["device"]["phone_status"]["accounts"]
        for redacted, original in zip(accounts, original_status["accounts"], strict=True):
            self.assertEqual(redacted["sipNumber"], "**REDACTED**")
            for key in (
                "account", "accountType", "enabled", "registrationEnabled",
                "registered", "registerTime", "state",
            ):
                if key in original:
                    self.assertEqual(redacted[key], original[key])
        first = accounts[0]
        self.assertEqual(first["username"], "**REDACTED**")
        self.assertEqual(first["accountName"], "**REDACTED**")
        self.assertEqual(first["registrar"], {
            "address": "**REDACTED**",
            "identity": "**REDACTED**",
            "state": "registered",
        })
        self.assertEqual(first["additionalIdentities"], [
            "**REDACTED**", {"uri": "**REDACTED**"},
        ])
        self.assertEqual(coordinator.phone_status, original_status)

    async def test_diagnostics_redacts_textual_account_and_registrar_identities(self) -> None:
        coordinator_module = sys.modules["custom_components.2n_intercom.coordinator"]
        coordinator = FakeCoordinator()
        coordinator.phone_status = {"accounts": [{
            "account": "account-identity",
            "sipAccount": 2,
            "registrar": "sip:registrar@example.invalid",
            "registrationState": "registered",
        }]}
        entry = FakeConfigEntry()
        entry.runtime_data = coordinator_module.TwoNIntercomRuntimeData(
            coordinator=coordinator, api=types.SimpleNamespace(),
        )

        result = await self.diag_module.async_get_config_entry_diagnostics(None, entry)

        self.assertEqual(result["device"]["phone_status"], {"accounts": [{
            "account": "**REDACTED**",
            "sipAccount": 2,
            "registrar": "**REDACTED**",
            "registrationState": "registered",
        }]})

    async def test_diagnostics_redacts_call_peers_and_omits_caller_details(self) -> None:
        coordinator_module = sys.modules["custom_components.2n_intercom.coordinator"]
        coordinator = FakeCoordinator()
        entry = FakeConfigEntry()
        entry.options["called_id"] = coordinator.called_peer
        entry.runtime_data = coordinator_module.TwoNIntercomRuntimeData(
            coordinator=coordinator, api=types.SimpleNamespace(),
        )

        result = await self.diag_module.async_get_config_entry_diagnostics(None, entry)

        self.assertEqual(result["call_state"]["called_peer"], "**REDACTED**")
        self.assertEqual(result["entry"]["options"]["called_id"], "**REDACTED**")
        self.assertNotIn(coordinator.called_peer, repr(result))
        self.assertNotIn("caller_info", result["call_state"])
        self.assertNotIn("caller", result["call_state"])
        for value in coordinator.caller_info.values():
            self.assertNotIn(value, repr(result))

    async def test_diagnostics_keeps_empty_state_and_custom_title(self) -> None:
        coordinator_module = sys.modules["custom_components.2n_intercom.coordinator"]
        for phone_status in ({}, {"accounts": []}):
            with self.subTest(phone_status=phone_status):
                coordinator = FakeCoordinator()
                coordinator.phone_status = phone_status
                coordinator.called_peer = None
                coordinator.caller_info = {}
                entry = FakeConfigEntry()
                entry.runtime_data = coordinator_module.TwoNIntercomRuntimeData(
                    coordinator=coordinator, api=types.SimpleNamespace(),
                )

                result = await self.diag_module.async_get_config_entry_diagnostics(None, entry)

                self.assertEqual(result["entry"]["title"], "Front Door Intercom")
                self.assertIsNone(result["call_state"]["called_peer"])
                self.assertEqual(result["device"]["phone_status"], phone_status)

    async def test_diagnostics_includes_device_state(self) -> None:
        diag_module = self.diag_module
        coordinator_module = sys.modules["custom_components.2n_intercom.coordinator"]

        coordinator = FakeCoordinator()
        entry = FakeConfigEntry()
        entry.runtime_data = coordinator_module.TwoNIntercomRuntimeData(
            coordinator=coordinator,
            api=types.SimpleNamespace(),
            loaded_platforms=["camera"],
        )

        result = await diag_module.async_get_config_entry_diagnostics(None, entry)

        self.assertEqual(result["device"]["system_info"]["variant"], "2N IP Intercom")
        self.assertEqual(result["call_state"]["active_session_id"], "session-abc")
        self.assertEqual(result["call_state"]["call_state"], "ringing")
        self.assertTrue(result["call_state"]["ring_active"])

    async def test_firmware_diagnostics_only_versions_and_selected_channel(self) -> None:
        coordinator_module = sys.modules["custom_components.2n_intercom.coordinator"]
        coordinator = FakeCoordinator()
        coordinator.system_info["swVersion"] = "3.1.0"
        entry = FakeConfigEntry()
        entry.runtime_data = coordinator_module.TwoNIntercomRuntimeData(
            coordinator=coordinator, api=types.SimpleNamespace(),
            firmware_latest_version="3.10.0",
        )
        for options, channel in (
            ({}, "active_track"), ({"firmware_channel": "lts"}, "lts"),
            ({"firmware_channel": "beta"}, "beta"),
        ):
            with self.subTest(channel=channel):
                entry.options = options
                result = await self.diag_module.async_get_config_entry_diagnostics(None, entry)
                self.assertEqual(result["firmware"], {
                    "installed_version": "3.1.0",
                    "latest_version": "3.10.0",
                    "channel": channel,
                })
                self.assertNotIn("http", repr(result["firmware"]))
                self.assertNotIn("super-secret", repr(result))

    async def test_diagnostics_includes_coordinator_metadata(self) -> None:
        diag_module = self.diag_module
        coordinator_module = sys.modules["custom_components.2n_intercom.coordinator"]

        coordinator = FakeCoordinator()
        entry = FakeConfigEntry()
        entry.runtime_data = coordinator_module.TwoNIntercomRuntimeData(
            coordinator=coordinator,
            api=types.SimpleNamespace(),
            loaded_platforms=["camera", "binary_sensor", "lock", "sensor"],
        )

        result = await diag_module.async_get_config_entry_diagnostics(None, entry)

        self.assertTrue(result["coordinator"]["last_update_success"])
        self.assertEqual(result["coordinator"]["update_interval"], 5.0)
        self.assertEqual(
            result["coordinator"]["loaded_platforms"],
            ["camera", "binary_sensor", "lock", "sensor"],
        )

    async def test_diagnostics_includes_access_control_without_identities(self) -> None:
        diag_module = self.diag_module
        coordinator_module = sys.modules["custom_components.2n_intercom.coordinator"]

        coordinator = FakeCoordinator()
        coordinator.log_caps = frozenset({"CardEntered", "CallStateChanged"})
        coordinator.subscribed_log_events = ("CallStateChanged", "CardEntered")
        coordinator.last_access_event = coordinator_module.AccessEvent(
            event_type="CardEntered",
            timestamp=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            credential_type="card",
            access_point=0,
            granted=True,
            user_uuid="abc",
            user_name="Alice",
        )
        coordinator.ring_snapshot = b"jpeg"
        coordinator.ring_snapshot_time = datetime(2026, 1, 2, tzinfo=timezone.utc)
        entry = FakeConfigEntry()
        entry.options = {"grant_access_user": "abc"}
        entry.runtime_data = coordinator_module.TwoNIntercomRuntimeData(
            coordinator=coordinator,
            api=types.SimpleNamespace(),
            loaded_platforms=["camera"],
        )

        result = await diag_module.async_get_config_entry_diagnostics(None, entry)

        access = result["access_control"]
        self.assertEqual(access["log_caps_events"], ["CallStateChanged", "CardEntered"])
        self.assertEqual(access["subscribed_events"], ["CallStateChanged", "CardEntered"])
        event = access["last_access_event"]
        self.assertEqual(event["event_type"], "CardEntered")
        self.assertTrue(event["granted"])
        self.assertEqual(event["timestamp"], "2026-01-02T03:04:05+00:00")
        self.assertEqual(event["user_uuid"], "**REDACTED**")
        self.assertEqual(event["user_name"], "**REDACTED**")
        self.assertEqual(result["entry"]["options"]["grant_access_user"], "**REDACTED**")
        self.assertTrue(result["ring_snapshot"]["captured"])
        self.assertNotIn("jpeg", str(result["ring_snapshot"]))


if __name__ == "__main__":
    unittest.main()
