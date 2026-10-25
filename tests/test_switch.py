"""Unit tests for the switch platform (auto-detected from device caps)."""

from __future__ import annotations

import asyncio
import sys
import types
import unittest
from unittest.mock import AsyncMock

from _stubs import (
    CONST_PATH,
    ENTITY_PATH,
    SWITCH_PATH,
    ensure_package,
    load_module,
)


def _install_homeassistant_stubs() -> None:
    ensure_package("homeassistant")

    exceptions = types.ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        def __init__(
            self, *, translation_domain, translation_key, translation_placeholders
        ) -> None:
            super().__init__(translation_key)
            self.translation_domain = translation_domain
            self.translation_key = translation_key
            self.translation_placeholders = translation_placeholders

    exceptions.HomeAssistantError = HomeAssistantError
    sys.modules["homeassistant.exceptions"] = exceptions

    switch_module = types.ModuleType("homeassistant.components.switch")

    class SwitchEntity:
        def __init__(self) -> None:
            self.hass = None

        def async_write_ha_state(self) -> None:
            return None

    switch_module.SwitchEntity = SwitchEntity
    sys.modules["homeassistant.components.switch"] = switch_module
    ensure_package("homeassistant.components")

    config_entries = types.ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntry = object
    sys.modules["homeassistant.config_entries"] = config_entries

    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    core.callback = lambda fn: fn  # noqa: E731 — identity decorator stub
    sys.modules["homeassistant.core"] = core

    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
    entity_platform.AddEntitiesCallback = object
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform

    # Entity registry stub — enough for async_get / async_get_entity_id / async_remove
    entity_registry_mod = types.ModuleType("homeassistant.helpers.entity_registry")

    class _FakeEntityRegistry:
        """Minimal entity registry for test isolation."""
        def __init__(self):
            self._entries: dict[str, str] = {}  # unique_id → entity_id

        def async_get_entity_id(self, domain, platform, unique_id):
            return self._entries.get(unique_id)

        def async_remove(self, entity_id):
            self._entries = {
                uid: eid for uid, eid in self._entries.items()
                if eid != entity_id
            }

        def register(self, unique_id, entity_id):
            """Test helper — simulate HA registering an entity."""
            self._entries[unique_id] = entity_id

    _global_registry = _FakeEntityRegistry()

    def async_get(hass):
        return _global_registry

    entity_registry_mod.async_get = async_get
    entity_registry_mod._test_registry = _global_registry
    sys.modules["homeassistant.helpers.entity_registry"] = entity_registry_mod

    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class CoordinatorEntity:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, coordinator) -> None:
            self.coordinator = coordinator
            self.hass = getattr(coordinator, "hass", None)

        def async_write_ha_state(self) -> None:
            return None

    update_coordinator.CoordinatorEntity = CoordinatorEntity
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator
    ensure_package("homeassistant.helpers")


def load_switch_module():
    _install_homeassistant_stubs()
    ensure_package("custom_components")
    ensure_package("custom_components.2n_intercom")
    load_module("custom_components.2n_intercom.const", CONST_PATH)
    coordinator_module = types.ModuleType("custom_components.2n_intercom.coordinator")
    coordinator_module.TwoNIntercomCoordinator = object
    coordinator_module.TwoNIntercomRuntimeData = object
    sys.modules["custom_components.2n_intercom.coordinator"] = coordinator_module
    load_module("custom_components.2n_intercom.entity", ENTITY_PATH)
    return load_module("custom_components.2n_intercom.switch", SWITCH_PATH)


class FakeConfigEntry:
    def __init__(self, entry_id: str, data: dict[str, object], options=None) -> None:
        self.entry_id = entry_id
        self.data = data
        self.options = options or {}
        self._unload_callbacks: list = []

    def async_on_unload(self, callback):
        self._unload_callbacks.append(callback)


