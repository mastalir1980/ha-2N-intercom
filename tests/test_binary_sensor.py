"""Unit tests for the binary sensor platform."""

from __future__ import annotations

import sys
import types
import unittest

from _stubs import (
    BINARY_SENSOR_PATH,
    CONST_PATH,
    ENTITY_PATH,
    ensure_package,
    load_module,
)


def _install_homeassistant_stubs() -> None:
    ensure_package("homeassistant")

    binary_sensor_module = types.ModuleType("homeassistant.components.binary_sensor")

    class BinarySensorDeviceClass:
        MOTION = "motion"

    class BinarySensorEntity:
        def __init__(self) -> None:
            self.hass = None

    binary_sensor_module.BinarySensorDeviceClass = BinarySensorDeviceClass
    binary_sensor_module.BinarySensorEntity = BinarySensorEntity
    sys.modules["homeassistant.components.binary_sensor"] = binary_sensor_module
    ensure_package("homeassistant.components")

    config_entries = types.ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntry = object
    sys.modules["homeassistant.config_entries"] = config_entries

    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    sys.modules["homeassistant.core"] = core

    entity = types.ModuleType("homeassistant.helpers.entity")

    class EntityCategory:
        DIAGNOSTIC = "diagnostic"

    entity.EntityCategory = EntityCategory
    sys.modules["homeassistant.helpers.entity"] = entity

    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
    entity_platform.AddEntitiesCallback = object
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform

    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class CoordinatorEntity:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, coordinator) -> None:
            self.coordinator = coordinator
            self.hass = getattr(coordinator, "hass", None)

    update_coordinator.CoordinatorEntity = CoordinatorEntity
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator
    ensure_package("homeassistant.helpers")


def load_binary_sensor_module():
    _install_homeassistant_stubs()
    ensure_package("custom_components")
    ensure_package("custom_components.2n_intercom")
    load_module("custom_components.2n_intercom.const", CONST_PATH)
    coordinator_module = types.ModuleType("custom_components.2n_intercom.coordinator")
    coordinator_module.TwoNIntercomCoordinator = object
    coordinator_module.TwoNIntercomRuntimeData = object
    sys.modules["custom_components.2n_intercom.coordinator"] = coordinator_module
    load_module("custom_components.2n_intercom.entity", ENTITY_PATH)
    return load_module("custom_components.2n_intercom.binary_sensor", BINARY_SENSOR_PATH)


class FakeConfigEntry:
    def __init__(self, entry_id: str, data: dict[str, object]) -> None:
        self.entry_id = entry_id
        self.data = data
        self.options = {}


class FakeCoordinator:
    def __init__(
        self,
        *,
        io_caps: dict[str, object] | None = None,
        io_status: dict[str, object] | None = None,
        switch_caps: dict[str, object] | None = None,
        switch_status: dict[str, object] | None = None,
    ) -> None:
        self.io_caps = io_caps or {}
        self.io_status = io_status or {}
        self.switch_caps = switch_caps or {}
        self.switch_status = switch_status or {}
        self.last_update_success = True
        self.motion_detection_available = False
        self.motion_detected = False
        self.last_motion_time = None

    def get_device_info(self, entry_id, name):
        return {"entry_id": entry_id, "name": name}


