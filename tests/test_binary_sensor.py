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
        TAMPER = "tamper"

    class BinarySensorEntity:
        _attr_device_class = None
        _attr_entity_category = None
        _attr_entity_registry_enabled_default = True

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
            ["entry-1_input1"],
        )

    async def test_setup_entry_adds_no_sensors_when_no_inputs_exist(self) -> None:
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
            [],
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
            ["entry-1_relay1_active"],
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

    async def test_setup_never_creates_a_doorbell_binary_sensor(self) -> None:
        coordinator = FakeCoordinator()
        entry = FakeConfigEntry("entry-1", {"enable_doorbell": True})
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)
        added = []
        await self.binary_sensor_module.async_setup_entry(
            None, entry, lambda entities, update_before_add=False: added.extend(entities)
        )

        self.assertNotIn("entry-1_doorbell", [e._attr_unique_id for e in added])
        self.assertFalse(hasattr(self.binary_sensor_module, "TwoNIntercomDoorbell"))

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

        entity = binary_sensor_module.TwoNIntercomInput1Sensor(coordinator, entry)

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

        entity = binary_sensor_module.TwoNIntercomInput1Sensor(coordinator, entry)
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


ISSUE_13_IO_PORTS = [
    ("led_secured", "output", 0),
    ("relay1", "output", 0),
    ("output1", "output", 0),
    ("modul1.relay1", "output", 0),
    ("modul1.relay2", "output", 0),
    ("input1", "input", 0),
    ("modul1.input1", "input", 0),
    ("modul1.input2", "input", 1),
    ("modul1.tamper", "input", 1),
]


