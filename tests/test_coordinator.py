"""Unit tests for the 2N Intercom coordinator."""

from __future__ import annotations

import asyncio
import sys
import types
import unittest

from _stubs import (
    API_PATH,
    CONST_PATH,
    COORDINATOR_PATH,
    ensure_package,
    install_api_stubs,
    load_module,
)


def _install_homeassistant_stubs() -> None:
    ensure_package("homeassistant")

    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    sys.modules["homeassistant.core"] = core

    exceptions = types.ModuleType("homeassistant.exceptions")

    class ConfigEntryNotReady(Exception):
        pass

    exceptions.ConfigEntryNotReady = ConfigEntryNotReady
    sys.modules["homeassistant.exceptions"] = exceptions

    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class DataUpdateCoordinator:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, hass, logger, name, update_interval) -> None:
            del logger, name, update_interval
            self.hass = hass
            self.data = None
            self.last_update_success = True

    class UpdateFailed(Exception):
        pass

    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.UpdateFailed = UpdateFailed
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator
    ensure_package("homeassistant.helpers")

    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    CONNECTION_NETWORK_MAC = "mac"
    DeviceInfo = dict
    device_registry.CONNECTION_NETWORK_MAC = CONNECTION_NETWORK_MAC
    device_registry.DeviceInfo = DeviceInfo
    sys.modules["homeassistant.helpers.device_registry"] = device_registry


def load_coordinator_module():
    install_api_stubs()
    _install_homeassistant_stubs()
    ensure_package("custom_components")
    ensure_package("custom_components.2n_intercom")
    load_module("custom_components.2n_intercom.const", CONST_PATH)
    load_module("custom_components.2n_intercom.api", API_PATH)
    return load_module("custom_components.2n_intercom.coordinator", COORDINATOR_PATH)


class TwoNIntercomCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    """Tests for coordinator call-state tracking."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator_module = load_coordinator_module()

    async def test_tracks_active_session_id_from_call_status(self) -> None:
        coordinator_module = self.coordinator_module

        class FakeAPI:
            async def async_get_system_info(self):
                return {"model": "2N"}

            async def async_get_call_status(self):
                return {
                    "state": "ringing",
                    "sessions": [
                        {
                            "session": "session-123",
                            "direction": "incoming",
                            "state": "ringing",
                            "calls": [{"peer": "100"}],
                        }
                    ],
                }

        hass = types.SimpleNamespace()
        coordinator = coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())

        data = await coordinator._async_update_data()
        coordinator.data = data

        self.assertEqual(data.active_session_id, "session-123")
        self.assertEqual(coordinator.active_session_id, "session-123")
        self.assertEqual(coordinator.call_state, "ringing")

    async def test_does_not_fall_back_to_ended_session_ids(self) -> None:
        coordinator_module = self.coordinator_module

        class FakeAPI:
            async def async_get_system_info(self):
                return {"model": "2N"}

            async def async_get_call_status(self):
                return {
                    "state": "idle",
                    "sessions": [
                        {
                            "session": "session-ended-1",
                            "direction": "incoming",
                            "state": "ended",
                            "calls": [{"peer": "100"}],
                        },
                        {
                            "session": "session-idle-2",
                            "direction": "incoming",
                            "state": "idle",
                            "calls": [{"peer": "101"}],
                        },
                    ],
                }

        hass = types.SimpleNamespace()
        coordinator = coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())

        data = await coordinator._async_update_data()
        coordinator.data = data

        self.assertIsNone(data.active_session_id)
        self.assertIsNone(coordinator.active_session_id)

    async def test_no_sessions_means_no_active_session(self) -> None:
        coordinator_module = self.coordinator_module

        class FakeAPI:
            async def async_get_system_info(self):
                return {"model": "2N"}

            async def async_get_call_status(self):
                return {"state": "idle", "sessions": []}

        hass = types.SimpleNamespace()
        coordinator = coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())

        data = await coordinator._async_update_data()
        coordinator.data = data

        self.assertIsNone(data.active_session_id)
        self.assertIsNone(coordinator.active_session_id)

    async def test_refresh_caches_phone_switch_and_io_data(self) -> None:
        coordinator_module = self.coordinator_module

        class FakeAPI:
            async def async_get_system_info(self):
                return {"model": "2N"}

            async def async_get_call_status(self):
                return {"state": "idle", "sessions": []}

            async def async_get_phone_status(self):
                return {"accounts": [{"account": 1, "registered": True}]}

            async def async_get_switch_caps(self):
                return {"switches": [{"switch": 1, "enabled": True}]}

            async def async_get_switch_status(self):
                return {"switches": [{"switch": 1, "active": False}]}

            async def async_get_io_caps(self):
                return {"ports": [{"port": "relay1", "type": "output"}]}

            async def async_get_io_status(self):
                return {"ports": [{"port": "relay1", "state": 0}]}

        hass = types.SimpleNamespace()
        coordinator = coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())

        data = await coordinator._async_update_data()
        coordinator.data = data

        self.assertEqual(data.phone_status, {"accounts": [{"account": 1, "registered": True}]})
        self.assertEqual(data.switch_caps, {"switches": [{"switch": 1, "enabled": True}]})
        self.assertEqual(data.switch_status, {"switches": [{"switch": 1, "active": False}]})
        self.assertEqual(data.io_caps, {"ports": [{"port": "relay1", "type": "output"}]})
        self.assertEqual(data.io_status, {"ports": [{"port": "relay1", "state": 0}]})
        self.assertEqual(coordinator.phone_status, data.phone_status)
        self.assertEqual(coordinator.switch_caps, data.switch_caps)
        self.assertEqual(coordinator.switch_status, data.switch_status)
        self.assertEqual(coordinator.io_caps, data.io_caps)
        self.assertEqual(coordinator.io_status, data.io_status)

    async def test_secondary_refresh_failure_keeps_previous_cache(self) -> None:
        coordinator_module = self.coordinator_module

        class FakeAPI:
            def __init__(self) -> None:
                self.calls = 0

            async def async_get_system_info(self):
                return {"model": "2N"}

            async def async_get_call_status(self):
                return {"state": "idle", "sessions": []}

            async def async_get_phone_status(self):
                self.calls += 1
                if self.calls > 1:
                    raise RuntimeError("temporary phone status failure")
                return {"accounts": [{"account": 1, "registered": True}]}

            async def async_get_switch_caps(self):
                return {"switches": [{"switch": 1, "enabled": True}]}

            async def async_get_switch_status(self):
                return {"switches": [{"switch": 1, "active": False}]}

            async def async_get_io_caps(self):
                return {"ports": [{"port": "relay1", "type": "output"}]}

            async def async_get_io_status(self):
                return {"ports": [{"port": "relay1", "state": 0}]}

        hass = types.SimpleNamespace()
        coordinator = coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())

        first = await coordinator._async_update_data()
        coordinator.data = first
        second = await coordinator._async_update_data()
        coordinator.data = second

        self.assertEqual(first.phone_status, {"accounts": [{"account": 1, "registered": True}]})
        self.assertEqual(second.phone_status, {"accounts": [{"account": 1, "registered": True}]})
        self.assertEqual(coordinator.phone_status, {"accounts": [{"account": 1, "registered": True}]})

    async def test_process_call_state_event_sets_ring_and_active_session(self) -> None:
        coordinator_module = self.coordinator_module

        class FakeAPI:
            async def async_get_system_info(self):
                return {"model": "2N"}

            async def async_get_call_status(self):
                return {"state": "idle", "sessions": []}

        hass = types.SimpleNamespace()
        coordinator = coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())

        data = await coordinator._async_update_data()
        coordinator.data = data

        coordinator._process_log_event(
            {
                "event": "CallStateChanged",
                "params": {
                    "direction": "incoming",
                    "state": "ringing",
                    "peer": "sip:100@example.com",
                    "session": 42,
                },
            }
        )

        self.assertEqual(coordinator.active_session_id, "42")
        self.assertEqual(coordinator.called_peer, "100")
        self.assertEqual(coordinator.call_state, "ringing")
        self.assertTrue(coordinator.ring_active)

    async def test_process_call_state_event_clears_ring_and_session_on_terminated(self) -> None:
        coordinator_module = self.coordinator_module

        class FakeAPI:
            async def async_get_system_info(self):
                return {"model": "2N"}

            async def async_get_call_status(self):
                return {"state": "idle", "sessions": []}

        hass = types.SimpleNamespace()
        coordinator = coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())

        data = await coordinator._async_update_data()
        coordinator.data = data

        coordinator._process_log_event(
            {
                "event": "CallStateChanged",
                "params": {
                    "direction": "incoming",
                    "state": "ringing",
                    "peer": "sip:100@example.com",
                    "session": 42,
                },
            }
        )
        coordinator._process_log_event(
            {
                "event": "CallStateChanged",
                "params": {
                    "direction": "incoming",
                    "state": "terminated",
                    "session": 42,
                },
            }
        )

        self.assertIsNone(coordinator.active_session_id)
        self.assertEqual(coordinator.call_state, "terminated")
        self.assertFalse(coordinator.ring_active)

    async def test_process_call_session_state_event_sets_ring_and_active_session(self) -> None:
        coordinator_module = self.coordinator_module

        class FakeAPI:
            async def async_get_system_info(self):
                return {"model": "2N"}

            async def async_get_call_status(self):
                return {"state": "idle", "sessions": []}

        hass = types.SimpleNamespace()
        coordinator = coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())

        data = await coordinator._async_update_data()
        coordinator.data = data

        coordinator._process_log_event(
            {
                "event": "CallSessionStateChanged",
                "params": {
                    "direction": "incoming",
                    "state": "ringing",
                    "address": "sip:100@example.com",
                    "sessionNumber": 42,
                    "callSequenceNumber": 7,
                },
            }
        )

        self.assertEqual(coordinator.active_session_id, "42")
        self.assertEqual(coordinator.called_peer, "100")
        self.assertEqual(coordinator.call_state, "ringing")
        self.assertTrue(coordinator.ring_active)

    async def test_process_call_session_state_event_clears_ring_and_session_on_idle(self) -> None:
        coordinator_module = self.coordinator_module

        class FakeAPI:
            async def async_get_system_info(self):
                return {"model": "2N"}

            async def async_get_call_status(self):
                return {"state": "idle", "sessions": []}

        hass = types.SimpleNamespace()
        coordinator = coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())

        data = await coordinator._async_update_data()
        coordinator.data = data

        coordinator._process_log_event(
            {
                "event": "CallSessionStateChanged",
                "params": {
                    "direction": "incoming",
                    "state": "ringing",
                    "address": "sip:100@example.com",
                    "sessionNumber": 42,
                    "callSequenceNumber": 7,
                },
            }
        )
        self.assertEqual(coordinator.active_session_id, "42")
        self.assertTrue(coordinator.ring_active)

        coordinator._process_log_event(
            {
                "event": "CallSessionStateChanged",
                "params": {
                    "direction": "incoming",
                    "state": "idle",
                    "sessionNumber": 42,
                    "callSequenceNumber": 7,
                },
            }
        )

        self.assertIsNone(coordinator.active_session_id)
        self.assertEqual(coordinator.call_state, "idle")
        self.assertFalse(coordinator.ring_active)

    async def test_stop_log_listener_unsubscribes_active_channel(self) -> None:
        coordinator_module = self.coordinator_module

        class FakeAPI:
            def __init__(self) -> None:
                self.unsubscribed: list[int] = []

            async def async_get_system_info(self):
                return {"model": "2N"}

            async def async_get_call_status(self):
                return {"state": "idle", "sessions": []}

            async def async_unsubscribe_log(self, subscription_id: int) -> bool:
                self.unsubscribed.append(subscription_id)
                return True

        hass = types.SimpleNamespace(async_create_task=asyncio.create_task)
        api = FakeAPI()
        coordinator = coordinator_module.TwoNIntercomCoordinator(hass, api)

        coordinator._log_subscription_id = 287363148
        coordinator._log_listener_task = asyncio.create_task(asyncio.sleep(3600))

        await coordinator.async_stop_log_listener()

        self.assertEqual(api.unsubscribed, [287363148])
        self.assertIsNone(coordinator._log_subscription_id)
        self.assertIsNone(coordinator._log_listener_task)


class ExtractCallPeerTests(unittest.TestCase):
    """Tests for _extract_called_peer static method."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator_module = load_coordinator_module()

    def test_no_sessions(self) -> None:
        result = self.coordinator_module.TwoNIntercomCoordinator._extract_called_peer(
            {"sessions": []}
        )
        self.assertIsNone(result)

    def test_sessions_none(self) -> None:
        result = self.coordinator_module.TwoNIntercomCoordinator._extract_called_peer({})
        self.assertIsNone(result)

    def test_no_calls(self) -> None:
        result = self.coordinator_module.TwoNIntercomCoordinator._extract_called_peer(
            {"sessions": [{"calls": []}]}
        )
        self.assertIsNone(result)

    def test_calls_none(self) -> None:
        result = self.coordinator_module.TwoNIntercomCoordinator._extract_called_peer(
            {"sessions": [{}]}
        )
        self.assertIsNone(result)

    def test_extracts_peer(self) -> None:
        result = self.coordinator_module.TwoNIntercomCoordinator._extract_called_peer(
            {"sessions": [{"calls": [{"peer": "sip:100@device"}]}]}
        )
        self.assertEqual(result, "sip:100@device")


