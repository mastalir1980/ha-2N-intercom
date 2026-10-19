"""Offline firmware catalog, entity lifecycle and read-only contract tests."""
from __future__ import annotations

import ast
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import re
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch, sentinel
from urllib.parse import urlsplit

from _stubs import (
    ENTITY_PATH,
    FIRMWARE_PATH,
    INTEGRATION_DIR,
    REPO_ROOT,
    UPDATE_PATH,
    ensure_package,
    install_update_stubs,
    load_module,
)
from test_coordinator import load_coordinator_module


def load_update_module():
    coordinator_module = load_coordinator_module()
    install_update_stubs()

    class CoordinatorEntity:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, coordinator):
            self.coordinator = coordinator
            self.hass = coordinator.hass
            self.state_writes = 0
            self.remove_callbacks = []

        @property
        def should_poll(self):
            return False

        @property
        def available(self):
            return self.coordinator.last_update_success

        async def async_added_to_hass(self):
            self.added = True

        def async_on_remove(self, callback):
            self.remove_callbacks.append(callback)

        def async_write_ha_state(self):
            self.state_writes += 1

        def _handle_coordinator_update(self):
            self.async_write_ha_state()

    sys.modules["homeassistant.helpers.update_coordinator"].CoordinatorEntity = CoordinatorEntity
    ensure_package("homeassistant.const").EntityCategory = types.SimpleNamespace(CONFIG="config")
    platform = types.ModuleType("homeassistant.helpers.entity_platform")
    platform.AddEntitiesCallback = object
    sys.modules[platform.__name__] = platform
    client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    client.async_get_clientsession = lambda hass: hass.shared_session
    sys.modules[client.__name__] = client
    event = types.ModuleType("homeassistant.helpers.event")
    event.async_track_time_interval = Mock(return_value=Mock())
    sys.modules[event.__name__] = event
    load_module("custom_components.2n_intercom.entity", ENTITY_PATH)
    firmware = load_module("custom_components.2n_intercom.firmware", FIRMWARE_PATH)
    update = load_module("custom_components.2n_intercom.update", UPDATE_PATH)
    return update, firmware, coordinator_module


def release_payload():
    return {
        "version": "3.10.0",
        "type": {"stable": True, "lts": False},
        "changelog.md": [
            {"version": "3.2.0", "text": "## Older release\nOlder changes"},
            {"version": "3.10.0", "text": "## Newest release\n" + "Changes " * 60},
        ],
        "files": [{"url": "https://example.invalid/download?token=private-token"}],
    }