class BinarySensorPlatformTests(unittest.IsolatedAsyncioTestCase):
    """Tests for binary sensor platform behavior."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.binary_sensor_module = load_binary_sensor_module()

    async def test_setup_entry_adds_input_sensor_when_input1_is_present(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator(
            io_caps={
                "ports": [
                    {"port": "input1", "type": "input"},
                ]
            },
            io_status={
                "ports": [
                    {"port": "input1", "state": 1},
                ]
            },
        )
        entry = FakeConfigEntry("entry-1", {"name": "Front Door"})
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)

        hass = types.SimpleNamespace(data={})
        added: list[object] = []

        await binary_sensor_module.async_setup_entry(
            hass,
            entry,
            lambda entities, update_before_add=False: added.extend(entities),
        )

        self.assertEqual(
            [entity._attr_unique_id for entity in added],
            ["entry-1_doorbell", "entry-1_input1"],
        )

    async def test_setup_entry_keeps_only_doorbell_when_input1_is_missing(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator(
            io_caps={"ports": [{"port": "relay1", "type": "output"}]},
            io_status={"ports": [{"port": "relay1", "state": 0}]},
        )
        entry = FakeConfigEntry("entry-1", {"name": "Front Door"})
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)

        hass = types.SimpleNamespace(data={})
        added: list[object] = []

        await binary_sensor_module.async_setup_entry(
            hass,
            entry,
            lambda entities, update_before_add=False: added.extend(entities),
        )

        self.assertEqual(
            [entity._attr_unique_id for entity in added],
            ["entry-1_doorbell"],
        )

    async def test_setup_entry_adds_relay_sensor_when_switch1_is_present(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator(
            switch_caps={
                "switches": [
                    {"switch": 1, "enabled": True},
                ]
            },
            switch_status={
                "switches": [
                    {"switch": 1, "active": False},
                ]
            },
        )
        entry = FakeConfigEntry("entry-1", {"name": "Front Door"})
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)

        hass = types.SimpleNamespace(data={})
        added: list[object] = []

        await binary_sensor_module.async_setup_entry(
            hass,
            entry,
            lambda entities, update_before_add=False: added.extend(entities),
        )

        self.assertEqual(
            [entity._attr_unique_id for entity in added],
            ["entry-1_doorbell", "entry-1_relay1_active"],
        )

    def test_input_sensor_uses_cached_io_status_payload(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator(
            io_caps={
                "ports": [
                    {"port": "input1", "type": "input"},
                ]
            },
            io_status={
                "ports": [
                    {"port": "input1", "state": 1},
                ]
            },
        )
        entity = binary_sensor_module.TwoNIntercomInput1Sensor(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Front Door"}),
        )

        self.assertTrue(entity.is_on)

    def test_doorbell_entity_has_translation_key(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator()
        entity = binary_sensor_module.TwoNIntercomDoorbell(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Front Door"}),
        )

        self.assertEqual(entity._attr_translation_key, "doorbell")
        self.assertTrue(entity._attr_has_entity_name)

    def test_input1_entity_has_translation_key(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator(
            io_caps={"ports": [{"port": "input1", "type": "input"}]},
            io_status={"ports": [{"port": "input1", "state": 0}]},
        )
        entity = binary_sensor_module.TwoNIntercomInput1Sensor(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Front Door"}),
        )

        self.assertEqual(entity._attr_translation_key, "input_1")
        self.assertTrue(entity._attr_has_entity_name)

    def test_relay1_active_entity_has_translation_key(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator(
            switch_caps={"switches": [{"switch": 1, "enabled": True}]},
            switch_status={"switches": [{"switch": 1, "active": False}]},
        )
        entity = binary_sensor_module.TwoNIntercomRelay1ActiveSensor(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Front Door"}),
        )

        self.assertEqual(entity._attr_translation_key, "relay_1_active")
        self.assertTrue(entity._attr_has_entity_name)

    def test_relay_sensor_uses_cached_switch_status_payload(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator(
            switch_caps={
                "switches": [
                    {"switch": 1, "enabled": True},
                ]
            },
            switch_status={
                "switches": [
                    {"switch": 1, "active": True, "locked": False, "held": False},
                ]
            },
        )
        entity = binary_sensor_module.TwoNIntercomRelay1ActiveSensor(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Front Door"}),
        )

        self.assertTrue(entity.is_on)
        self.assertEqual(entity._attr_unique_id, "entry-1_relay1_active")
        self.assertEqual(entity._attr_entity_category, "diagnostic")


    def test_doorbell_is_on_when_ring_active(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator()
        coordinator.ring_active = True
        entity = binary_sensor_module.TwoNIntercomDoorbell(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Door"}),
        )
        self.assertTrue(entity.is_on)

    def test_doorbell_is_off_when_not_ringing(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator()
        coordinator.ring_active = False
        entity = binary_sensor_module.TwoNIntercomDoorbell(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Door"}),
        )
        self.assertFalse(entity.is_on)

    def test_doorbell_extra_state_attributes(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        from datetime import datetime

        coordinator = FakeCoordinator()
        coordinator.ring_active = True
        coordinator.last_ring_time = datetime(2026, 4, 12, 10, 0)
        coordinator.called_peer = "sip:100@intercom"
        coordinator.caller_info = {
            "name": "John",
            "number": "100",
            "button": "1",
        }
        coordinator.data = types.SimpleNamespace(
            call_status={"direction": "incoming"},
        )
        coordinator.call_state = "ringing"

        entity = binary_sensor_module.TwoNIntercomDoorbell(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Door"}),
        )
        attrs = entity.extra_state_attributes
        self.assertEqual(attrs["caller_name"], "John")
        self.assertEqual(attrs["caller_number"], "100")
        self.assertEqual(attrs["button"], "1")
        self.assertEqual(attrs["called_peer"], "sip:100@intercom")
        self.assertIn("last_ring", attrs)
        self.assertEqual(attrs["call_state"], "ringing")
        self.assertEqual(attrs["call_direction"], "incoming")

    def test_doorbell_extra_state_attributes_tz_aware_last_ring(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        from datetime import datetime, timezone

        coordinator = FakeCoordinator()
        coordinator.ring_active = True
        coordinator.last_ring_time = datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc)
        coordinator.called_peer = None
        coordinator.caller_info = {}
        coordinator.data = types.SimpleNamespace(
            call_status={"direction": "incoming"},
        )
        coordinator.call_state = "ringing"

        entity = binary_sensor_module.TwoNIntercomDoorbell(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Door"}),
        )
        attrs = entity.extra_state_attributes
        self.assertTrue(attrs["last_ring"].endswith("+00:00"))

    def test_doorbell_extra_state_attributes_empty(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator()
        coordinator.ring_active = False
        coordinator.last_ring_time = None
        coordinator.called_peer = None
        coordinator.caller_info = {}
        coordinator.data = None

        entity = binary_sensor_module.TwoNIntercomDoorbell(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Door"}),
        )
        attrs = entity.extra_state_attributes
        self.assertEqual(attrs, {})

    def test_input1_off_when_state_zero(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator(
            io_status={"ports": [{"port": "input1", "state": 0}]},
        )
        entity = binary_sensor_module.TwoNIntercomInput1Sensor(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Door"}),
        )
        self.assertFalse(entity.is_on)

    def test_input1_on_with_string_state(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator(
            io_status={"ports": [{"port": "input1", "state": "on"}]},
        )
        entity = binary_sensor_module.TwoNIntercomInput1Sensor(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Door"}),
        )
        self.assertTrue(entity.is_on)

    def test_relay1_active_off(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator(
            switch_status={"switches": [{"switch": 1, "active": False}]},
        )
        entity = binary_sensor_module.TwoNIntercomRelay1ActiveSensor(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Door"}),
        )
        self.assertFalse(entity.is_on)

    def test_relay1_active_disabled_by_default(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator(
            switch_status={"switches": [{"switch": 1, "active": False}]},
        )
        entity = binary_sensor_module.TwoNIntercomRelay1ActiveSensor(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Door"}),
        )
        self.assertFalse(entity._attr_entity_registry_enabled_default)

    def test_port_exists_with_type_filter(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        payload = {"ports": [{"port": "input1", "type": "output"}]}
        # Should not find it because type doesn't match
        self.assertFalse(
            binary_sensor_module._port_exists(payload, "input1", port_type="input")
        )
        # Without type filter, should find it
        self.assertTrue(
            binary_sensor_module._port_exists(payload, "input1")
        )

    def test_switch_exists_true(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        self.assertTrue(
            binary_sensor_module._switch_exists({"switches": [{"switch": 1}]}, 1)
        )

    def test_switch_exists_false(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        self.assertFalse(
            binary_sensor_module._switch_exists({"switches": [{"switch": 2}]}, 1)
        )

    def test_switch_exists_empty(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        self.assertFalse(
            binary_sensor_module._switch_exists({}, 1)
        )


    def test_entity_base_properties(self) -> None:
        """Test that entity base class provides device_info, available, name."""
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator()
        coordinator.last_update_success = True
        entry = FakeConfigEntry("entry-1", {"name": "Front Door"})
        entry.options = {}

        entity = binary_sensor_module.TwoNIntercomDoorbell(coordinator, entry)

        # device_info set by base entity __init__ via _attr_device_info
        info = entity._attr_device_info
        self.assertEqual(info["entry_id"], "entry-1")
        self.assertEqual(info["name"], "Front Door")

    def test_entity_display_name_from_options(self) -> None:
        """_entry_display_name prefers options over data."""
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator()
        entry = FakeConfigEntry("entry-1", {"name": "Data Name"})
        entry.options = {"name": "Options Name"}

        entity = binary_sensor_module.TwoNIntercomDoorbell(coordinator, entry)
        info = entity._attr_device_info
        self.assertEqual(info["name"], "Options Name")

    # --- Motion sensor tests ---

    async def test_setup_entry_adds_motion_sensor_when_available(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator()
        coordinator.motion_detection_available = True
        entry = FakeConfigEntry("entry-1", {"name": "Front Door"})
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)

        hass = types.SimpleNamespace(data={})
        added: list[object] = []

        await binary_sensor_module.async_setup_entry(
            hass,
            entry,
            lambda entities, update_before_add=False: added.extend(entities),
        )

        unique_ids = [e._attr_unique_id for e in added]
        self.assertIn("entry-1_motion", unique_ids)

    async def test_setup_entry_skips_motion_sensor_when_not_available(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator()
        coordinator.motion_detection_available = False
        entry = FakeConfigEntry("entry-1", {"name": "Front Door"})
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)

        hass = types.SimpleNamespace(data={})
        added: list[object] = []

        await binary_sensor_module.async_setup_entry(
            hass,
            entry,
            lambda entities, update_before_add=False: added.extend(entities),
        )

        unique_ids = [e._attr_unique_id for e in added]
        self.assertNotIn("entry-1_motion", unique_ids)

    def test_motion_sensor_is_on_when_detected(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator()
        coordinator.motion_detected = True
        entity = binary_sensor_module.TwoNIntercomMotionSensor(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Door"}),
        )
        self.assertTrue(entity.is_on)

    def test_motion_sensor_is_off_when_not_detected(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator()
        coordinator.motion_detected = False
        entity = binary_sensor_module.TwoNIntercomMotionSensor(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Door"}),
        )
        self.assertFalse(entity.is_on)

    def test_motion_sensor_device_class(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator()
        entity = binary_sensor_module.TwoNIntercomMotionSensor(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Door"}),
        )
        self.assertEqual(entity._attr_device_class, "motion")

    def test_motion_sensor_no_translation_key(self) -> None:
        """Motion name comes from device_class, not a translation_key."""
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator()
        entity = binary_sensor_module.TwoNIntercomMotionSensor(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Door"}),
        )
        self.assertFalse(hasattr(entity, "_attr_translation_key"))
        self.assertTrue(entity._attr_has_entity_name)

    def test_motion_sensor_unique_id(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator()
        entity = binary_sensor_module.TwoNIntercomMotionSensor(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Door"}),
        )
        self.assertEqual(entity._attr_unique_id, "entry-1_motion")

    def test_motion_sensor_extra_state_attributes_with_time(self) -> None:
        from datetime import datetime
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator()
        coordinator.last_motion_time = datetime(2026, 4, 12, 14, 30, 0)
        entity = binary_sensor_module.TwoNIntercomMotionSensor(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Door"}),
        )
        attrs = entity.extra_state_attributes
        self.assertIn("last_motion", attrs)
        self.assertEqual(attrs["last_motion"], "2026-04-12T14:30:00")

    def test_motion_sensor_extra_state_attributes_tz_aware(self) -> None:
        from datetime import datetime, timezone
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator()
        coordinator.last_motion_time = datetime(2026, 4, 12, 14, 30, 0, tzinfo=timezone.utc)
        entity = binary_sensor_module.TwoNIntercomMotionSensor(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Door"}),
        )
        attrs = entity.extra_state_attributes
        self.assertTrue(attrs["last_motion"].endswith("+00:00"))

    def test_motion_sensor_extra_state_attributes_empty(self) -> None:
        binary_sensor_module = self.binary_sensor_module
        coordinator = FakeCoordinator()
        coordinator.last_motion_time = None
        entity = binary_sensor_module.TwoNIntercomMotionSensor(
            coordinator,
            FakeConfigEntry("entry-1", {"name": "Door"}),
        )
        attrs = entity.extra_state_attributes
        self.assertEqual(attrs, {})


if __name__ == "__main__":
    unittest.main()
