"""Coordinator event-picture hooks with real storage and no HA or network."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from itertools import product
from pathlib import Path
import shutil
import sys
import threading
import types
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from _stubs import INTEGRATION_DIR, load_module
from test_coordinator_access import _CoordinatorTestCase, _FakeAPI, _Hass

_DEFAULT_ROOT = object()
_ACCESS_TYPES = {
    "CardEntered": "card_entered",
    "CodeEntered": "code_entered",
    "MobKeyEntered": "mobile_key_entered",
    "FingerEntered": "fingerprint_entered",
    "ApiAccessRequested": "api_access_requested",
    "UserAuthenticated": "user_authenticated",
    "UserRejected": "user_rejected",
    "AccessTaken": "access_taken",
    "AccessBlocked": "access_blocked",
    "AccessLimited": "access_limited",
}
_CREDENTIAL_EVENTS = tuple(_ACCESS_TYPES)[:4]
_SECRETS = {
    "uid": "A1B2C3D4",
    "code": "97531086",
    "authid": "synthetic-mobile-key",
    "name": "Synthetic Visitor",
    "uuid": "11111111-2222-4333-8444-555555555555",
    "peer": "visitor@example.invalid",
}


class _ExecutorHass(_Hass):
    def __init__(self) -> None:
        super().__init__()
        self.executor_calls = []
        self.executor_threads = []
        self.before_executor = None

    async def async_add_executor_job(self, func, *args):
        self.executor_calls.append((func, args))
        if self.before_executor is not None:
            self.before_executor(func, args)

        def execute():
            self.executor_threads.append(threading.get_ident())
            return func(*args)

        return await asyncio.to_thread(execute)

    async def drain(self) -> None:
        # Unlike the shared harness, surface background-task failures.
        while self.tasks:
            pending, self.tasks = self.tasks, []
            await asyncio.gather(*pending)


class CoordinatorEventPictureTests(_CoordinatorTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.pictures = load_module(
            "custom_components.2n_intercom.event_pictures",
            INTEGRATION_DIR / "event_pictures.py",
        )

    def setUp(self) -> None:
        self.root = Path.cwd() / f".event-picture-tests-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.local_time = datetime(
            2026, 4, 18, 9, 10, 11, tzinfo=timezone(timedelta(hours=2))
        )
        self.clock = Mock(return_value=100.0)
        patches = (
            patch.object(self.pictures, "time", types.SimpleNamespace(monotonic=self.clock)),
            patch.object(self.module.dt_util, "now", return_value=self.local_time),
            patch.object(
                self.module.dt_util, "utcnow",
                return_value=self.local_time.astimezone(timezone.utc),
            ),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    async def _new(self, api=None, *, store=True, media_root=_DEFAULT_ROOT, **kwargs):
        hass = _ExecutorHass()
        api = api or _FakeAPI(snapshot=b"\xff\xd8synthetic-frame\xff\xd9")
        entry = types.SimpleNamespace(entry_id="picture-entry", title="Front Door")
        picture_store = None
        if store:
            root = self.root if media_root is _DEFAULT_ROOT else media_root
            picture_store = self.pictures.EventPictureStore(hass, entry, root, 7)
            await picture_store.async_initialize()
        kwargs.setdefault("ring_snapshot_enabled", True)
        coordinator = self.module.TwoNIntercomCoordinator(
            hass, api, config_entry=entry, picture_store=picture_store, **kwargs
        )
        coordinator.async_request_refresh = AsyncMock()
        coordinator.async_update_listeners = Mock()
        coordinator.data = self.module.TwoNIntercomData(
            call_status={}, last_ring_time=None, caller_info=None,
            active_session_id=None, available=True, phone_status={},
            switch_caps={}, switch_status={}, io_caps={}, io_status={},
        )
        api_module = sys.modules["custom_components.2n_intercom.api"]
        coordinator._camera_transport_info = api_module.CameraTransportInfo(source="external")
        self.addAsyncCleanup(hass.drain)
        return coordinator, hass, api

    def _access(self, coordinator, name="CardEntered", valid=True):
        return coordinator._process_log_event({
            "event": name,
            "utcTime": 1548078453,
            "params": {
                **_SECRETS, "valid": valid, "ap": 0, "session": 7,
                "direction": "IN", "state": "in", "type": "finger",
            },
        })

    def _ring(self, coordinator, *, state="ringing", event="CallStateChanged", peer=None):
        params = {"state": state, "session": 1, "direction": "outgoing"}
        if event == "CallSessionStateChanged":
            params["originator"] = "button"
        if peer is not None:
            params["peer"] = peer
        return coordinator._process_log_event({"event": event, "params": params})

    def _emit_kind(self, coordinator, kind):
        if kind == "ring":
            self._ring(coordinator, state="idle")
            return self._ring(coordinator)
        return self._access(coordinator, valid=kind == "access-granted")

    def _files(self):
        return set(self.root.rglob("*.jpg"))

    def _seed_ring(self, coordinator):
        coordinator._ring_snapshot = b"previous-ring"
        coordinator._ring_snapshot_time = datetime(2026, 4, 17, tzinfo=timezone.utc)
        coordinator._publish_event_state()
        return coordinator.ring_snapshot, coordinator.ring_snapshot_time

    def _assert_ring(self, coordinator, image, timestamp):
        self.assertEqual(coordinator.ring_snapshot, image)
        self.assertEqual(coordinator.ring_snapshot_time, timestamp)
        self.assertEqual(coordinator.data.ring_snapshot, image)
        self.assertEqual(coordinator.data.ring_snapshot_time, timestamp)

    def _assert_private(self, text):
        for value in _SECRETS.values():
            self.assertNotIn(value.casefold(), text.casefold())

    async def test_counted_ring_saves_existing_capture_after_ram_is_published(self) -> None:
        coordinator, hass, api = await self._new()

        def observe_save(func, args):
            if func is self.pictures._save_picture:
                self.assertIs(coordinator.ring_snapshot, api.snapshot)
                self.assertIs(coordinator.data.ring_snapshot, api.snapshot)
                coordinator.async_update_listeners.assert_called()

        hass.before_executor = observe_save
        self.assertTrue(self._ring(coordinator))
        self.assertTrue(self._ring(coordinator, event="CallSessionStateChanged"))
        await hass.drain()

        self.assertEqual(coordinator.ring_count, 1)
        self.assertEqual(coordinator.bus_events_fired, {"ring": 1})
        self.assertEqual(api.snapshot_calls, [
            {"width": None, "height": None, "source": "external"},
        ])
        path = self.root / "2n_intercom/front_door/2026-04-18/091011-ring.jpg"
        self.assertEqual(self._files(), {path})
        self.assertEqual(path.read_bytes(), api.snapshot)
        self._assert_ring(coordinator, api.snapshot, self.local_time.astimezone(timezone.utc))
        self.assertEqual(
            [func for func, _ in hass.executor_calls],
            [self.pictures.is_writable, self.pictures._save_picture],
        )
        self.assertTrue(all(
            thread != threading.get_ident() for thread in hass.executor_threads
        ))

    async def test_counted_button_ring_saves_once(self) -> None:
        coordinator, hass, api = await self._new(ring_on_keypress=True)
        with patch.object(coordinator, "_schedule_keypress_ring_clear"):
            for _ in range(2):
                coordinator._process_log_event({
                    "event": "KeyPressed", "params": {"key": "%1"},
                })
        await hass.drain()
        self.assertEqual(coordinator.ring_count, 1)
        self.assertEqual(len(api.snapshot_calls), 1)
        self.assertEqual(len(self._files()), 1)
        self.assertEqual(next(iter(self._files())).read_bytes(), coordinator.ring_snapshot)

    async def test_no_store_writes_nothing_with_ring_capture_on_or_off(self) -> None:
        for ring_enabled in (False, True):
            with self.subTest(ring_enabled=ring_enabled):
                coordinator, hass, api = await self._new(
                    store=False, ring_snapshot_enabled=ring_enabled
                )
                self.assertIsNone(coordinator.picture_store)
                self._ring(coordinator)
                self._access(coordinator)
                await hass.drain()
                self.assertEqual(self._files(), set())
                self.assertEqual(hass.executor_calls, [])
                self.assertEqual(len(api.snapshot_calls), int(ring_enabled))
                self.assertEqual(coordinator.ring_count, 1)
                self.assertEqual(len(hass.bus.events), 2)
                expected = api.snapshot if ring_enabled else None
                self.assertEqual(coordinator.ring_snapshot, expected)

    async def test_each_credential_result_saves_kind_without_changing_ring(self) -> None:
        for name, valid in product(_CREDENTIAL_EVENTS, (True, False)):
            with self.subTest(event=name, valid=valid):
                before = self._files()
                coordinator, hass, api = await self._new()
                previous_image, previous_time = self._seed_ring(coordinator)
                self.assertTrue(self._access(coordinator, name, valid))
                self.assertEqual(api.snapshot_calls, [])
                self.assertEqual(len(hass.bus.events), 1)
                await hass.drain()

                paths = self._files() - before
                self.assertEqual(len(paths), 1)
                path = next(iter(paths))
                kind = "access-granted" if valid else "access-denied"
                self.assertRegex(path.name, rf"^\d{{6}}-{kind}(?:-\d+)?\.jpg$")
                self.assertEqual(path.read_bytes(), api.snapshot)
                self.assertEqual(api.snapshot_calls, [
                    {"width": None, "height": None, "source": "external"},
                ])
                self._assert_ring(coordinator, previous_image, previous_time)
                self.assertEqual(coordinator.ring_count, 0)
                self.assertEqual(coordinator.bus_events_fired, {_ACCESS_TYPES[name]: 1})
                self._assert_private(path.relative_to(self.root).as_posix())

    async def test_api_and_every_followup_capture_nothing_even_without_throttling(self) -> None:
        coordinator, hass, api = await self._new()
        previous_image, previous_time = self._seed_ring(coordinator)
        excluded = tuple(_ACCESS_TYPES)[4:]
        for index, name in enumerate(excluded):
            self.clock.return_value = 100.0 + index * 10
            self.assertTrue(self._access(coordinator, name))
            await hass.drain()

        self.assertEqual(api.snapshot_calls, [])
        self.assertEqual(self._files(), set())
        self.assertEqual([func for func, _ in hass.executor_calls], [self.pictures.is_writable])
        self.assertEqual(
            [payload["type"] for _, payload in hass.bus.events],
            [_ACCESS_TYPES[name] for name in excluded],
        )
        self._assert_ring(coordinator, previous_image, previous_time)
        self.assertTrue(coordinator.picture_store.try_reserve())

    async def test_exact_bus_payloads_match_without_store_for_all_access_types(self) -> None:
        for name in _ACCESS_TYPES:
            for valid in (True, False):
                with self.subTest(event=name, valid=valid):
                    coordinator, hass, _ = await self._new()
                    baseline, baseline_hass, _ = self._make(
                        config_entry=coordinator.config_entry
                    )
                    self._access(baseline, name, valid)
                    self._access(coordinator, name, valid)
                    self.assertEqual(hass.bus.events, baseline_hass.bus.events)
                    payload = hass.bus.events[0][1]
                    self.assertEqual(hass.bus.events[0][0], "2n_intercom_event")
                    self.assertEqual(set(payload), {
                        "device_id", "config_entry_id", "type", "timestamp",
                        "credential_type", "access_point", "direction", "granted",
                        "reason", "state", "user_uuid", "user_name", "session",
                    })
                    self.assertEqual(payload["type"], _ACCESS_TYPES[name])
                    self.assertEqual(payload["timestamp"], "2019-01-21T13:47:33+00:00")
                    self.assertEqual(coordinator.bus_events_fired, baseline.bus_events_fired)
                    await hass.drain()
                    await baseline_hass.drain()
                    self.assertEqual(hass.bus.events, baseline_hass.bus.events)

    async def test_ring_and_access_paths_never_use_replayed_identity(self) -> None:
        coordinator, hass, _ = await self._new()
        self._ring(coordinator, peer=_SECRETS["peer"])
        await hass.drain()
        for index, (name, valid) in enumerate(product(_CREDENTIAL_EVENTS, (True, False)), 1):
            self.clock.return_value = 100.0 + index * 10
            self._access(coordinator, name, valid)
            await hass.drain()

        self.assertEqual(len(self._files()), 9)
        for path in self._files():
            relative = path.relative_to(self.root).as_posix()
            self._assert_private(relative)
            self.assertRegex(
                relative,
                r"^2n_intercom/front_door/2026-04-18/"
                r"091011-(?:ring|access-granted|access-denied)(?:-\d+)?\.jpg$",
            )

    async def test_shared_ten_second_window_for_every_pair_of_capture_kinds(self) -> None:
        kinds = ("ring", "access-granted", "access-denied")
        for first, second in product(kinds, repeat=2):
            with self.subTest(first=first, second=second):
                self.clock.return_value = 100.0
                before = self._files()
                coordinator, hass, api = await self._new()
                self._seed_ring(coordinator)
                self._emit_kind(coordinator, first)
                await hass.drain()
                self.assertEqual(len(api.snapshot_calls), 1)
                self.assertEqual(len(self._files() - before), 1)
                previous_image, previous_time = (
                    coordinator.ring_snapshot, coordinator.ring_snapshot_time
                )

                self.clock.return_value = 109.999
                api.snapshot = b"within-window"
                self._emit_kind(coordinator, second)
                await hass.drain()
                requests = 1 + int(second == "ring")
                self.assertEqual(len(api.snapshot_calls), requests)
                self.assertEqual(len(self._files() - before), 1)
                if second == "ring":
                    self._assert_ring(
                        coordinator, b"within-window", self.local_time.astimezone(timezone.utc)
                    )
                else:
                    self._assert_ring(coordinator, previous_image, previous_time)

                self.clock.return_value = 110.0
                api.snapshot = b"at-ten-seconds"
                self._emit_kind(coordinator, second)
                await hass.drain()
                self.assertEqual(len(api.snapshot_calls), requests + 1)
                new_files = self._files() - before
                self.assertEqual(len(new_files), 2)
                self.assertIn(b"at-ten-seconds", [path.read_bytes() for path in new_files])
                self.assertEqual(len(hass.bus.events), 3)

    async def test_two_synchronous_access_events_reserve_before_any_request(self) -> None:
        coordinator, hass, api = await self._new()
        self._access(coordinator, "CardEntered", True)
        self._access(coordinator, "CodeEntered", False)
        self.assertEqual(api.snapshot_calls, [])
        self.assertEqual(len(hass.tasks), 1)
        self.assertEqual(len(hass.bus.events), 2)
        self.assertEqual(coordinator.bus_events_fired, {
            "card_entered": 1, "code_entered": 1,
        })
        await hass.drain()
        self.assertEqual(len(api.snapshot_calls), 1)
        self.assertEqual(len(self._files()), 1)
        self.assertTrue(next(iter(self._files())).name.endswith("-access-granted.jpg"))

    async def test_ring_reserves_before_request_can_trigger_competing_access(self) -> None:
        coordinator, hass, api = await self._new()
        original_snapshot = api.async_get_snapshot

        async def snapshot(**kwargs):
            self._access(coordinator, "CodeEntered", False)
            return await original_snapshot(**kwargs)

        api.async_get_snapshot = snapshot
        self._ring(coordinator)
        await hass.drain()
        self.assertEqual(len(api.snapshot_calls), 1)
        self.assertEqual(coordinator.bus_events_fired, {"ring": 1, "code_entered": 1})
        self.assertEqual(len(self._files()), 1)
        self.assertTrue(next(iter(self._files())).name.endswith("-ring.jpg"))

    async def test_throttle_uses_start_not_completion_of_pending_request(self) -> None:
        coordinator, hass, api = await self._new()
        started = asyncio.Event()
        release = asyncio.Event()
        original_snapshot = api.async_get_snapshot

        async def snapshot(**kwargs):
            result = await original_snapshot(**kwargs)
            started.set()
            await release.wait()
            return result

        api.async_get_snapshot = snapshot
        self._access(coordinator)
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
            self.clock.return_value = 109.999
            self._access(coordinator, "CodeEntered", False)
            self.assertEqual(len(hass.tasks), 1)
            self.assertEqual(len(api.snapshot_calls), 1)
            self.clock.return_value = 110.0
            self._access(coordinator, "FingerEntered", False)
            self.assertEqual(len(hass.tasks), 2)
        finally:
            release.set()
        await hass.drain()
        self.assertEqual(len(api.snapshot_calls), 2)
        self.assertEqual(len(self._files()), 2)
        self.assertEqual(len(hass.bus.events), 3)

    async def test_snapshot_failures_keep_ram_counters_and_events_without_private_logs(self) -> None:
        private_error = " ".join(_SECRETS.values())
        failures = (RuntimeError(private_error), OSError(private_error), None, b"")
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                self.clock.return_value = 100.0
                coordinator, hass, api = await self._new(_FakeAPI(snapshot=failure))
                previous_image, previous_time = self._seed_ring(coordinator)
                with self.assertLogs("custom_components.2n_intercom", level="DEBUG") as logs:
                    self._ring(coordinator)
                    await hass.drain()
                    self.clock.return_value = 110.0
                    self._access(coordinator)
                    await hass.drain()

                self._assert_ring(coordinator, previous_image, previous_time)
                self.assertEqual(coordinator.ring_count, 1)
                self.assertEqual(coordinator.bus_events_fired, {"ring": 1, "card_entered": 1})
                self.assertEqual(len(hass.bus.events), 2)
                self.assertEqual(len(api.snapshot_calls), 2)
                self.assertEqual(self._files(), set())
                self._assert_private("\n".join(logs.output))
                self.assertIn("keeping previous image", "\n".join(logs.output))

    async def test_oserror_writes_do_not_escape_or_corrupt_ram_events_or_counters(self) -> None:
        coordinator, hass, api = await self._new()
        self._seed_ring(coordinator)
        for failing_operation in ("replace", "write_picture"):
            with self.subTest(operation=failing_operation):
                self.clock.return_value += 10
                ring_frame = f"ring-{failing_operation}".encode()
                api.snapshot = ring_frame
                target = self.pictures.os if failing_operation == "replace" else self.pictures
                with patch.object(
                    target, failing_operation, side_effect=OSError(" ".join(_SECRETS.values()))
                ), self.assertLogs(self.pictures._LOGGER, level="WARNING") as logs:
                    self._ring(coordinator, state="idle")
                    self._ring(coordinator)
                    await hass.drain()
                    self._assert_ring(
                        coordinator, api.snapshot, self.local_time.astimezone(timezone.utc)
                    )
                    self.clock.return_value += 10
                    api.snapshot = b"access-image-must-not-replace-ring"
                    self._access(coordinator, valid=False)
                    await hass.drain()

                self.assertEqual(len(logs.records), 2)
                self._assert_private("\n".join(logs.output))
                self.assertEqual(self._files(), set())
                self.assertEqual(list(self.root.rglob("*.tmp")), [])
                self._assert_ring(
                    coordinator, ring_frame, self.local_time.astimezone(timezone.utc),
                )
        self.assertEqual(coordinator.ring_count, 2)
        self.assertEqual(coordinator.bus_events_fired, {"ring": 2, "card_entered": 2})
        self.assertEqual(len(hass.bus.events), 4)
        self.assertEqual(len(api.snapshot_calls), 4)

    async def test_unavailable_media_warns_once_and_never_breaks_event_handling(self) -> None:
        for availability in ("not-configured", "missing", "not-writable"):
            with self.subTest(availability=availability):
                root = None if availability == "not-configured" else self.root
                if availability == "missing":
                    root = self.root / "missing"
                probe = patch.object(
                    self.pictures.tempfile, "TemporaryFile",
                    side_effect=PermissionError(" ".join(_SECRETS.values())),
                ) if availability == "not-writable" else patch.object(
                    self.pictures, "is_writable", wraps=self.pictures.is_writable
                )
                with probe, self.assertLogs(self.pictures._LOGGER, level="WARNING") as logs:
                    coordinator, hass, api = await self._new(media_root=root)
                    store = coordinator.picture_store
                    await store.async_initialize()
                    await store.async_initialize()
                    self.assertFalse(store.enabled)
                    self.assertFalse(store.try_reserve())
                    self._ring(coordinator)
                    self._access(coordinator)
                    await hass.drain()

                self.assertEqual(len(logs.records), 1)
                self._assert_private("\n".join(logs.output))
                self.assertEqual(len(api.snapshot_calls), 1)
                self.assertEqual(coordinator.ring_count, 1)
                self.assertEqual(coordinator.bus_events_fired, {"ring": 1, "card_entered": 1})
                self.assertEqual(len(hass.bus.events), 2)
                self.assertEqual(self._files(), set())
                self._assert_ring(
                    coordinator, api.snapshot, self.local_time.astimezone(timezone.utc)
                )