class Response:
    def __init__(self, status=200, payload=None):
        self.status = status
        self.json = AsyncMock(return_value=payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FirmwareCatalogTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.update, cls.firmware, cls.coordinators = load_update_module()

    def setUp(self):
        self.payload = release_payload()
        self.response = Response(payload=self.payload)
        self.session = types.SimpleNamespace(get=Mock(return_value=self.response))

    async def _check(self, track="newest", package="test-package"):
        return await self.firmware.check(self.session, package, track, "3.1.0")

    async def test_public_get_has_only_catalog_parameters_and_no_credentials(self):
        result = await self._check()
        self.session.get.assert_called_once_with(
            "https://update.2n.cz/hip/test-package/newest/",
            params={"current_ver": "3.1.0", "ui_lang": "en"},
            allow_redirects=False,
        )
        self.assertEqual(result.version, "3.10.0")
        self.assertNotIn("private-token", repr(result))
        self.assertNotIn("files", vars(result))

    async def test_package_is_a_single_encoded_path_segment(self):
        await self._check(package="test/package?#")
        self.assertEqual(
            self.session.get.call_args.args[0],
            "https://update.2n.cz/hip/test%2Fpackage%3F%23/newest/",
        )

    async def test_204_does_not_try_to_decode_json(self):
        self.response.status = 204
        self.assertIsNone(await self._check())
        self.response.json.assert_not_awaited()

    async def test_track_matching_requires_exact_boolean_flags(self):
        for track, flags, matches in (
            ("newest", {"stable": True}, True),
            ("newest", {"stable": False}, False),
            ("lts", {"lts": True}, True),
            ("lts", {"lts": False}, False),
            ("early", {"stable": False}, True),
            ("early", {"stable": True}, False),
        ):
            with self.subTest(track=track, flags=flags):
                self.payload["type"] = flags
                result = await self._check(track)
                self.assertEqual(result is not None, matches)

    async def test_notes_are_newest_first_and_not_limited(self):
        result = await self._check()
        expected = "\n\n".join(item["text"] for item in reversed(self.payload["changelog.md"]))
        self.assertEqual(result.release_notes, expected)
        self.assertGreater(len(result.release_notes), 255)

    async def test_malformed_catalog_is_a_failure_not_up_to_date(self):
        malformed = [None, [], "", {}, {"version": "3.10.0"}]
        for key, value in (
            ("version", None), ("version", ""), ("version", 3),
            ("type", None), ("type", []), ("type", {}),
            ("type", {"stable": "true"}), ("type", {"stable": 1}),
            ("changelog.md", None), ("changelog.md", {}),
            ("changelog.md", ["notes"]),
            ("changelog.md", [{"version": "3.10.0"}]),
            ("changelog.md", [{"version": 3, "text": "notes"}]),
            ("changelog.md", [{"version": "3.10.0", "text": None}]),
        ):
            payload = deepcopy(self.payload)
            payload[key] = value
            malformed.append(payload)
        for payload in malformed:
            with self.subTest(payload=payload):
                self.response.json.return_value = payload
                with self.assertRaises(self.firmware.FirmwareCheckError):
                    await self._check()

    async def test_http_errors_and_redirects_are_not_up_to_date(self):
        for status in (301, 401, 404, 429, 500):
            with self.subTest(status=status):
                self.response.status = status
                with self.assertRaisesRegex(self.firmware.FirmwareCheckError, f"HTTP {status}"):
                    await self._check()
        self.response.json.assert_not_awaited()

    async def test_network_and_json_errors_have_safe_messages(self):
        for error in (
            self.firmware.aiohttp.ClientError("https://example.invalid/?token=private-token"),
            TimeoutError("private-token"),
            ValueError("private-token"),
        ):
            with self.subTest(error=type(error).__name__):
                self.response.json.side_effect = error
                with self.assertRaises(self.firmware.FirmwareCheckError) as ctx:
                    await self._check()
                self.assertEqual(str(ctx.exception), "Firmware server request failed")
                self.assertNotIn("private-token", str(ctx.exception))

    async def test_cancelled_checks_are_not_swallowed(self):
        self.response.json.side_effect = asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await self._check()

    async def test_invalid_inputs_do_not_make_requests(self):
        for package, track, version in (
            ("", "newest", "3.1.0"),
            ("test-package", "invalid", "3.1.0"),
            ("test-package", "newest", ""),
        ):
            with self.subTest(package=package, track=track, version=version):
                with self.assertRaises(self.firmware.FirmwareCheckError):
                    await self.firmware.check(self.session, package, track, version)
        self.session.get.assert_not_called()


class FirmwareEntityTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.update, cls.firmware, cls.coordinators = load_update_module()

    def setUp(self):
        self.payload = release_payload()
        self.response = Response(payload=self.payload)
        self.session = types.SimpleNamespace(get=Mock(return_value=self.response))
        self.hass = types.SimpleNamespace(shared_session=self.session)
        self.api = types.SimpleNamespace(
            session=sentinel.device_session,
            async_get_system_info=AsyncMock(return_value={
                "swVersion": "3.1.0", "firmwarePackage": "test-package",
            }),
            async_get_call_status=AsyncMock(return_value={"state": "idle"}),
            async_get_phone_status=AsyncMock(return_value={}),
            async_get_switch_caps=AsyncMock(return_value={}),
            async_get_switch_status=AsyncMock(return_value={}),
            async_get_io_caps=AsyncMock(return_value={}),
            async_get_io_status=AsyncMock(return_value={}),
        )
        self.entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={
                "host": "example.invalid", "protocol": "https", "port": 443,
                "username": "test-user", "password": "test-secret",
            },
            options={},
        )
        self.coordinator = self.coordinators.TwoNIntercomCoordinator(
            self.hass, self.api, config_entry=self.entry
        )
        self.coordinator._system_info = {
            "swVersion": "3.1.0", "firmwarePackage": "test-package",
        }
        self.entry.runtime_data = self.coordinators.TwoNIntercomRuntimeData(
            coordinator=self.coordinator, api=self.api
        )

    def _entity(self):
        return self.update.TwoNIntercomFirmwareUpdate(
            self.coordinator, self.entry, self.session
        )

    async def test_setup_one_informational_entity_using_shared_session(self):
        added = Mock()
        get_session = Mock(return_value=self.session)
        with patch.object(self.update, "async_get_clientsession", get_session):
            await self.update.async_setup_entry(self.hass, self.entry, added)
        get_session.assert_called_once_with(self.hass)
        entities, update_before_add = added.call_args.args
        self.assertTrue(update_before_add)
        self.assertEqual(len(entities), 1)
        entity = entities[0]
        self.assertIs(entity._session, self.session)
        self.assertIsNot(entity._session, self.api.session)
        self.assertIsInstance(entity, self.update.TwoNIntercomEntity)
        self.assertIsInstance(entity, self.update.UpdateEntity)
        self.assertEqual(entity._attr_unique_id, "entry-1_firmware")
        self.assertEqual(entity._attr_device_class, "firmware")
        self.assertEqual(entity._attr_entity_category, "config")
        features = self.update.UpdateEntityFeature
        self.assertEqual(entity._attr_supported_features, features.RELEASE_NOTES)
        self.assertFalse(entity._attr_supported_features & (features.INSTALL | features.PROGRESS))
        self.assertEqual(entity._attr_translation_key, "firmware")
        self.assertFalse(entity.should_poll)
        self.assertEqual(entity.release_url, "https://example.invalid/")
        self.assertEqual(
            entity._attr_device_info["configuration_url"], entity.release_url
        )

    async def test_missing_package_skips_entity_with_debug_log(self):
        for value in (None, "", "  ", 123):
            with self.subTest(value=value):
                self.coordinator._system_info["firmwarePackage"] = value
                added = Mock()
                with (
                    self.assertLogs(self.update.__name__, level="DEBUG") as logs,
                    patch.object(self.update, "async_get_clientsession") as get_session,
                ):
                    await self.update.async_setup_entry(self.hass, self.entry, added)
                self.assertIn("firmwarePackage", logs.output[0])
                added.assert_not_called()
                get_session.assert_not_called()

    async def test_installed_version_follows_real_coordinator_refresh(self):
        entity = self._entity()
        self.assertEqual(entity.installed_version, "3.1.0")
        self.coordinator.data = await self.coordinator._async_update_data()
        self.api.async_get_system_info.return_value = {
            "swVersion": "3.10.0", "firmwarePackage": "test-package",
        }
        self.coordinator.data = await self.coordinator._async_update_data()
        entity._handle_coordinator_update()
        self.assertEqual(entity.installed_version, "3.10.0")
        self.assertEqual(self.coordinator.system_info["firmwarePackage"], "test-package")
        self.session.get.assert_not_called()

    async def test_device_info_failure_preserves_installed_version(self):
        entity = self._entity()
        self.coordinator.data = await self.coordinator._async_update_data()
        self.api.async_get_system_info.side_effect = TimeoutError
        self.coordinator.data = await self.coordinator._async_update_data()
        self.assertEqual(entity.installed_version, "3.1.0")

    async def test_200_versions_notes_and_summary_limit(self):
        entity = self._entity()
        self.assertIsNone(entity.latest_version)
        self.assertIsNone(await entity.async_release_notes())
        await entity.async_update()
        self.assertEqual(entity.latest_version, "3.10.0")
        self.assertEqual(self.entry.runtime_data.firmware_latest_version, "3.10.0")
        notes = await entity.async_release_notes()
        self.assertTrue(notes.startswith("## Newest release"))
        self.assertTrue(notes.endswith("Older changes"))
        self.assertEqual(entity.release_summary, notes[:255])
        self.assertEqual(len(entity.release_summary), 255)
        self.assertNotIn("private-token", repr(vars(entity)))

    async def test_204_and_mismatched_tracks_clear_obsolete_release_notes(self):
        entity = self._entity()
        for status in (204, 200):
            await entity.async_update()
            self.response.status = status
            self.payload["type"]["stable"] = False
            await entity.async_update()
            self.assertEqual(entity.latest_version, entity.installed_version)
            self.assertIsNone(entity.release_summary)
            self.assertIsNone(await entity.async_release_notes())
            self.response.status = 200
            self.payload["type"]["stable"] = True

    async def test_selected_option_maps_all_channels_not_entry_data(self):
        entity = self._entity()
        self.entry.data["firmware_channel"] = "beta"
        for channel, track, flags in (
            (None, "newest", {"stable": True}),
            ("active_track", "newest", {"stable": True}),
            ("lts", "lts", {"lts": True}),
            ("beta", "early", {"stable": False}),
        ):
            with self.subTest(channel=channel):
                self.entry.options = {} if channel is None else {"firmware_channel": channel}
                self.payload["type"] = flags
                await entity.async_update()
                self.assertEqual(
                    self.session.get.call_args.args[0],
                    f"https://update.2n.cz/hip/test-package/{track}/",
                )
                self.assertEqual(entity.latest_version, "3.10.0")

    async def test_failure_streak_logs_once_keeps_cache_and_recovers(self):
        entity = self._entity()
        await entity.async_update()
        previous_notes = await entity.async_release_notes()
        self.response.status = 503
        with self.assertLogs(self.update.__name__, level="WARNING") as logs:
            await entity.async_update()
            await entity.async_update()
        self.assertEqual(len(logs.output), 1)
        self.assertEqual(entity.latest_version, "3.10.0")
        self.assertEqual(await entity.async_release_notes(), previous_notes)
        self.assertTrue(entity.available)
        self.assertTrue(self.coordinator.last_update_success)
        self.assertIsNone(self.coordinator._log_listener_task)
        self.response.status = 204
        await entity.async_update()
        self.assertEqual(entity.latest_version, "3.1.0")
        self.response.status = 503
        with self.assertLogs(self.update.__name__, level="WARNING") as logs:
            await entity.async_update()
        self.assertEqual(len(logs.output), 1)

    async def test_failed_first_check_stays_unknown_instead_of_up_to_date(self):
        entity = self._entity()
        self.response.json.return_value = {"version": "3.10.0"}
        with self.assertLogs(self.update.__name__, level="WARNING"):
            await entity.async_update()
        self.assertIsNone(entity.latest_version)
        self.assertIsNone(self.entry.runtime_data.firmware_latest_version)
        self.assertIsNone(entity.release_summary)

    async def test_malformed_failed_check_preserves_last_successful_result(self):
        entity = self._entity()
        await entity.async_update()
        self.response.json.return_value = None
        with self.assertLogs(self.update.__name__, level="WARNING"):
            await entity.async_update()
        self.assertEqual(entity.latest_version, "3.10.0")
        self.assertTrue(entity.release_summary)

    async def test_failure_does_not_stop_device_refresh_or_ring_events(self):
        entity = self._entity()
        listener_task = asyncio.create_task(asyncio.sleep(60))
        self.coordinator._log_listener_task = listener_task
        self.session.get.side_effect = TimeoutError("private-token")
        try:
            with self.assertLogs(self.update.__name__, level="WARNING") as logs:
                await entity.async_update()
            self.assertNotIn("private-token", str(logs.output))
            self.coordinator.data = await self.coordinator._async_update_data()
            self.assertTrue(self.coordinator.data.available)
            self.assertTrue(self.coordinator._process_log_event({
                "event": "CallStateChanged",
                "params": {"state": "ringing", "direction": "outgoing", "session": 1},
            }))
            self.assertEqual(self.coordinator.ring_count, 1)
            self.assertFalse(listener_task.done())
            self.assertIs(self.coordinator._log_listener_task, listener_task)
        finally:
            listener_task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await listener_task

    async def test_separate_interval_initial_check_manual_refresh_and_cleanup(self):
        added = Mock()
        await self.update.async_setup_entry(self.hass, self.entry, added)
        entities, refresh = added.call_args.args
        entity = entities[0]
        if refresh:
            await entity.async_update()
        self.assertEqual(self.session.get.call_count, 1)
        cancel = Mock()
        with patch.object(
            self.update, "async_track_time_interval", return_value=cancel
        ) as track:
            await entity.async_added_to_hass()
        track.assert_called_once_with(
            self.hass, entity._async_interval_update, timedelta(hours=6)
        )
        for _ in range(3):
            self.coordinator.data = await self.coordinator._async_update_data()
            entity._handle_coordinator_update()
        self.assertEqual(self.session.get.call_count, 1)
        now = datetime(2026, 1, 2, tzinfo=timezone.utc)
        with patch.object(self.update.dt_util, "utcnow", return_value=now):
            await track.call_args.args[1](now)
        self.assertEqual(self.session.get.call_count, 2)
        self.assertEqual(entity._last_check, now)
        self.assertIsNotNone(entity._last_check.utcoffset())
        # homeassistant.update_entity invokes the entity's async_update directly.
        await entity.async_update()
        self.assertEqual(self.session.get.call_count, 3)
        for callback in entity.remove_callbacks:
            callback()
        cancel.assert_called_once_with()

    async def test_concurrent_checks_are_serialized(self):
        entity = self._entity()
        active = 0
        maximum_active = 0

        async def check(*args):
            nonlocal active, maximum_active
            active += 1
            maximum_active = max(maximum_active, active)
            await asyncio.sleep(0)
            active -= 1
            return None

        with patch.object(self.update, "check", side_effect=check):
            await asyncio.gather(entity.async_update(), entity.async_update())
        self.assertEqual(maximum_active, 1)

    def test_shared_web_ui_url_handles_defaults_nondefault_ports_and_ipv6(self):
        for protocol, host, port, expected in (
            ("https", "example.invalid", None, "https://example.invalid/"),
            ("https", "example.invalid", 443, "https://example.invalid/"),
            ("https", "example.invalid", 8443, "https://example.invalid:8443/"),
            ("http", "example.invalid", None, "http://example.invalid/"),
            ("http", "example.invalid", 80, "http://example.invalid/"),
            ("http", "example.invalid", 8080, "http://example.invalid:8080/"),
            ("https", "2001:db8::1", 443, "https://[2001:db8::1]/"),
            ("http", "[2001:db8::1]", 8080, "http://[2001:db8::1]:8080/"),
        ):
            with self.subTest(protocol=protocol, host=host, port=port):
                self.entry.data.update({"host": host, "protocol": protocol})
                self.entry.data.pop("port", None)
                if port is not None:
                    self.entry.data["port"] = port
                self.entry.options.update({
                    "host": "ignored.invalid", "protocol": "http", "port": 1234
                })
                entity = self._entity()
                self.assertEqual(entity.release_url, expected)
                self.assertEqual(entity._attr_device_info["configuration_url"], expected)
                self.assertIsNone(urlsplit(entity.release_url).username)
                self.assertIsNone(urlsplit(entity.release_url).password)
                self.assertNotIn("test-secret", entity.release_url)


