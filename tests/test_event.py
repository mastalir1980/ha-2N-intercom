"""Unit tests for doorbell events using the real coordinator ring detection."""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import Mock

from _stubs import ENTITY_PATH, EVENT_PATH, install_event_stubs, load_module
from test_binary_sensor import load_binary_sensor_module
from test_coordinator import load_coordinator_module


def load_event_module():
    coordinator_module = load_coordinator_module()
    install_event_stubs()
    sys.modules["homeassistant.core"].callback = lambda func: func
    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
    entity_platform.AddEntitiesCallback = object
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform

    class CoordinatorEntity:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, coordinator) -> None:
            self.coordinator = coordinator
            self.hass = coordinator.hass
            self.state_writes = 0

        @property
        def available(self):
            return self.coordinator.last_update_success

        @property
        def should_poll(self):
            return False

        async def async_added_to_hass(self) -> None:
            await super().async_added_to_hass()
            self._remove_listener = self.coordinator.async_add_listener(
                self._handle_coordinator_update
            )

        async def async_will_remove_from_hass(self) -> None:
            self._remove_listener()

        def async_write_ha_state(self) -> None:
            self.state_writes += 1

    sys.modules["homeassistant.helpers.update_coordinator"].CoordinatorEntity = CoordinatorEntity
    load_module("custom_components.2n_intercom.entity", ENTITY_PATH)
    return (
        load_module("custom_components.2n_intercom.event", EVENT_PATH),
        coordinator_module,
    )


class FakeConfigEntry:
    def __init__(self, coordinator) -> None:
        self.entry_id = "entry-1"
        self.data = {"name": "Front Door"}
        self.options = {}
        self.runtime_data = types.SimpleNamespace(coordinator=coordinator)


class DoorbellEventTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.binary_sensor_module = load_binary_sensor_module()
        cls.module, cls.coordinator_module = load_event_module()

    def _coordinator(self, *, called_id=None):
        coordinator = self.coordinator_module.TwoNIntercomCoordinator(
            types.SimpleNamespace(), types.SimpleNamespace(), called_id=called_id
        )
        coordinator.data = self.coordinator_module.TwoNIntercomData(
            call_status={}, last_ring_time=None, caller_info=None,
            active_session_id=None, available=True, phone_status={},
            switch_caps={}, switch_status={}, io_caps={}, io_status={},
        )
        listeners = []

        def add_listener(listener):
            listeners.append(listener)
            return lambda: listeners.remove(listener)

        coordinator.async_add_listener = add_listener
        coordinator.async_update_listeners = lambda: [
            listener() for listener in list(listeners)
        ]
        return coordinator

    def _entity(self, coordinator):
        entity = self.module.TwoNIntercomDoorbellEvent(
            coordinator, FakeConfigEntry(coordinator)
        )
        entity._trigger_event = Mock(wraps=entity._trigger_event)
        return entity

    def _call_pair(self, coordinator, *, incoming=False, peer="100", publish_each=True):
        for event, signal in (
            ("CallStateChanged", {"direction": "incoming" if incoming else "outgoing"}),
            ("CallSessionStateChanged", {"originator": "incoming" if incoming else "button"}),
        ):
            self.assertTrue(coordinator._process_log_event({
                "event": event,
                "params": {"state": "ringing", "session": 42, "peer": peer, **signal},
            }))
            if publish_each:
                coordinator._publish_event_state()
        if not publish_each:
            coordinator._publish_event_state()

    async def test_setup_creates_one_doorbell_event_on_the_shared_device(self) -> None:
        coordinator = self._coordinator()
        entry = FakeConfigEntry(coordinator)
        added = []
        await self.module.async_setup_entry(
            coordinator.hass, entry, lambda entities: added.extend(entities)
        )

        self.assertEqual(len(added), 1)
        entity = added[0]
        self.assertIsInstance(entity, self.module.TwoNIntercomEntity)
        self.assertEqual(entity._attr_unique_id, "entry-1_doorbell_event")
        self.assertEqual(entity._attr_translation_key, "doorbell")
        self.assertEqual(entity._attr_device_class, self.module.EventDeviceClass.DOORBELL)
        self.assertEqual(entity.event_types, ["ring"])
        self.assertTrue(entity._attr_has_entity_name)
        self.assertEqual(
            entity._attr_device_info, coordinator.get_device_info("entry-1", "Front Door")
        )
        self.assertFalse(entity.should_poll)
        self.assertEqual(self.module.PARALLEL_UPDATES, 0)

    async def test_both_call_events_trigger_exactly_once(self) -> None:
        for publish_each in (True, False):
            with self.subTest(publish_each=publish_each):
                coordinator = self._coordinator()
                entity = self._entity(coordinator)
                await entity.async_added_to_hass()

                self._call_pair(coordinator, publish_each=publish_each)
                coordinator._publish_event_state()

                entity._trigger_event.assert_called_once_with("ring", {"called_peer": "100"})

    async def test_next_ring_triggers_again_even_after_pulse_expired(self) -> None:
        coordinator = self._coordinator()
        entity = self._entity(coordinator)
        await entity.async_added_to_hass()
        self._call_pair(coordinator)
        coordinator._process_log_event({
            "event": "CallSessionStateChanged",
            "params": {"state": "terminated", "session": 42},
        })
        coordinator._publish_event_state()
        coordinator._process_log_event({
            "event": "CallStateChanged",
            "params": {"state": "ringing", "direction": "outgoing", "session": 43},
        })

        # The event is independent of the short binary sensor pulse.
        coordinator._ring_pulse_until = None
        coordinator._publish_event_state()
        self.assertFalse(coordinator.ring_active)
        self.assertEqual(entity._trigger_event.call_count, 2)
        self.assertEqual(coordinator.ring_count, 2)

    async def test_incoming_calls_never_trigger(self) -> None:
        for called_id in (None, "100"):
            with self.subTest(called_id=called_id):
                coordinator = self._coordinator(called_id=called_id)
                entity = self._entity(coordinator)
                await entity.async_added_to_hass()
                self._call_pair(coordinator, incoming=True)
                entity._trigger_event.assert_not_called()

    async def test_called_id_filter_applies_to_both_call_events(self) -> None:
        for called_id, rings in (("200/2", 0), ("SIPS:100@example.com/2", 1)):
            with self.subTest(called_id=called_id):
                coordinator = self._coordinator(called_id=called_id)
                entity = self._entity(coordinator)
                await entity.async_added_to_hass()
                self._call_pair(coordinator, peer="sip:100@example.com:5061")
                self.assertEqual(entity._trigger_event.call_count, rings)

    async def test_only_known_caller_attributes_match_binary_sensor(self) -> None:
        coordinator = self._coordinator()
        coordinator.data.caller_info = {
            "name": "Visitor", "number": "100", "button": 1, "password": "not-exposed",
        }
        entity = self._entity(coordinator)
        await entity.async_added_to_hass()
        self._call_pair(coordinator, peer="sip:100:not-exposed@example.com")
        binary_sensor = self.binary_sensor_module.TwoNIntercomDoorbell(
            coordinator, FakeConfigEntry(coordinator)
        )
        expected = {
            key: binary_sensor.extra_state_attributes[key]
            for key in ("called_peer", "caller_name", "caller_number")
        }

        entity._trigger_event.assert_called_once_with("ring", expected)
        self.assertEqual(
            entity._last_event_extra_attributes,
            {"called_peer": "100", "caller_name": "Visitor", "caller_number": "100"},
        )
        self.assertEqual(binary_sensor._attr_unique_id, "entry-1_doorbell")
        self.assertIsNone(binary_sensor._attr_device_class)
        self.assertTrue(binary_sensor.is_on)

    async def test_ring_without_caller_metadata_has_no_extra_attributes(self) -> None:
        coordinator = self._coordinator()
        entity = self._entity(coordinator)
        await entity.async_added_to_hass()
        self._call_pair(coordinator, peer=None)
        entity._trigger_event.assert_called_once_with("ring", {})

    async def test_existing_rings_are_not_replayed_at_add_time(self) -> None:
        coordinator = self._coordinator()
        self._call_pair(coordinator)
        entity = self._entity(coordinator)
        coordinator._process_log_event({
            "event": "CallSessionStateChanged",
            "params": {"state": "terminated", "session": 42},
        })
        self._call_pair(coordinator)

        await entity.async_added_to_hass()
        coordinator._publish_event_state()

        self.assertTrue(entity.event_added)
        entity._trigger_event.assert_not_called()
        self.assertIsNone(entity._last_event_type)

    async def test_readding_entity_does_not_replay_last_ring(self) -> None:
        coordinator = self._coordinator()
        entity = self._entity(coordinator)
        await entity.async_added_to_hass()
        self._call_pair(coordinator)
        await entity.async_will_remove_from_hass()
        readded = self._entity(coordinator)
        await readded.async_added_to_hass()
        coordinator._publish_event_state()

        entity._trigger_event.assert_called_once()
        readded._trigger_event.assert_not_called()

    async def test_unrelated_updates_write_availability_without_ringing(self) -> None:
        coordinator = self._coordinator()
        entity = self._entity(coordinator)
        await entity.async_added_to_hass()
        self.assertTrue(entity.available)
        coordinator.last_update_success = False
        coordinator._publish_event_state()
        self.assertFalse(entity.available)
        coordinator.last_update_success = True
        coordinator._publish_event_state()
        self.assertTrue(entity.available)
        self.assertEqual(entity.state_writes, 2)
        entity._trigger_event.assert_not_called()


if __name__ == "__main__":
    unittest.main()