class ExtractCallStateTests(unittest.TestCase):
    """Tests for _extract_call_state static method."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator_module = load_coordinator_module()

    def test_top_level_state(self) -> None:
        result = self.coordinator_module.TwoNIntercomCoordinator._extract_call_state(
            {"state": "ringing"}
        )
        self.assertEqual(result, "ringing")

    def test_session_level_state(self) -> None:
        result = self.coordinator_module.TwoNIntercomCoordinator._extract_call_state(
            {"sessions": [{"state": "incoming"}]}
        )
        self.assertEqual(result, "incoming")

    def test_call_level_state(self) -> None:
        result = self.coordinator_module.TwoNIntercomCoordinator._extract_call_state(
            {"sessions": [{"calls": [{"state": "active"}]}]}
        )
        self.assertEqual(result, "active")

    def test_call_level_status(self) -> None:
        result = self.coordinator_module.TwoNIntercomCoordinator._extract_call_state(
            {"sessions": [{"calls": [{"status": "connected"}]}]}
        )
        self.assertEqual(result, "connected")

    def test_call_level_callState(self) -> None:
        result = self.coordinator_module.TwoNIntercomCoordinator._extract_call_state(
            {"sessions": [{"calls": [{"callState": "alerting"}]}]}
        )
        self.assertEqual(result, "alerting")

    def test_no_state_anywhere(self) -> None:
        result = self.coordinator_module.TwoNIntercomCoordinator._extract_call_state(
            {"sessions": [{"calls": [{}]}]}
        )
        self.assertIsNone(result)

    def test_empty_sessions(self) -> None:
        result = self.coordinator_module.TwoNIntercomCoordinator._extract_call_state(
            {"sessions": []}
        )
        self.assertIsNone(result)


class ExtractActiveSessionIdTests(unittest.TestCase):
    """Tests for _extract_active_session_id static method."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator_module = load_coordinator_module()

    def _extract(self, call_status):
        return self.coordinator_module.TwoNIntercomCoordinator._extract_active_session_id(
            call_status
        )

    def test_not_a_dict(self) -> None:
        self.assertIsNone(self._extract("bad"))
        self.assertIsNone(self._extract(None))

    def test_session_not_dict(self) -> None:
        self.assertIsNone(self._extract({"sessions": ["bad"]}))

    def test_session_no_candidate(self) -> None:
        self.assertIsNone(self._extract({"sessions": [{"state": "ringing"}]}))

    def test_session_empty_candidate(self) -> None:
        self.assertIsNone(
            self._extract({"sessions": [{"session": "  ", "state": "ringing"}]})
        )

    def test_session_inactive_state(self) -> None:
        self.assertIsNone(
            self._extract({"sessions": [{"session": "s1", "state": "idle"}]})
        )

    def test_top_level_active_with_session(self) -> None:
        result = self._extract({"state": "active", "session": "top-1"})
        self.assertEqual(result, "top-1")

    def test_top_level_active_no_session(self) -> None:
        self.assertIsNone(self._extract({"state": "active"}))

    def test_top_level_active_empty_session(self) -> None:
        self.assertIsNone(self._extract({"state": "active", "session": "  "}))