class FirmwareReadOnlyContractTests(unittest.TestCase):
    def test_integration_has_no_device_firmware_endpoint_literals(self):
        prohibited = re.compile(r"/api/(?:firmware|autoupdate)(?:[/\"'?]|$)")
        for path in INTEGRATION_DIR.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    with self.subTest(file=path.name, line=node.lineno):
                        self.assertIsNone(prohibited.search(node.value))

    def test_firmware_platform_translations_and_icons_are_wired(self):
        for name in ("strings.json", "translations/en.json", "translations/de.json", "translations/cs.json"):
            data = json.loads((INTEGRATION_DIR / name).read_text(encoding="utf-8"))
            with self.subTest(name=name):
                self.assertTrue(data["entity"]["update"]["firmware"]["name"])
                self.assertTrue(data["options"]["step"]["device"]["data"]["firmware_channel"])
                self.assertTrue(data["options"]["step"]["device"]["data_description"]["firmware_channel"])
                self.assertEqual(
                    set(data["selector"]["firmware_channel"]["options"]),
                    {"active_track", "lts", "beta"},
                )
        icons = json.loads((INTEGRATION_DIR / "icons.json").read_text(encoding="utf-8"))
        self.assertEqual(icons["entity"]["update"]["firmware"]["default"], "mdi:chip")

    def test_firmware_user_documentation_covers_read_only_behavior(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        for expected in ("### Firmware updates", "firmware_channel", "device web UI", "six hours"):
            self.assertIn(expected, readme)
        endpoints = readme.split("## 2N API Endpoints Used", 1)[1].split("## Data Updates", 1)[0]
        self.assertIn("https://update.2n.cz/hip/", endpoints)
        reference = (REPO_ROOT / "docs/API_REFERENCE.md").read_text(encoding="utf-8")
        self.assertIn("firmware_channel", reference)
        self.assertIn("RELEASE_NOTES", reference)


if __name__ == "__main__":
    unittest.main()