class FakeCoordinator:
    def __init__(self, trigger_result: bool = True, switch_caps=None, switch_status=None) -> None:
        self.last_update_success = True
        self._trigger_result = trigger_result
        self._switch_caps = switch_caps or {}
        self._switch_status = switch_status or {}
        self.trigger_calls: list[dict] = []
        self._listeners: list = []

    @property
    def switch_caps(self):
        return self._switch_caps

    @property
    def switch_status(self):
        return self._switch_status

    @property
    def io_caps(self):
        return {}

    @property
    def io_status(self):
        return {}

    def get_device_info(self, entry_id, name):
        return {"entry_id": entry_id, "name": name}

    async def async_trigger_relay(self, relay, duration):
        self.trigger_calls.append({"relay": relay, "duration": duration})
        return self._trigger_result

    def async_add_listener(self, callback):
        self._listeners.append(callback)
        def remove():
            self._listeners.remove(callback)
        return remove

    def fire_update(self):
        """Simulate a coordinator update — calls all listeners."""
        for listener in list(self._listeners):
            listener()


# Realistic device caps
DEVICE_CAPS_ONE_ENABLED = {
    "switches": [
        {"switch": 1, "enabled": True, "mode": "monostable", "switchOnDuration": 5, "type": "normal"},
        {"switch": 2, "enabled": False},
        {"switch": 3, "enabled": False},
        {"switch": 4, "enabled": False},
    ]
}

DEVICE_CAPS_TWO_ENABLED = {
    "switches": [
        {"switch": 1, "enabled": True, "mode": "monostable", "switchOnDuration": 5, "type": "normal"},
        {"switch": 2, "enabled": True, "mode": "monostable", "switchOnDuration": 15, "type": "normal"},
        {"switch": 3, "enabled": False},
        {"switch": 4, "enabled": False},
    ]
}