class ExtractFirstNonemptyStringTests(unittest.TestCase):
    """Tests for _extract_first_nonempty_string static method."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator_module = load_coordinator_module()

    def _extract(self, params, *keys):
        return self.coordinator_module.TwoNIntercomCoordinator._extract_first_nonempty_string(
            params, *keys
        )

    def test_first_key_present(self) -> None:
        self.assertEqual(self._extract({"a": "val"}, "a", "b"), "val")

    def test_falls_through_to_second(self) -> None:
        self.assertEqual(self._extract({"b": "val"}, "a", "b"), "val")

    def test_skips_none(self) -> None:
        self.assertEqual(self._extract({"a": None, "b": "x"}, "a", "b"), "x")

    def test_skips_empty_string(self) -> None:
        self.assertEqual(self._extract({"a": "  ", "b": "x"}, "a", "b"), "x")

    def test_all_missing(self) -> None:
        self.assertIsNone(self._extract({}, "a", "b"))

    def test_converts_int(self) -> None:
        self.assertEqual(self._extract({"a": 42}, "a"), "42")


class ProcessLogEventEdgeCaseTests(unittest.IsolatedAsyncioTestCase):
    """Tests for _process_log_event edge cases."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator_module = load_coordinator_module()

    def _make_coordinator(self, **kwargs):
        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()
        return self.coordinator_module.TwoNIntercomCoordinator(hass, api, **kwargs)

    def test_non_dict_event_returns_false(self) -> None:
        c = self._make_coordinator()
        self.assertFalse(c._process_log_event("not a dict"))

    def test_unsupported_event_name(self) -> None:
        c = self._make_coordinator()
        self.assertFalse(
            c._process_log_event({"event": "DoorOpened", "params": {"state": "open"}})
        )

    def test_params_not_dict(self) -> None:
        c = self._make_coordinator()
        self.assertFalse(
            c._process_log_event({"event": "CallStateChanged", "params": "bad"})
        )

    def test_no_state_in_params(self) -> None:
        c = self._make_coordinator()
        self.assertFalse(
            c._process_log_event({"event": "CallStateChanged", "params": {"peer": "a"}})
        )

    def test_empty_state_string(self) -> None:
        c = self._make_coordinator()
        self.assertFalse(
            c._process_log_event(
                {"event": "CallStateChanged", "params": {"state": "  "}}
            )
        )

    def test_outgoing_ring_does_not_trigger(self) -> None:
        c = self._make_coordinator()
        c.data = self.coordinator_module.TwoNIntercomData(
            call_status={}, last_ring_time=None, caller_info=None,
            active_session_id=None, available=True, phone_status={},
            switch_caps={}, switch_status={}, io_caps={}, io_status={},
        )
        c._process_log_event({
            "event": "CallStateChanged",
            "params": {"state": "ringing", "direction": "outgoing", "session": "s1"},
        })
        self.assertFalse(c._ring_detected)

    def test_ring_filter_blocks_non_matching_peer(self) -> None:
        c = self._make_coordinator(called_id="sip:200@device")
        c.data = self.coordinator_module.TwoNIntercomData(
            call_status={}, last_ring_time=None, caller_info=None,
            active_session_id=None, available=True, phone_status={},
            switch_caps={}, switch_status={}, io_caps={}, io_status={},
        )
        c._process_log_event({
            "event": "CallStateChanged",
            "params": {"state": "ringing", "direction": "incoming",
                       "peer": "sip:100@device", "session": "s1"},
        })
        self.assertFalse(c._ring_detected)

    def test_terminated_clears_session_when_no_session_id(self) -> None:
        c = self._make_coordinator()
        c._active_session_id = "s1"
        c._process_log_event({
            "event": "CallStateChanged",
            "params": {"state": "terminated"},
        })
        self.assertIsNone(c._active_session_id)

    def test_terminated_does_not_clear_different_session(self) -> None:
        c = self._make_coordinator()
        c._active_session_id = "s1"
        c._process_log_event({
            "event": "CallStateChanged",
            "params": {"state": "terminated", "session": "s2"},
        })
        # Different session ID → don't clear
        self.assertEqual(c._active_session_id, "s1")

    # --- Motion detection event tests ---

    def test_motion_detected_in_event(self) -> None:
        c = self._make_coordinator()
        self.assertFalse(c._motion_detected)
        result = c._process_log_event({
            "event": "MotionDetected",
            "params": {"state": "in"},
        })
        self.assertTrue(result)
        self.assertTrue(c._motion_detected)
        self.assertIsNotNone(c._last_motion_time)

    def test_motion_detected_out_event(self) -> None:
        c = self._make_coordinator()
        c._motion_detected = True
        result = c._process_log_event({
            "event": "MotionDetected",
            "params": {"state": "out"},
        })
        self.assertTrue(result)
        self.assertFalse(c._motion_detected)

    def test_motion_detected_unknown_state(self) -> None:
        c = self._make_coordinator()
        result = c._process_log_event({
            "event": "MotionDetected",
            "params": {"state": "unknown"},
        })
        self.assertFalse(result)
        self.assertFalse(c._motion_detected)

    def test_motion_detected_no_params(self) -> None:
        c = self._make_coordinator()
        result = c._process_log_event({
            "event": "MotionDetected",
        })
        self.assertFalse(result)

    def test_motion_detected_params_not_dict(self) -> None:
        c = self._make_coordinator()
        result = c._process_log_event({
            "event": "MotionDetected",
            "params": "bad",
        })
        self.assertFalse(result)

    def test_motion_detection_available_property(self) -> None:
        c = self._make_coordinator()
        c._system_caps = {"motionDetection": "active,licensed"}
        self.assertTrue(c.motion_detection_available)

    def test_motion_detection_not_available_when_inactive(self) -> None:
        c = self._make_coordinator()
        c._system_caps = {"motionDetection": "inactive,licensed"}
        self.assertFalse(c.motion_detection_available)

    def test_motion_detection_not_available_when_missing(self) -> None:
        c = self._make_coordinator()
        c._system_caps = {}
        self.assertFalse(c.motion_detection_available)

    # --- RTSP server capability tests ---

    def test_rtsp_server_available_when_active(self) -> None:
        c = self._make_coordinator()
        c._system_caps = {"rtspServer": "active,licensed"}
        self.assertTrue(c.rtsp_server_available)

    def test_rtsp_server_not_available_when_inactive(self) -> None:
        c = self._make_coordinator()
        c._system_caps = {"rtspServer": "inactive,licensed"}
        self.assertFalse(c.rtsp_server_available)

    def test_rtsp_server_not_available_when_missing(self) -> None:
        c = self._make_coordinator()
        c._system_caps = {}
        self.assertFalse(c.rtsp_server_available)

    def test_camera_transport_overrides_includes_rtsp_capable_true(self) -> None:
        c = self._make_coordinator()
        c._system_caps = {"rtspServer": "active,licensed"}
        overrides = c._camera_transport_overrides()
        self.assertTrue(overrides["rtsp_capable"])

    def test_camera_transport_overrides_includes_rtsp_capable_false(self) -> None:
        c = self._make_coordinator()
        c._system_caps = {"rtspServer": "inactive,licensed"}
        overrides = c._camera_transport_overrides()
        self.assertFalse(overrides["rtsp_capable"])

    def test_camera_transport_overrides_omits_rtsp_capable_without_caps(self) -> None:
        c = self._make_coordinator()
        c._system_caps = {}
        overrides = c._camera_transport_overrides()
        self.assertNotIn("rtsp_capable", overrides)