class IoInputSensorTests(unittest.IsolatedAsyncioTestCase):
    """Physical input discovery, upgrade compatibility, and pushed state."""

    @classmethod
    def setUpClass(cls) -> None:
        from test_coordinator import load_coordinator_module

        cls.coordinator_module = load_coordinator_module()
        cls.binary_sensor_module = load_binary_sensor_module()

    def _make_coordinator(self):
        return FakeCoordinator(
            io_caps={
                "ports": [
                    {"port": port, "type": kind}
                    for port, kind, _ in ISSUE_13_IO_PORTS
                ]
            },
            io_status={
                "ports": [
                    {"port": port, "state": state}
                    for port, _, state in ISSUE_13_IO_PORTS
                ]
            },
        )

    async def _setup_sensors(self, coordinator):
        entry = FakeConfigEntry("entry-1", {"name": "Front Door"})
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)
        added = []
        await self.binary_sensor_module.async_setup_entry(
            None, entry, lambda entities, update_before_add=False: added.extend(entities)
        )
        return {entity._attr_unique_id: entity for entity in added}

    async def test_discovers_issue_13_inputs_without_outputs(self) -> None:
        sensors = await self._setup_sensors(self._make_coordinator())
        self.assertEqual(
            set(sensors),
            {
                "entry-1_input1",
                "entry-1_io_modul1.input1",
                "entry-1_io_modul1.input2",
                "entry-1_io_modul1.tamper",
            },
        )
        for port, kind, state in ISSUE_13_IO_PORTS:
            if kind != "input":
                continue
            uid = "entry-1_input1" if port == "input1" else f"entry-1_io_{port}"
            sensor = sensors[uid]
            with self.subTest(port=port):
                self.assertIs(sensor.is_on, bool(state))
                self.assertTrue(sensor._attr_entity_registry_enabled_default)
                self.assertIsNone(sensor._attr_entity_category)
                if port == "input1":
                    self.assertIsInstance(
                        sensor, self.binary_sensor_module.TwoNIntercomInput1Sensor
                    )
                    self.assertEqual(sensor._attr_unique_id, "entry-1_input1")
                    self.assertEqual(sensor._attr_translation_key, "input_1")
                else:
                    self.assertEqual(sensor._attr_translation_placeholders, {"port": port})
                    self.assertEqual(
                        sensor._attr_translation_key,
                        "io_tamper" if port.endswith(".tamper") else "io_input",
                    )
                self.assertEqual(
                    sensor._attr_device_class,
                    "tamper" if port.endswith(".tamper") else None,
                )

    async def test_discovery_skips_malformed_missing_and_duplicate_ports(self) -> None:
        coordinator = self._make_coordinator()
        coordinator.io_caps["ports"].extend([
            None, "invalid", {},
            {"type": "input"},
            {"type": "input", "port": 12},
            {"type": "input", "port": []},
            {"type": "input", "port": ""},
            {"type": "input", "port": "missing"},
            {"type": "input", "port": "input1"},
            {"type": "input", "port": "modul1.input2"},
            {"port": "unknown_type"},
        ])
        coordinator.io_status["ports"].extend([
            None, "invalid", {}, {"port": []},
            {"port": "status_only", "state": 1},
            {"port": "unknown_type", "state": 1},
        ])
        sensors = await self._setup_sensors(coordinator)
        self.assertEqual(len(sensors), 4)
        self.assertEqual(
            self.binary_sensor_module.io_ports_of_type(
                coordinator.io_caps, coordinator.io_status, "input"
            ),
            ["input1", "modul1.input1", "modul1.input2", "modul1.tamper"],
        )

    async def test_discovery_skips_invalid_port_lists(self) -> None:
        for payload_name in ("io_caps", "io_status"):
            for ports in (None, 1, "invalid", {}, []):
                with self.subTest(payload=payload_name, ports=ports):
                    coordinator = self._make_coordinator()
                    setattr(coordinator, payload_name, {"ports": ports})
                    sensors = await self._setup_sensors(coordinator)
                    self.assertEqual(set(sensors), set())
            coordinator = self._make_coordinator()
            setattr(coordinator, payload_name, {})
            sensors = await self._setup_sensors(coordinator)
            self.assertEqual(set(sensors), set())

    async def test_tamper_classification_requires_exact_port_or_suffix(self) -> None:
        ports = ["tamper", "modul1.tamper", "modul2.tamper", "tamper1", "notamper"]
        coordinator = FakeCoordinator(
            io_caps={"ports": [{"port": port, "type": "input"} for port in ports]},
            io_status={"ports": [{"port": port, "state": 0} for port in ports]},
        )
        sensors = await self._setup_sensors(coordinator)
        self.assertEqual(len(sensors), len(ports))
        for port in ports:
            with self.subTest(port=port):
                sensor = sensors[f"entry-1_io_{port}"]
                tamper = port == "tamper" or port.endswith(".tamper")
                self.assertEqual(sensor._attr_device_class, "tamper" if tamper else None)
                self.assertEqual(
                    sensor._attr_translation_key, "io_tamper" if tamper else "io_input"
                )
                self.assertEqual(sensor._attr_translation_placeholders, {"port": port})

    def test_generic_input_reads_only_matching_cached_port(self) -> None:
        coordinator = self._make_coordinator()
        sensor = self.binary_sensor_module.TwoNIntercomIoInputSensor(
            coordinator, FakeConfigEntry("entry-1", {}), "modul1.input1"
        )
        for state in (
            1, True, "1", "on", "true", 0, False, "0", "off", "false", None, [], {}
        ):
            with self.subTest(state=state):
                coordinator.io_status = {
                    "ports": [
                        {"port": "input1", "state": 1},
                        {"port": "modul1.input1", "state": state},
                    ]
                }
                self.assertIs(sensor.is_on, state in (1, True, "1", "on", "true"))
        for ports in (None, 1, {}, [None, {}, {"port": "input1", "state": 1}]):
            with self.subTest(ports=ports):
                coordinator.io_status = {"ports": ports}
                self.assertFalse(sensor.is_on)

    async def test_input_changed_event_updates_only_matching_input(self) -> None:
        coordinator = self.coordinator_module.TwoNIntercomCoordinator(
            types.SimpleNamespace(), types.SimpleNamespace()
        )
        fixture = self._make_coordinator()
        coordinator._io_caps = fixture.io_caps
        coordinator._io_status = fixture.io_status
        coordinator.get_device_info = fixture.get_device_info
        sensors = await self._setup_sensors(coordinator)
        for port, kind, _ in ISSUE_13_IO_PORTS:
            if kind != "input":
                continue
            uid = "entry-1_input1" if port == "input1" else f"entry-1_io_{port}"
            for state in (True, False, 1, 0):
                with self.subTest(port=port, state=state):
                    before = {
                        key: sensor.is_on
                        for key, sensor in sensors.items()
                    }
                    self.assertTrue(coordinator._process_log_event({
                        "event": "InputChanged",
                        "params": {"port": port, "state": state},
                    }))
                    self.assertIs(sensors[uid].is_on, bool(state))
                    for other_uid, old_state in before.items():
                        if other_uid != uid:
                            self.assertIs(sensors[other_uid].is_on, old_state)


if __name__ == "__main__":
    unittest.main()
