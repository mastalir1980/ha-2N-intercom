"""Coordinator tests for the optional ring on a call-button press (TASK-39)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from test_coordinator_access import BASE_EVENTS, _CoordinatorTestCase, _FakeAPI


def _key(key: str) -> dict:
    return {"event": "KeyPressed", "params": {"key": key}}


def _call(event: str, state: str, **params) -> dict:
    return {"event": event, "params": {"state": state, "session": 135, **params}}


class KeyPressedSubscriptionTests(_CoordinatorTestCase):
    async def test_subscribes_key_pressed_when_option_on_and_listed(self) -> None:
        api = _FakeAPI(log_caps=["CallStateChanged", "KeyPressed"])
        coordinator, _hass, _ = self._make(api, ring_on_keypress=True)

        await self._run_listener_once(coordinator)

        self.assertEqual(api.subscriptions[0], BASE_EVENTS + ["KeyPressed"])

    async def test_no_key_pressed_when_option_off(self) -> None:
        api = _FakeAPI(log_caps=["CallStateChanged", "KeyPressed"])
        coordinator, _hass, _ = self._make(api)

        await self._run_listener_once(coordinator)

        self.assertEqual(api.subscriptions[0], BASE_EVENTS)

    async def test_no_key_pressed_when_device_does_not_list_it(self) -> None:
        for caps in (["CallStateChanged"], None, RuntimeError("caps failed")):
            with self.subTest(caps=caps):
                api = _FakeAPI(log_caps=caps)
                coordinator, _hass, _ = self._make(api, ring_on_keypress=True)

                await self._run_listener_once(coordinator)

                self.assertEqual(api.subscriptions[0], BASE_EVENTS)


class KeyPressedRingTests(_CoordinatorTestCase):
    def _make_ring(self, **kwargs):
        kwargs.setdefault("ring_on_keypress", True)
        kwargs.setdefault("ring_snapshot_enabled", True)
        return self._make(**kwargs)

    async def test_call_button_press_rings_once_with_snapshot(self) -> None:
        coordinator, hass, api = self._make_ring()

        self.assertTrue(coordinator._process_log_event(_key("%1")))
        await hass.drain()

        self.assertTrue(coordinator.ring_active)
        self.assertEqual(coordinator.ring_count, 1)
        self.assertIsNotNone(coordinator.last_ring_time.tzinfo)
        self.assertEqual(len(api.snapshot_calls), 1)
        self.assertEqual(coordinator.ring_snapshot, b"jpeg-1")

    async def test_call_button_press_without_snapshot_option(self) -> None:
        coordinator, hass, api = self._make_ring(ring_snapshot_enabled=False)

        coordinator._process_log_event(_key("%2"))
        await hass.drain()

        self.assertEqual(coordinator.ring_count, 1)
        self.assertEqual(api.snapshot_calls, [])

    async def test_keypad_keys_never_ring(self) -> None:
        for key in ("0", "5", "9", "*", "#", "", "%", "%a", "1%1"):
            with self.subTest(key=key):
                coordinator, hass, api = self._make_ring()

                self.assertFalse(coordinator._process_log_event(_key(key)))
                await hass.drain()

                self.assertFalse(coordinator.ring_active)
                self.assertEqual(coordinator.ring_count, 0)
                self.assertEqual(api.snapshot_calls, [])

    async def test_pin_entry_does_not_ring(self) -> None:
        coordinator, hass, api = self._make_ring()

        for key in ("1", "2", "3", "4", "#"):
            coordinator._process_log_event(_key(key))
        await hass.drain()

        self.assertEqual(coordinator.ring_count, 0)
        self.assertEqual(api.snapshot_calls, [])

    async def test_option_off_ignores_call_button(self) -> None:
        coordinator, hass, api = self._make_ring(ring_on_keypress=False)

        self.assertFalse(coordinator._process_log_event(_key("%1")))
        await hass.drain()

        self.assertEqual(coordinator.ring_count, 0)
        self.assertEqual(api.snapshot_calls, [])

    async def test_invalid_params_are_ignored(self) -> None:
        coordinator, _hass, _api = self._make_ring()

        self.assertFalse(coordinator._process_log_event(
            {"event": "KeyPressed", "params": "garbage"}
        ))
        self.assertEqual(coordinator.ring_count, 0)

    async def test_press_that_starts_a_call_rings_once(self) -> None:
        sequences = {
            "key first": [
                _key("%1"),
                _call("CallStateChanged", "ringing", direction="outgoing"),
                _call("CallSessionStateChanged", "ringing", originator="button"),
            ],
            "call first": [
                _call("CallStateChanged", "ringing", direction="outgoing"),
                _call("CallSessionStateChanged", "ringing", originator="button"),
                _key("%1"),
            ],
        }
        for name, sequence in sequences.items():
            with self.subTest(order=name):
                coordinator, hass, api = self._make_ring()

                for event in sequence:
                    coordinator._process_log_event(event)
                await hass.drain()

                self.assertEqual(coordinator.ring_count, 1)
                self.assertEqual(len(api.snapshot_calls), 1)
                self.assertEqual(coordinator.active_session_id, "135")

                coordinator._process_log_event(
                    _call("CallSessionStateChanged", "terminated")
                )
                self.assertFalse(coordinator.ring_active)
                self.assertEqual(coordinator.ring_count, 1)

    async def test_called_id_filter_does_not_apply_to_presses(self) -> None:
        coordinator, hass, _api = self._make_ring(called_id="sip:200@example.com")

        coordinator._process_log_event(_key("%1"))
        await hass.drain()

        self.assertEqual(coordinator.ring_count, 1)

    async def test_key_only_ring_clears_and_next_press_rings_again(self) -> None:
        coordinator, hass, api = self._make_ring()
        hass.loop = asyncio.get_running_loop()

        with patch.object(self.module, "KEYPRESS_RING_HOLD", 0.01):
            coordinator._process_log_event(_key("%1"))
            self.assertTrue(coordinator.ring_active)
            await asyncio.sleep(0.05)

            self.assertFalse(coordinator.ring_active)
            coordinator.async_update_listeners.assert_called()

            coordinator._process_log_event(_key("%1"))
            await hass.drain()

        self.assertEqual(coordinator.ring_count, 2)
        self.assertEqual(len(api.snapshot_calls), 2)

    async def test_clear_leaves_a_ring_that_a_call_took_over(self) -> None:
        coordinator, hass, _api = self._make_ring()
        hass.loop = asyncio.get_running_loop()

        with patch.object(self.module, "KEYPRESS_RING_HOLD", 0.01):
            coordinator._process_log_event(_key("%1"))
            coordinator._process_log_event(
                _call("CallStateChanged", "ringing", direction="outgoing")
            )
            await asyncio.sleep(0.05)

        self.assertTrue(coordinator._ring_detected)
        self.assertEqual(coordinator.ring_count, 1)
        await hass.drain()

    async def test_stop_log_listener_cancels_pending_clear(self) -> None:
        coordinator, hass, _api = self._make_ring()
        hass.loop = asyncio.get_running_loop()

        coordinator._process_log_event(_key("%1"))
        self.assertIsNotNone(coordinator._keypress_clear_handle)
        await coordinator.async_stop_log_listener()

        self.assertIsNone(coordinator._keypress_clear_handle)
        await hass.drain()