class LogListenerTests(unittest.IsolatedAsyncioTestCase):
    """Tests for log subscription lifecycle."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator_module = load_coordinator_module()

    async def test_run_log_subscription_processes_events(self) -> None:
        events_pulled = []

        class FakeAPI:
            def __init__(self):
                self.pull_count = 0

            async def async_pull_log(self, sub_id, timeout=1):
                self.pull_count += 1
                if self.pull_count == 1:
                    return [
                        {
                            "event": "CallStateChanged",
                            "params": {"state": "ringing", "session": "s1",
                                       "direction": "incoming"},
                        }
                    ]
                raise RuntimeError("done")

        hass = types.SimpleNamespace()
        api = FakeAPI()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c.data = self.coordinator_module.TwoNIntercomData(
            call_status={}, last_ring_time=None, caller_info=None,
            active_session_id=None, available=True, phone_status={},
            switch_caps={}, switch_status={}, io_caps={}, io_status={},
        )

        with self.assertRaises(RuntimeError):
            await c._async_run_log_subscription(42)

        self.assertTrue(c._ring_detected)

    async def test_log_listener_loop_resubscribes_on_failure(self) -> None:
        class FakeAPI:
            def __init__(self):
                self.subscribe_count = 0
                self.unsubscribed = []

            async def async_subscribe_log(self, events):
                self.subscribe_count += 1
                if self.subscribe_count == 1:
                    return None  # first attempt fails → backoff+retry
                if self.subscribe_count == 2:
                    return 99  # second attempt succeeds
                return None

            async def async_pull_log(self, sub_id, timeout=1):
                raise RuntimeError("stop")

            async def async_unsubscribe_log(self, sub_id):
                self.unsubscribed.append(sub_id)

        hass = types.SimpleNamespace()
        api = FakeAPI()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)

        # Patch the backoff constants to speed up the test
        coord_mod = sys.modules["custom_components.2n_intercom.coordinator"]
        orig_initial = coord_mod.LOG_LISTENER_INITIAL_BACKOFF
        coord_mod.LOG_LISTENER_INITIAL_BACKOFF = 0.01

        try:
            async def stop_after_delay():
                await asyncio.sleep(0.15)
                c._log_listener_stopped = True

            task = asyncio.create_task(c._async_log_listener_loop())
            stopper = asyncio.create_task(stop_after_delay())
            await asyncio.gather(task, stopper, return_exceptions=True)

            self.assertGreaterEqual(api.subscribe_count, 2)
        finally:
            coord_mod.LOG_LISTENER_INITIAL_BACKOFF = orig_initial

    async def test_log_listener_loop_subscribe_exception(self) -> None:
        class FakeAPI:
            def __init__(self):
                self.subscribe_count = 0

            async def async_subscribe_log(self, events):
                self.subscribe_count += 1
                if self.subscribe_count <= 1:
                    raise RuntimeError("subscribe failed")
                return 99

            async def async_pull_log(self, sub_id, timeout=1):
                raise RuntimeError("stop")

            async def async_unsubscribe_log(self, sub_id):
                pass

        hass = types.SimpleNamespace()
        api = FakeAPI()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)

        async def stop_after_delay():
            await asyncio.sleep(0.1)
            c._log_listener_stopped = True

        task = asyncio.create_task(c._async_log_listener_loop())
        stopper = asyncio.create_task(stop_after_delay())
        await asyncio.gather(task, stopper, return_exceptions=True)

        self.assertGreaterEqual(api.subscribe_count, 1)

    async def test_start_log_listener_noop_when_running(self) -> None:
        hass = types.SimpleNamespace(async_create_task=asyncio.create_task)
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c._log_listener_task = asyncio.create_task(asyncio.sleep(3600))

        await c.async_start_log_listener()
        # Should not replace the existing task
        self.assertIsNotNone(c._log_listener_task)

        c._log_listener_task.cancel()
        try:
            await c._log_listener_task
        except asyncio.CancelledError:
            pass

    async def test_stop_log_listener_handles_unsubscribe_failure(self) -> None:
        class FakeAPI:
            async def async_unsubscribe_log(self, sub_id):
                raise RuntimeError("unsubscribe failed")

        hass = types.SimpleNamespace(async_create_task=asyncio.create_task)
        api = FakeAPI()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c._log_subscription_id = 123
        c._log_listener_task = asyncio.create_task(asyncio.sleep(3600))

        await c.async_stop_log_listener()
        # Should not raise; clears state despite failure
        self.assertIsNone(c._log_subscription_id)


class RefreshSecondaryCacheTests(unittest.IsolatedAsyncioTestCase):
    """Tests for _refresh_secondary_cache."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator_module = load_coordinator_module()

    async def test_missing_api_method_uses_cached(self) -> None:
        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()  # no methods
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c._phone_status = {"cached": True}

        result = await c._refresh_secondary_cache(
            "_phone_status", "async_get_phone_status", "phone status"
        )
        self.assertEqual(result, {"cached": True})

    async def test_missing_api_method_no_cache(self) -> None:
        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)

        result = await c._refresh_secondary_cache(
            "_phone_status", "async_get_phone_status", "phone status"
        )
        self.assertEqual(result, {})

    async def test_warning_log_level(self) -> None:
        class FakeAPI:
            async def async_get_switch_caps(self):
                raise RuntimeError("fail")

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())
        c._switch_caps = {"cached": True}

        result = await c._refresh_secondary_cache(
            "_switch_caps", "async_get_switch_caps", "switch caps",
            log_level="warning",
        )
        self.assertEqual(result, {"cached": True})