class SwitchAutoDetectionTests(unittest.IsolatedAsyncioTestCase):
    """Tests for auto-detection of switches from device caps."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.switch_module = load_switch_module()

    async def test_auto_detects_enabled_switch(self) -> None:
        coordinator = FakeCoordinator(switch_caps=DEVICE_CAPS_ONE_ENABLED)
        entry = FakeConfigEntry("entry-1", {"name": "Intercom"})
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)

        added: list[object] = []
        await self.switch_module.async_setup_entry(
            None, entry,
            lambda entities, update_before_add=False: added.extend(entities),
        )
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]._attr_unique_id, "entry-1_switch_1")
        self.assertEqual(added[0]._attr_name, "Relay 1")
        self.assertEqual(added[0]._pulse_duration, 5000)

    async def test_auto_detects_multiple_enabled_switches(self) -> None:
        coordinator = FakeCoordinator(switch_caps=DEVICE_CAPS_TWO_ENABLED)
        entry = FakeConfigEntry("entry-1", {"name": "Intercom"})
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)

        added: list[object] = []
        await self.switch_module.async_setup_entry(
            None, entry,
            lambda entities, update_before_add=False: added.extend(entities),
        )
        self.assertEqual(len(added), 2)
        self.assertEqual(added[0]._relay_number, 1)
        self.assertEqual(added[0]._pulse_duration, 5000)
        self.assertEqual(added[1]._relay_number, 2)
        self.assertEqual(added[1]._pulse_duration, 15000)

    async def test_skips_disabled_switches(self) -> None:
        caps = {"switches": [{"switch": 1, "enabled": False}]}
        coordinator = FakeCoordinator(switch_caps=caps)
        entry = FakeConfigEntry("entry-1", {"name": "Intercom"})
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)

        added: list[object] = []
        await self.switch_module.async_setup_entry(
            None, entry,
            lambda entities, update_before_add=False: added.extend(entities),
        )
        self.assertEqual(len(added), 0)

    async def test_skips_gate_type_user_override(self) -> None:
        coordinator = FakeCoordinator(switch_caps=DEVICE_CAPS_ONE_ENABLED)
        entry = FakeConfigEntry("entry-1", {"name": "Intercom"}, options={
            "relays": [{"relay_number": 1, "relay_device_type": "gate"}],
        })
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)

        added: list[object] = []
        await self.switch_module.async_setup_entry(
            None, entry,
            lambda entities, update_before_add=False: added.extend(entities),
        )
        self.assertEqual(len(added), 0)

    async def test_user_override_name_and_pulse(self) -> None:
        coordinator = FakeCoordinator(switch_caps=DEVICE_CAPS_ONE_ENABLED)
        entry = FakeConfigEntry("entry-1", {"name": "Intercom"}, options={
            "relays": [{
                "relay_number": 1,
                "relay_name": "Haustür",
                "relay_device_type": "door",
                "relay_pulse_duration": 3000,
            }],
        })
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)

        added: list[object] = []
        await self.switch_module.async_setup_entry(
            None, entry,
            lambda entities, update_before_add=False: added.extend(entities),
        )
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]._attr_name, "Haustür")
        self.assertEqual(added[0]._pulse_duration, 3000)

    async def test_empty_caps_creates_nothing(self) -> None:
        coordinator = FakeCoordinator(switch_caps={})
        entry = FakeConfigEntry("entry-1", {"name": "Intercom"})
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)

        added: list[object] = []
        await self.switch_module.async_setup_entry(
            None, entry,
            lambda entities, update_before_add=False: added.extend(entities),
        )
        self.assertEqual(len(added), 0)

    async def test_caps_without_duration_uses_default(self) -> None:
        caps = {"switches": [{"switch": 1, "enabled": True}]}
        coordinator = FakeCoordinator(switch_caps=caps)
        entry = FakeConfigEntry("entry-1", {"name": "Intercom"})
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)

        added: list[object] = []
        await self.switch_module.async_setup_entry(
            None, entry,
            lambda entities, update_before_add=False: added.extend(entities),
        )
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]._pulse_duration, 2000)


class SwitchDynamicDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    """Tests for dynamic add/remove on coordinator updates."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.switch_module = load_switch_module()

    async def test_new_relay_enabled_adds_entity(self) -> None:
        """Enabling a relay on the device adds an entity on next update."""
        coordinator = FakeCoordinator(switch_caps=DEVICE_CAPS_ONE_ENABLED)
        entry = FakeConfigEntry("entry-1", {"name": "Intercom"})
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)

        added: list[object] = []
        await self.switch_module.async_setup_entry(
            None, entry,
            lambda entities, update_before_add=False: added.extend(entities),
        )
        self.assertEqual(len(added), 1)

        # Simulate enabling relay 2 on the device.
        coordinator._switch_caps = DEVICE_CAPS_TWO_ENABLED
        coordinator.fire_update()

        self.assertEqual(len(added), 2)
        self.assertEqual(added[1]._relay_number, 2)

    async def test_relay_disabled_removes_entity(self) -> None:
        """Disabling a relay on the device removes the entity from registry."""
        registry = sys.modules["homeassistant.helpers.entity_registry"]._test_registry
        coordinator = FakeCoordinator(switch_caps=DEVICE_CAPS_TWO_ENABLED)
        entry = FakeConfigEntry("entry-1", {"name": "Intercom"})
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)

        added: list[object] = []
        await self.switch_module.async_setup_entry(
            None, entry,
            lambda entities, update_before_add=False: added.extend(entities),
        )
        self.assertEqual(len(added), 2)

        # Simulate HA registering the entities.
        registry.register("entry-1_switch_1", "switch.relay_1")
        registry.register("entry-1_switch_2", "switch.relay_2")

        # Simulate disabling relay 2 on the device.
        coordinator._switch_caps = DEVICE_CAPS_ONE_ENABLED
        coordinator.fire_update()

        # Relay 2 entity should be removed from registry.
        self.assertIsNone(registry.async_get_entity_id("switch", "2n_intercom", "entry-1_switch_2"))
        # Relay 1 should still be there.
        self.assertEqual(registry.async_get_entity_id("switch", "2n_intercom", "entry-1_switch_1"), "switch.relay_1")

    async def test_no_duplicate_on_repeated_updates(self) -> None:
        """Repeated coordinator updates don't create duplicate entities."""
        coordinator = FakeCoordinator(switch_caps=DEVICE_CAPS_ONE_ENABLED)
        entry = FakeConfigEntry("entry-1", {"name": "Intercom"})
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)

        added: list[object] = []
        await self.switch_module.async_setup_entry(
            None, entry,
            lambda entities, update_before_add=False: added.extend(entities),
        )
        self.assertEqual(len(added), 1)

        coordinator.fire_update()
        coordinator.fire_update()
        coordinator.fire_update()

        # Still only 1 entity.
        self.assertEqual(len(added), 1)

    async def test_config_and_capability_events_add_and_remove_relay_entities(self) -> None:
        from test_coordinator import load_coordinator_module

        coordinator_module = load_coordinator_module()
        registry = self.switch_module.er._test_registry
        for event_name in ("ConfigurationChanged", "CapabilitiesChanged"):
            with self.subTest(event=event_name):
                tasks = []
                listeners = []

                def create_task(coro):
                    task = asyncio.create_task(coro)
                    tasks.append(task)
                    return task

                def add_listener(callback):
                    listeners.append(callback)
                    return lambda: listeners.remove(callback)

                def update_listeners():
                    for callback in listeners:
                        callback()

                api = types.SimpleNamespace(
                    async_get_switch_caps=AsyncMock(return_value=DEVICE_CAPS_ONE_ENABLED),
                )
                coordinator = coordinator_module.TwoNIntercomCoordinator(
                    types.SimpleNamespace(async_create_task=create_task), api,
                )
                coordinator.async_add_listener = add_listener
                coordinator.async_update_listeners = update_listeners
                await coordinator._refresh_secondary_cache(
                    "_switch_caps", "async_get_switch_caps", "switch caps",
                )
                entry = FakeConfigEntry("event-entry", {"name": "Intercom"})
                entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)
                added = []

                def add_entities(entities, update_before_add=False):
                    for entity in entities:
                        added.append(entity)
                        registry.register(
                            entity._attr_unique_id, f"switch.event_relay_{entity._relay_number}",
                        )

                await self.switch_module.async_setup_entry(None, entry, add_entities)
                self.assertEqual([entity._relay_number for entity in added], [1])

                api.async_get_switch_caps.return_value = DEVICE_CAPS_TWO_ENABLED
                coordinator._process_log_event({"event": event_name})
                await asyncio.gather(*tasks)
                self.assertEqual([entity._relay_number for entity in added], [1, 2])

                api.async_get_switch_caps.return_value = DEVICE_CAPS_ONE_ENABLED
                coordinator._process_log_event({"event": event_name})
                await asyncio.gather(*tasks)
                self.assertIsNone(registry.async_get_entity_id(
                    "switch", "2n_intercom", "event-entry_switch_2",
                ))
                self.assertEqual(registry.async_get_entity_id(
                    "switch", "2n_intercom", "event-entry_switch_1",
                ), "switch.event_relay_1")
                self.assertEqual(api.async_get_switch_caps.await_count, 3)