class InitializeStaticCachesTests(unittest.IsolatedAsyncioTestCase):
    """Tests for async_initialize_static_caches."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator_module = load_coordinator_module()

    async def test_system_info_failure_sets_empty(self) -> None:
        class FakeAPI:
            async def async_get_system_info(self):
                raise RuntimeError("unreachable")

            async def async_get_switch_caps(self):
                return {}

            async def async_get_io_caps(self):
                return {}

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())

        await c.async_initialize_static_caches()
        self.assertEqual(c._system_info, {})

    async def test_camera_transport_resolved(self) -> None:
        from dataclasses import dataclass

        @dataclass
        class FakeTransport:
            source: str = "internal"

        class FakeAPI:
            camera_transport_info = FakeTransport()

            async def async_get_system_info(self):
                return {"model": "2N"}

            async def async_get_switch_caps(self):
                return {}

            async def async_get_io_caps(self):
                return {}

            async def async_get_camera_transport_info(self, **kwargs):
                return FakeTransport(source=kwargs.get("camera_source", "internal"))

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())

        await c.async_initialize_static_caches()
        self.assertIsNotNone(c._camera_transport_info)

    async def test_camera_transport_failure_fallback(self) -> None:
        from dataclasses import dataclass

        @dataclass
        class FakeTransport:
            source: str = "internal"

        class FakeAPI:
            camera_transport_info = FakeTransport()

            async def async_get_system_info(self):
                return {"model": "2N"}

            async def async_get_switch_caps(self):
                return {}

            async def async_get_io_caps(self):
                return {}

            async def async_get_camera_transport_info(self, **kwargs):
                raise RuntimeError("camera fail")

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())

        await c.async_initialize_static_caches()
        self.assertEqual(c._camera_transport_info, FakeTransport())

    async def test_camera_transport_no_api_method(self) -> None:
        class FakeAPI:
            async def async_get_system_info(self):
                return {"model": "2N"}

            async def async_get_switch_caps(self):
                return {}

            async def async_get_io_caps(self):
                return {}

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())

        await c.async_initialize_static_caches()
        self.assertIsNone(c._camera_transport_info)


class CameraTransportOverridesTests(unittest.TestCase):
    """Tests for _camera_transport_overrides."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator_module = load_coordinator_module()

    def test_defaults_when_no_config_entry(self) -> None:
        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c.config_entry = None

        overrides = c._camera_transport_overrides()
        self.assertIn("requested_mode", overrides)

    def test_reads_options_from_config_entry(self) -> None:
        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c.config_entry = types.SimpleNamespace(
            options={
                "live_view_mode": "mjpeg",
                "mjpeg_width": 640,
                "mjpeg_height": 480,
                "mjpeg_fps": 5,
                "camera_source": "external",
            }
        )

        overrides = c._camera_transport_overrides()
        self.assertEqual(overrides["requested_mode"], "mjpeg")
        self.assertEqual(overrides["mjpeg_width"], 640)
        self.assertEqual(overrides["mjpeg_height"], 480)
        self.assertEqual(overrides["mjpeg_fps"], 5)
        self.assertEqual(overrides["camera_source"], "external")

    def test_ignores_invalid_types(self) -> None:
        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c.config_entry = types.SimpleNamespace(
            options={
                "live_view_mode": "",
                "mjpeg_width": "bad",
                "mjpeg_height": -1,
                "mjpeg_fps": 0,
                "camera_source": "invalid_source",
            }
        )

        overrides = c._camera_transport_overrides()
        # All invalid → only defaults
        self.assertNotIn("mjpeg_width", overrides)
        self.assertNotIn("mjpeg_height", overrides)
        self.assertNotIn("mjpeg_fps", overrides)
        self.assertNotIn("camera_source", overrides)


class AsyncUpdateDataErrorTests(unittest.IsolatedAsyncioTestCase):
    """Tests for _async_update_data error handling paths."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator_module = load_coordinator_module()
        cls.UpdateFailed = sys.modules[
            "homeassistant.helpers.update_coordinator"
        ].UpdateFailed
        cls.ConfigEntryNotReady = sys.modules[
            "homeassistant.exceptions"
        ].ConfigEntryNotReady

    def _base_api(self):
        """Return an API with all secondary methods."""

        class FullAPI:
            reset_session_calls = 0

            async def async_get_system_info(self):
                return {"model": "2N"}

            async def async_get_call_status(self):
                return {"state": "idle", "sessions": []}

            async def async_get_phone_status(self):
                return {}

            async def async_get_switch_caps(self):
                return {}

            async def async_get_switch_status(self):
                return {}

            async def async_get_io_caps(self):
                return {}

            async def async_get_io_status(self):
                return {}

            async def async_reset_session(self):
                FullAPI.reset_session_calls += 1

        return FullAPI()

    async def test_single_auth_error_raises_update_failed(self) -> None:
        """A single transient 401 must NOT trip the reauth flow.

        It must also reset the HTTP session so the next poll rebuilds the
        DigestAuthMiddleware from scratch (deterministic recovery from a
        stale nonce, rather than relying on the middleware to renegotiate).
        """
        api_module = sys.modules["custom_components.2n_intercom.api"]
        api = self._base_api()
        api.async_get_call_status = lambda self=None: (_ for _ in ()).throw(
            api_module.TwoNAuthenticationError("bad creds")
        )

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)

        with self.assertRaises(self.UpdateFailed) as ctx:
            await c._async_update_data()
        self.assertIn("Authentication error", str(ctx.exception))
        self.assertEqual(c._auth_error_count, 1)
        self.assertEqual(type(api).reset_session_calls, 1)

    async def test_consecutive_auth_errors_raise_config_entry_auth_failed(self) -> None:
        """After NUM_AUTH_ERRORS consecutive 401s, the reauth flow triggers."""
        api_module = sys.modules["custom_components.2n_intercom.api"]
        api = self._base_api()
        api.async_get_call_status = lambda self=None: (_ for _ in ()).throw(
            api_module.TwoNAuthenticationError("bad creds")
        )

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)

        threshold = self.coordinator_module.NUM_AUTH_ERRORS
        for _ in range(threshold - 1):
            with self.assertRaises(self.UpdateFailed):
                await c._async_update_data()

        with self.assertRaises(Exception) as ctx:
            await c._async_update_data()
        # Should be ConfigEntryAuthFailed (or its fallback)
        self.assertIn("Authentication failed", str(ctx.exception))
        self.assertEqual(c._auth_error_count, threshold)

    async def test_auth_error_count_resets_on_success(self) -> None:
        """A successful poll between auth errors resets the counter."""
        api_module = sys.modules["custom_components.2n_intercom.api"]
        api = self._base_api()

        fail = True

        async def maybe_fail_call():
            if fail:
                raise api_module.TwoNAuthenticationError("bad creds")
            return {"state": "idle", "sessions": []}

        api.async_get_call_status = maybe_fail_call

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)

        with self.assertRaises(self.UpdateFailed):
            await c._async_update_data()
        self.assertEqual(c._auth_error_count, 1)

        fail = False
        await c._async_update_data()
        self.assertEqual(c._auth_error_count, 0)

    async def test_connection_error_raises_update_failed(self) -> None:
        api_module = sys.modules["custom_components.2n_intercom.api"]
        api = self._base_api()

        async def fail_call():
            raise api_module.TwoNConnectionError("timeout")

        api.async_get_call_status = fail_call

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)

        with self.assertRaises(self.UpdateFailed):
            await c._async_update_data()
        self.assertEqual(c._retry_count, 1)

    async def test_max_retries_raises_config_entry_not_ready(self) -> None:
        api_module = sys.modules["custom_components.2n_intercom.api"]
        api = self._base_api()

        async def fail_call():
            raise api_module.TwoNConnectionError("timeout")

        api.async_get_call_status = fail_call

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c._retry_count = self.coordinator_module.MAX_RETRIES  # already at max

        with self.assertRaises(self.ConfigEntryNotReady):
            await c._async_update_data()

    async def test_generic_error_raises_update_failed(self) -> None:
        api = self._base_api()

        async def fail_call():
            raise ValueError("unexpected")

        api.async_get_call_status = fail_call

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)

        with self.assertRaises(self.UpdateFailed):
            await c._async_update_data()

    async def test_system_info_fallback_in_update_data(self) -> None:
        api = self._base_api()

        async def fail_info():
            raise RuntimeError("info fail")

        api.async_get_system_info = fail_info

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        # _system_info is None → triggers fallback
        data = await c._async_update_data()
        self.assertEqual(c._system_info, {})

    async def test_poll_captures_baseline_state(self) -> None:
        """Polling captures session id, peer, and call state baseline."""
        api = self._base_api()

        async def ringing_call():
            return {
                "state": "ringing",
                "sessions": [
                    {"session": "s1", "state": "ringing",
                     "calls": [{"peer": "sip:100@x"}]}
                ],
            }

        api.async_get_call_status = ringing_call

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)

        data = await c._async_update_data()
        c.data = data

        # Polling captures baseline state but does NOT do ring detection
        self.assertEqual(c._active_session_id, "s1")
        self.assertEqual(c._last_called_peer, "100")
        self.assertEqual(c._last_call_state_value, "ringing")
        self.assertFalse(c._ring_detected)  # ring detection is event-only

    async def test_poll_does_not_set_ring_detected(self) -> None:
        """Polling never sets _ring_detected; that's event-driven only."""
        call_count = 0
        api = self._base_api()

        async def changing_call():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "state": "ringing",
                    "sessions": [
                        {"session": "s1", "state": "ringing",
                         "calls": [{"peer": "100"}]}
                    ],
                }
            return {"state": "idle", "sessions": []}

        api.async_get_call_status = changing_call

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)

        data1 = await c._async_update_data()
        c.data = data1
        # Polling does not trigger ring detection
        self.assertFalse(c._ring_detected)
        self.assertEqual(c._last_call_state_value, "ringing")

        data2 = await c._async_update_data()
        c.data = data2
        self.assertFalse(c._ring_detected)
        self.assertEqual(c._last_call_state_value, "idle")


class PropertyTests(unittest.IsolatedAsyncioTestCase):
    """Tests for coordinator properties."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator_module = load_coordinator_module()

    def test_ring_active_false_when_no_data(self) -> None:
        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        self.assertFalse(c.ring_active)

    def test_ring_active_false_when_not_detected(self) -> None:
        from datetime import datetime, timedelta

        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c.data = self.coordinator_module.TwoNIntercomData(
            call_status={}, last_ring_time=None, caller_info=None,
            active_session_id=None, available=True, phone_status={},
            switch_caps={}, switch_status={}, io_caps={}, io_status={},
        )
        c._ring_detected = False
        self.assertFalse(c.ring_active)

    def test_ring_active_false_when_pulse_expired(self) -> None:
        from datetime import datetime, timedelta

        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c.data = self.coordinator_module.TwoNIntercomData(
            call_status={}, last_ring_time=None, caller_info=None,
            active_session_id=None, available=True, phone_status={},
            switch_caps={}, switch_status={}, io_caps={}, io_status={},
        )
        c._ring_detected = True
        c._ring_pulse_until = datetime.now() - timedelta(seconds=10)
        self.assertFalse(c.ring_active)

    def test_ring_active_true_within_pulse(self) -> None:
        from datetime import datetime, timedelta

        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c.data = self.coordinator_module.TwoNIntercomData(
            call_status={}, last_ring_time=None, caller_info=None,
            active_session_id=None, available=True, phone_status={},
            switch_caps={}, switch_status={}, io_caps={}, io_status={},
        )
        c._ring_detected = True
        c._ring_pulse_until = datetime.now() + timedelta(seconds=10)
        self.assertTrue(c.ring_active)

    def test_ring_active_false_when_pulse_none(self) -> None:
        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c.data = self.coordinator_module.TwoNIntercomData(
            call_status={}, last_ring_time=None, caller_info=None,
            active_session_id=None, available=True, phone_status={},
            switch_caps={}, switch_status={}, io_caps={}, io_status={},
        )
        c._ring_detected = True
        c._ring_pulse_until = None
        self.assertFalse(c.ring_active)

    def test_last_ring_time(self) -> None:
        from datetime import datetime

        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        self.assertIsNone(c.last_ring_time)
        c._last_ring_time = datetime(2026, 1, 1)
        self.assertEqual(c.last_ring_time, datetime(2026, 1, 1))

    def test_caller_info_with_data(self) -> None:
        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c.data = self.coordinator_module.TwoNIntercomData(
            call_status={}, last_ring_time=None,
            caller_info={"name": "John"},
            active_session_id=None, available=True, phone_status={},
            switch_caps={}, switch_status={}, io_caps={}, io_status={},
        )
        self.assertEqual(c.caller_info, {"name": "John"})

    def test_caller_info_empty(self) -> None:
        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        self.assertEqual(c.caller_info, {})

    def test_system_info_property(self) -> None:
        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        self.assertEqual(c.system_info, {})
        c._system_info = {"model": "Verso"}
        self.assertEqual(c.system_info, {"model": "Verso"})

    def test_camera_transport_info_from_cache(self) -> None:
        from dataclasses import dataclass

        @dataclass
        class FakeTransport:
            source: str = "internal"

        hass = types.SimpleNamespace()
        api = types.SimpleNamespace(camera_transport_info=FakeTransport())
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c._camera_transport_info = FakeTransport(source="external")
        self.assertEqual(c.camera_transport_info.source, "external")

    def test_camera_transport_info_from_api(self) -> None:
        from dataclasses import dataclass

        @dataclass
        class FakeTransport:
            source: str = "internal"

        hass = types.SimpleNamespace()
        api = types.SimpleNamespace(camera_transport_info=FakeTransport())
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        self.assertEqual(c.camera_transport_info.source, "internal")


class DeviceInfoTests(unittest.TestCase):
    """Tests for get_device_info."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator_module = load_coordinator_module()

    def test_basic_device_info(self) -> None:
        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c._system_info = {"variant": "IP Verso", "swVersion": "2.50"}

        info = c.get_device_info("e1", "Front Door")
        self.assertEqual(info["name"], "Front Door")
        self.assertEqual(info["model"], "IP Verso")
        self.assertEqual(info["sw_version"], "2.50")
        self.assertEqual(info["manufacturer"], "2N")

    def test_device_info_with_serial_hw_mac(self) -> None:
        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c._system_info = {
            "variant": "IP Verso",
            "swVersion": "2.50",
            "serialNumber": "SN123",
            "hwVersion": "HW1.0",
            "macAddr": "AA:BB:CC:DD:EE:FF",
        }

        info = c.get_device_info("e1", "Door")
        self.assertEqual(info["serial_number"], "SN123")
        self.assertEqual(info["hw_version"], "HW1.0")
        self.assertIn(("mac", "AA:BB:CC:DD:EE:FF"), info["connections"])

    def test_device_info_falls_back_to_deviceName(self) -> None:
        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c._system_info = {"deviceName": "2N Intercom"}

        info = c.get_device_info("e1", "Door")
        self.assertEqual(info["model"], "2N Intercom")

    def test_device_info_defaults(self) -> None:
        hass = types.SimpleNamespace()
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c._system_info = {}

        info = c.get_device_info("e1", "Door")
        self.assertEqual(info["model"], "IP Intercom")
        self.assertEqual(info["sw_version"], "1.0.0")
        self.assertNotIn("serial_number", info)
        self.assertNotIn("hw_version", info)
        self.assertNotIn("connections", info)