class SwitchEntityTests(unittest.IsolatedAsyncioTestCase):
    """Tests for switch entity behavior."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.switch_module = load_switch_module()

    def _make_switch(self, coordinator=None, **kwargs):
        coordinator = coordinator or FakeCoordinator()
        entry = FakeConfigEntry("entry-1", {"name": "Intercom"})
        defaults = {
            "relay_number": 1,
            "relay_name": "Front Door",
            "pulse_duration": 2000,
        }
        defaults.update(kwargs)
        return self.switch_module.TwoNIntercomSwitch(
            coordinator, entry, **defaults
        )

    def test_initial_state(self) -> None:
        switch = self._make_switch()
        self.assertFalse(switch.is_on)
        self.assertEqual(switch._attr_name, "Front Door")
        self.assertEqual(switch._attr_unique_id, "entry-1_switch_1")

    def test_is_on_reads_live_status(self) -> None:
        coordinator = FakeCoordinator(switch_status={
            "switches": [{"switch": 1, "active": True, "held": False}]
        })
        switch = self._make_switch(coordinator=coordinator)
        self.assertTrue(switch.is_on)

    def test_is_on_falls_back_to_optimistic(self) -> None:
        coordinator = FakeCoordinator(switch_status={})
        switch = self._make_switch(coordinator=coordinator)
        self.assertFalse(switch.is_on)
        switch._attr_is_on = True
        self.assertTrue(switch.is_on)

    async def test_turn_on_triggers_relay(self) -> None:
        coordinator = FakeCoordinator(trigger_result=True)
        switch = self._make_switch(coordinator=coordinator, pulse_duration=10)
        await switch.async_turn_on()

        self.assertEqual(len(coordinator.trigger_calls), 1)
        self.assertEqual(coordinator.trigger_calls[0]["relay"], 1)
        self.assertEqual(coordinator.trigger_calls[0]["duration"], 10)

        await asyncio.sleep(0.02)
        self.assertFalse(switch._attr_is_on)

    async def test_turn_on_failure_stays_off(self) -> None:
        coordinator = FakeCoordinator(trigger_result=False)
        switch = self._make_switch(coordinator=coordinator)
        await switch.async_turn_on()
        self.assertFalse(switch._attr_is_on)

    async def test_turn_off(self) -> None:
        switch = self._make_switch()
        switch._attr_is_on = True
        await switch.async_turn_off()
        self.assertFalse(switch._attr_is_on)

    async def test_turn_on_cancels_pending_off(self) -> None:
        coordinator = FakeCoordinator(trigger_result=True)
        switch = self._make_switch(coordinator=coordinator, pulse_duration=5000)
        await switch.async_turn_on()
        first_task = switch._turning_off_task
        self.assertFalse(first_task.done())

        switch._pulse_duration = 10
        await switch.async_turn_on()
        await asyncio.sleep(0)
        self.assertTrue(first_task.done())
        await asyncio.sleep(0.02)

    def test_device_info(self) -> None:
        switch = self._make_switch()
        info = switch._attr_device_info
        self.assertEqual(info["entry_id"], "entry-1")


ISSUE_13_IO_PORTS = [
    ("led_secured", "output"),
    ("relay1", "output"),
    ("output1", "output"),
    ("modul1.relay1", "output"),
    ("modul1.relay2", "output"),
    ("input1", "input"),
    ("modul1.input1", "input"),
    ("modul1.input2", "input"),
    ("modul1.tamper", "input"),
]


class IoOutputSwitchTests(unittest.IsolatedAsyncioTestCase):
    """Physical output discovery, confirmed state, and action failures."""

    @classmethod
    def setUpClass(cls) -> None:
        from test_coordinator import load_coordinator_module

        cls.coordinator_module = load_coordinator_module()
        cls.switch_module = load_switch_module()

    def _make_coordinator(self, success=True):
        coordinator = self.coordinator_module.TwoNIntercomCoordinator(
            types.SimpleNamespace(),
            types.SimpleNamespace(async_io_control=AsyncMock(return_value=success)),
        )
        coordinator._io_caps = {
            "ports": [{"port": port, "type": kind} for port, kind in ISSUE_13_IO_PORTS]
        }
        coordinator._io_status = {
            "ports": [{"port": port, "state": 0} for port, _ in ISSUE_13_IO_PORTS]
        }
        coordinator.async_request_refresh = AsyncMock()
        coordinator.get_device_info = lambda entry_id, name: {
            "entry_id": entry_id, "name": name
        }
        coordinator.listeners = []

        def add_listener(listener):
            coordinator.listeners.append(listener)
            return lambda: coordinator.listeners.remove(listener)

        coordinator.async_add_listener = add_listener
        return coordinator

    def _make_switch(self, coordinator=None, port="modul1.relay1"):
        if coordinator is None:
            coordinator = self._make_coordinator()
        return self.switch_module.TwoNIntercomIoOutputSwitch(
            coordinator, FakeConfigEntry("entry-1", {"name": "Intercom"}), port
        )

    async def test_discovers_issue_13_outputs_once_alongside_logical_switch(self):
        coordinator = self._make_coordinator()
        coordinator._switch_caps = DEVICE_CAPS_ONE_ENABLED
        entry = FakeConfigEntry("entry-1", {"name": "Intercom"})
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)
        added = []
        await self.switch_module.async_setup_entry(
            None, entry, lambda entities, update_before_add=False: added.extend(entities)
        )
        self.assertEqual(
            {entity._attr_unique_id for entity in added},
            {
                "entry-1_switch_1",
                "entry-1_io_relay1",
                "entry-1_io_output1",
                "entry-1_io_modul1.relay1",
                "entry-1_io_modul1.relay2",
            },
        )
        for entity in added[1:]:
            self.assertFalse(entity._attr_entity_registry_enabled_default)
            self.assertEqual(entity._attr_translation_key, "io_output")
            self.assertEqual(entity._attr_translation_placeholders, {"port": entity._port})
        for listener in coordinator.listeners:
            listener()
        self.assertEqual(len(added), 5)

    def test_discovery_skips_malformed_missing_and_duplicate_ports(self):
        coordinator = self._make_coordinator()
        coordinator._io_caps["ports"].extend([
            None, "not a port", {},
            {"type": "output"},
            {"type": "output", "port": 12},
            {"type": "output", "port": []},
            {"type": "output", "port": ""},
            {"type": "output", "port": "missing"},
            {"type": "output", "port": "relay1"},
        ])
        coordinator._io_status["ports"].extend([None, "invalid", {}, {"port": []}])
        self.assertEqual(
            self.switch_module._io_output_ports(coordinator),
            ["relay1", "output1", "modul1.relay1", "modul1.relay2"],
        )
        for ports in (None, 1, "invalid", {}):
            with self.subTest(ports=ports):
                coordinator._io_caps = {"ports": ports}
                self.assertEqual(self.switch_module._io_output_ports(coordinator), [])
        coordinator._io_caps = {"ports": [{"port": "relay1", "type": "output"}]}
        for ports in (None, 1, "invalid", {}):
            with self.subTest(status_ports=ports):
                coordinator._io_status = {"ports": ports}
                self.assertEqual(self.switch_module._io_output_ports(coordinator), [])

    def test_state_comes_only_from_matching_io_status(self):
        coordinator = self._make_coordinator()
        switch = self._make_switch(coordinator)
        for state in (1, True, "1", "on", "true"):
            with self.subTest(state=state):
                coordinator._io_status = {
                    "ports": [{"port": "modul1.relay1", "state": state}]
                }
                self.assertTrue(switch.is_on)
        for state in (0, False, "0", "off", "false", None, [], {}):
            with self.subTest(state=state):
                coordinator._io_status["ports"][0]["state"] = state
                self.assertFalse(switch.is_on)
        for ports in (None, 1, {}, [None, {}, {"port": "relay1", "state": 1}]):
            with self.subTest(ports=ports):
                coordinator._io_status = {"ports": ports}
                self.assertFalse(switch.is_on)

    async def test_turn_on_off_use_api_and_refresh_without_optimistic_state(self):
        coordinator = self._make_coordinator()
        switch = self._make_switch(coordinator)
        await switch.async_turn_on()
        coordinator.api.async_io_control.assert_awaited_once_with("modul1.relay1", True)
        coordinator.async_request_refresh.assert_awaited_once_with()
        self.assertFalse(switch.is_on)
        self.assertFalse(hasattr(switch, "_turning_off_task"))

        coordinator._io_status["ports"][3]["state"] = 1
        self.assertTrue(switch.is_on)
        coordinator.api.async_io_control.reset_mock()
        coordinator.async_request_refresh.reset_mock()
        await switch.async_turn_off()
        coordinator.api.async_io_control.assert_awaited_once_with("modul1.relay1", False)
        coordinator.async_request_refresh.assert_awaited_once_with()
        self.assertTrue(switch.is_on)

    async def test_success_reads_refreshed_device_state(self):
        coordinator = self._make_coordinator()
        switch = self._make_switch(coordinator)

        async def refresh():
            coordinator._io_status = {
                "ports": [{"port": "modul1.relay1", "state": 1}]
            }

        coordinator.async_request_refresh = AsyncMock(side_effect=refresh)
        await switch.async_turn_on()
        self.assertTrue(switch.is_on)

    async def test_failures_raise_translated_error_and_keep_state(self):
        for on in (True, False):
            with self.subTest(on=on):
                coordinator = self._make_coordinator(success=False)
                coordinator._io_status["ports"][3]["state"] = int(not on)
                switch = self._make_switch(coordinator)
                action = switch.async_turn_on if on else switch.async_turn_off
                with self.assertRaises(self.switch_module.HomeAssistantError) as caught:
                    await action()
                error = caught.exception
                self.assertEqual(error.translation_domain, "2n_intercom")
                self.assertEqual(error.translation_key, "io_control_failed")
                self.assertEqual(error.translation_placeholders, {"port": "modul1.relay1"})
                coordinator.api.async_io_control.assert_awaited_once_with("modul1.relay1", on)
                coordinator.async_request_refresh.assert_not_awaited()
                self.assertIs(switch.is_on, not on)

    def test_output_changed_event_updates_switch_state(self):
        coordinator = self._make_coordinator()
        switch = self._make_switch(coordinator)
        for state in (True, False, 1, 0):
            with self.subTest(state=state):
                self.assertTrue(coordinator._process_log_event({
                    "event": "OutputChanged",
                    "params": {"port": "modul1.relay1", "state": state},
                }))
                self.assertIs(switch.is_on, bool(state))


if __name__ == "__main__":
    unittest.main()