class TriggerRelayTests(unittest.IsolatedAsyncioTestCase):
    """Tests for async_trigger_relay."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator_module = load_coordinator_module()

    async def test_trigger_success(self) -> None:
        class FakeAPI:
            async def async_switch_control(self, relay, action, duration):
                return True

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())
        result = await c.async_trigger_relay(1, 2000)
        self.assertTrue(result)

    async def test_trigger_failure(self) -> None:
        class FakeAPI:
            async def async_switch_control(self, relay, action, duration):
                return False

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())
        result = await c.async_trigger_relay(1)
        self.assertFalse(result)

    async def test_trigger_exception(self) -> None:
        class FakeAPI:
            async def async_switch_control(self, relay, action, duration):
                raise RuntimeError("relay error")

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())
        result = await c.async_trigger_relay(1)
        self.assertFalse(result)


class SnapshotTests(unittest.IsolatedAsyncioTestCase):
    """Tests for async_get_snapshot."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator_module = load_coordinator_module()

    async def test_snapshot_returns_bytes(self) -> None:
        class FakeAPI:
            async def async_get_snapshot(self, width=None, height=None, source=None):
                return b"\xff\xd8\xff"

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())
        result = await c.async_get_snapshot(640, 480)
        self.assertEqual(result, b"\xff\xd8\xff")

    async def test_snapshot_cache(self) -> None:
        call_count = 0

        class FakeAPI:
            async def async_get_snapshot(self, width=None, height=None, source=None):
                nonlocal call_count
                call_count += 1
                return b"\xff\xd8\xff"

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())

        r1 = await c.async_get_snapshot(640, 480)
        r2 = await c.async_get_snapshot(640, 480)
        self.assertEqual(call_count, 1)  # second hit cache
        self.assertEqual(r1, r2)

    async def test_snapshot_cache_miss_on_different_size(self) -> None:
        call_count = 0

        class FakeAPI:
            async def async_get_snapshot(self, width=None, height=None, source=None):
                nonlocal call_count
                call_count += 1
                return b"\xff\xd8\xff"

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())

        await c.async_get_snapshot(640, 480)
        await c.async_get_snapshot(320, 240)
        self.assertEqual(call_count, 2)

    async def test_snapshot_returns_none_on_error(self) -> None:
        class FakeAPI:
            async def async_get_snapshot(self, width=None, height=None, source=None):
                raise RuntimeError("camera error")

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())
        result = await c.async_get_snapshot()
        self.assertIsNone(result)

    async def test_snapshot_returns_none_when_empty(self) -> None:
        class FakeAPI:
            async def async_get_snapshot(self, width=None, height=None, source=None):
                return None

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())
        result = await c.async_get_snapshot()
        self.assertIsNone(result)

    async def test_snapshot_passes_camera_source(self) -> None:
        from dataclasses import dataclass

        @dataclass
        class FakeTransport:
            source: str = "external"

        captured = {}

        class FakeAPI:
            async def async_get_snapshot(self, width=None, height=None, source=None):
                captured["source"] = source
                return b"\xff"

        hass = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, FakeAPI())
        c._camera_transport_info = FakeTransport(source="external")

        await c.async_get_snapshot()
        self.assertEqual(captured["source"], "external")


class NormalizePeerTests(unittest.TestCase):
    """Tests for _normalize_peer."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator_module = load_coordinator_module()

    def _normalize(self, peer):
        return self.coordinator_module.TwoNIntercomCoordinator._normalize_peer(peer)

    def test_none(self) -> None:
        self.assertIsNone(self._normalize(None))

    def test_empty(self) -> None:
        self.assertIsNone(self._normalize(""))

    def test_all_calls(self) -> None:
        self.assertIsNone(self._normalize("__all__"))

    def test_sip_uri(self) -> None:
        self.assertEqual(self._normalize("sip:100@device"), "100")

    def test_plain_number(self) -> None:
        self.assertEqual(self._normalize("100"), "100")

    def test_whitespace_only(self) -> None:
        self.assertIsNone(self._normalize("   "))


class EventDrivenHandlerTests(unittest.IsolatedAsyncioTestCase):
    """Tests for event-driven state handlers (SwitchStateChanged, etc.)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.coordinator_module = load_coordinator_module()

    def _make_coordinator(self, **kwargs):
        refresh_calls = []

        async def fake_request_refresh():
            refresh_calls.append(True)

        hass = types.SimpleNamespace(
            async_create_task=lambda coro: asyncio.ensure_future(coro),
        )
        api = types.SimpleNamespace()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api, **kwargs)
        c.async_request_refresh = fake_request_refresh
        c._refresh_calls = refresh_calls
        return c

    # --- SwitchStateChanged ---

    def test_process_switch_state_event(self) -> None:
        c = self._make_coordinator()
        c._switch_status = {
            "switches": [
                {"switch": 1, "active": False},
                {"switch": 2, "active": False},
            ]
        }
        result = c._process_switch_state_event({"switch": 1, "state": True})
        self.assertTrue(result)
        self.assertTrue(c._switch_status["switches"][0]["active"])
        self.assertFalse(c._switch_status["switches"][1]["active"])

    def test_process_switch_state_event_no_baseline(self) -> None:
        c = self._make_coordinator()
        c._switch_status = None
        result = c._process_switch_state_event({"switch": 1, "state": True})
        self.assertFalse(result)

    def test_process_switch_state_event_bad_params(self) -> None:
        c = self._make_coordinator()
        c._switch_status = {"switches": [{"switch": 1, "active": False}]}
        self.assertFalse(c._process_switch_state_event({"switch": "bad", "state": True}))
        self.assertFalse(c._process_switch_state_event({"switch": 1, "state": "yes"}))
        self.assertFalse(c._process_switch_state_event("not a dict"))

    def test_process_switch_state_event_unknown_switch(self) -> None:
        c = self._make_coordinator()
        c._switch_status = {"switches": [{"switch": 1, "active": False}]}
        result = c._process_switch_state_event({"switch": 99, "state": True})
        self.assertFalse(result)

    # --- InputChanged ---

    def test_process_input_changed_event(self) -> None:
        c = self._make_coordinator()
        c._io_status = {
            "ports": [
                {"port": "input1", "state": False},
                {"port": "input2", "state": False},
            ]
        }
        result = c._process_input_changed_event({"port": "input1", "state": True})
        self.assertTrue(result)
        self.assertTrue(c._io_status["ports"][0]["state"])
        self.assertFalse(c._io_status["ports"][1]["state"])

    def test_process_input_changed_event_no_baseline(self) -> None:
        c = self._make_coordinator()
        c._io_status = None
        result = c._process_input_changed_event({"port": "input1", "state": True})
        self.assertFalse(result)

    # --- OutputChanged ---

    def test_process_output_changed_event(self) -> None:
        c = self._make_coordinator()
        c._io_status = {
            "ports": [
                {"port": "relay1", "state": False},
            ]
        }
        result = c._process_output_changed_event({"port": "relay1", "state": True})
        self.assertTrue(result)
        self.assertTrue(c._io_status["ports"][0]["state"])

    def test_process_output_changed_event_no_baseline(self) -> None:
        c = self._make_coordinator()
        c._io_status = None
        result = c._process_output_changed_event({"port": "relay1", "state": True})
        self.assertFalse(result)

    # --- RegistrationStateChanged ---

    def test_process_registration_event(self) -> None:
        c = self._make_coordinator()
        c._phone_status = {
            "accounts": [
                {"sipAccount": 1, "state": "registered"},
                {"sipAccount": 2, "state": "registered"},
            ]
        }
        result = c._process_registration_event({"sipAccount": 1, "state": "unregistered"})
        self.assertTrue(result)
        self.assertEqual(c._phone_status["accounts"][0]["state"], "unregistered")
        self.assertEqual(c._phone_status["accounts"][1]["state"], "registered")

    def test_process_registration_event_no_baseline(self) -> None:
        c = self._make_coordinator()
        c._phone_status = None
        result = c._process_registration_event({"sipAccount": 1, "state": "unregistered"})
        self.assertFalse(result)

    def test_process_registration_event_bad_params(self) -> None:
        c = self._make_coordinator()
        c._phone_status = {"accounts": [{"sipAccount": 1, "state": "registered"}]}
        self.assertFalse(c._process_registration_event({"sipAccount": 1, "state": 42}))
        self.assertFalse(c._process_registration_event({"state": "registered"}))

    # --- ConfigurationChanged / CapabilitiesChanged ---

    async def test_process_config_changed_event(self) -> None:
        caps_refreshed = []

        async def fake_refresh(cache_attr, method_name, label, **kw):
            caps_refreshed.append(cache_attr)
            return {}

        c = self._make_coordinator()
        c._refresh_secondary_cache = fake_refresh
        result = c._process_config_changed_event()
        self.assertFalse(result)  # returns False (async task handles it)
        # Let the scheduled task run
        await asyncio.sleep(0.05)
        self.assertIn("_switch_caps", caps_refreshed)
        self.assertIn("_io_caps", caps_refreshed)

    # --- DeviceState ---

    async def test_process_device_state_startup(self) -> None:
        c = self._make_coordinator()
        result = c._process_device_state_event({"state": "startup"})
        self.assertFalse(result)
        # Let the scheduled refresh task run
        await asyncio.sleep(0.05)
        self.assertTrue(len(c._refresh_calls) > 0)

    def test_process_device_state_non_startup(self) -> None:
        c = self._make_coordinator()
        result = c._process_device_state_event({"state": "running"})
        self.assertFalse(result)

    def test_process_device_state_bad_params(self) -> None:
        c = self._make_coordinator()
        result = c._process_device_state_event("not a dict")
        self.assertFalse(result)

    # --- Event dispatch via _process_log_event ---

    def test_dispatch_switch_state_changed(self) -> None:
        c = self._make_coordinator()
        c._switch_status = {"switches": [{"switch": 1, "active": False}]}
        result = c._process_log_event({
            "event": "SwitchStateChanged",
            "params": {"switch": 1, "state": True},
        })
        self.assertTrue(result)
        self.assertTrue(c._switch_status["switches"][0]["active"])

    def test_dispatch_input_changed(self) -> None:
        c = self._make_coordinator()
        c._io_status = {"ports": [{"port": "input1", "state": False}]}
        result = c._process_log_event({
            "event": "InputChanged",
            "params": {"port": "input1", "state": True},
        })
        self.assertTrue(result)

    def test_dispatch_output_changed(self) -> None:
        c = self._make_coordinator()
        c._io_status = {"ports": [{"port": "relay1", "state": False}]}
        result = c._process_log_event({
            "event": "OutputChanged",
            "params": {"port": "relay1", "state": True},
        })
        self.assertTrue(result)

    def test_dispatch_registration_state_changed(self) -> None:
        c = self._make_coordinator()
        c._phone_status = {"accounts": [{"sipAccount": 1, "state": "registered"}]}
        result = c._process_log_event({
            "event": "RegistrationStateChanged",
            "params": {"sipAccount": 1, "state": "unregistered"},
        })
        self.assertTrue(result)

    # --- Subscription filter completeness ---

    async def test_log_listener_subscribes_all_events(self) -> None:
        subscribed_events = []

        class FakeAPI:
            async def async_subscribe_log(self, events):
                subscribed_events.extend(events)
                return 1

            async def async_pull_log(self, sub_id, timeout=1):
                raise RuntimeError("stop")

            async def async_unsubscribe_log(self, sub_id):
                pass

        hass = types.SimpleNamespace(
            async_create_task=lambda coro: asyncio.ensure_future(coro),
        )
        api = FakeAPI()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c._system_caps = {"motionDetection": "active,licensed"}

        async def stop_soon():
            await asyncio.sleep(0.05)
            c._log_listener_stopped = True

        task = asyncio.create_task(c._async_log_listener_loop())
        stopper = asyncio.create_task(stop_soon())
        await asyncio.gather(task, stopper, return_exceptions=True)

        expected = {
            "CallStateChanged",
            "CallSessionStateChanged",
            "SwitchStateChanged",
            "InputChanged",
            "OutputChanged",
            "RegistrationStateChanged",
            "ConfigurationChanged",
            "CapabilitiesChanged",
            "DeviceState",
            "MotionDetected",
        }
        self.assertEqual(set(subscribed_events), expected)

    # --- Reconnect triggers baseline refresh ---

    async def test_reconnect_triggers_baseline_refresh(self) -> None:
        refresh_calls = []

        class FakeAPI:
            def __init__(self):
                self.sub_count = 0

            async def async_subscribe_log(self, events):
                self.sub_count += 1
                return self.sub_count

            async def async_pull_log(self, sub_id, timeout=1):
                raise RuntimeError("stop pull")

            async def async_unsubscribe_log(self, sub_id):
                pass

        async def fake_refresh():
            refresh_calls.append(True)

        hass = types.SimpleNamespace(
            async_create_task=lambda coro: asyncio.ensure_future(coro),
        )
        api = FakeAPI()
        c = self.coordinator_module.TwoNIntercomCoordinator(hass, api)
        c.async_request_refresh = fake_refresh

        coord_mod = sys.modules["custom_components.2n_intercom.coordinator"]
        orig_initial = coord_mod.LOG_LISTENER_INITIAL_BACKOFF
        coord_mod.LOG_LISTENER_INITIAL_BACKOFF = 0.01

        try:
            async def stop_soon():
                await asyncio.sleep(0.1)
                c._log_listener_stopped = True

            task = asyncio.create_task(c._async_log_listener_loop())
            stopper = asyncio.create_task(stop_soon())
            await asyncio.gather(task, stopper, return_exceptions=True)

            # Should have called refresh at least once on subscription establishment
            self.assertGreater(len(refresh_calls), 0)
        finally:
            coord_mod.LOG_LISTENER_INITIAL_BACKOFF = orig_initial

    # --- Data rebuild from caches on event ---

    async def test_event_rebuilds_data_from_caches(self) -> None:
        c = self._make_coordinator()
        # Seed initial data
        c.data = self.coordinator_module.TwoNIntercomData(
            call_status={"state": "idle"},
            last_ring_time=None,
            caller_info=None,
            active_session_id=None,
            available=True,
            phone_status={"accounts": [{"sipAccount": 1, "state": "registered"}]},
            switch_caps={"switches": [{"switch": 1, "enabled": True}]},
            switch_status={"switches": [{"switch": 1, "active": False}]},
            io_caps={},
            io_status={"ports": [{"port": "relay1", "state": False}]},
        )
        # Seed caches
        c._phone_status = {"accounts": [{"sipAccount": 1, "state": "registered"}]}
        c._switch_caps = {"switches": [{"switch": 1, "enabled": True}]}
        c._switch_status = {"switches": [{"switch": 1, "active": False}]}
        c._io_caps = {}
        c._io_status = {"ports": [{"port": "relay1", "state": False}]}

        # Simulate pull loop processing a SwitchStateChanged event
        events = [{
            "event": "SwitchStateChanged",
            "params": {"switch": 1, "state": True},
        }]

        # Simulate _async_run_log_subscription logic
        updated = False
        for event in events:
            updated = c._process_log_event(event) or updated

        self.assertTrue(updated)

        # Rebuild data (mimicking centralized rebuild)
        if updated:
            current = c.data
            if current is not None:
                c.data = self.coordinator_module.TwoNIntercomData(
                    call_status=current.call_status,
                    last_ring_time=c._last_ring_time,
                    caller_info=current.caller_info,
                    active_session_id=c._active_session_id,
                    available=True,
                    phone_status=c._phone_status or {},
                    switch_caps=c._switch_caps or {},
                    switch_status=c._switch_status or {},
                    io_caps=c._io_caps or {},
                    io_status=c._io_status or {},
                )

        # Verify the rebuilt data reflects the cache patch
        self.assertTrue(c.data.switch_status["switches"][0]["active"])
