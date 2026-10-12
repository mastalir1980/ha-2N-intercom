"""Unit tests for the last-ring image entity (TASK-9)."""

from __future__ import annotations

from datetime import datetime, timezone
import sys
import types
import unittest

from _stubs import (
    CONST_PATH,
    ENTITY_PATH,
    IMAGE_PATH,
    ensure_package,
    load_module,
)


def _install_homeassistant_stubs() -> None:
    ensure_package("homeassistant")
    ensure_package("homeassistant.components")
    ensure_package("homeassistant.helpers")

    image_module = types.ModuleType("homeassistant.components.image")

    class ImageEntity:
        _attr_image_last_updated = None

        def __init__(self, hass, verify_ssl: bool = False) -> None:
            self.hass = hass
            self.image_init_called = True

        @property
        def image_last_updated(self):
            return self._attr_image_last_updated

    image_module.ImageEntity = ImageEntity
    sys.modules["homeassistant.components.image"] = image_module

    config_entries = types.ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntry = object
    sys.modules["homeassistant.config_entries"] = config_entries

    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    core.callback = lambda func: func
    sys.modules["homeassistant.core"] = core

    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
    entity_platform.AddEntitiesCallback = object
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform

    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class CoordinatorEntity:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, coordinator) -> None:
            self.coordinator = coordinator
            self.state_writes = 0

        def _handle_coordinator_update(self) -> None:
            self.state_writes += 1

    update_coordinator.CoordinatorEntity = CoordinatorEntity
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator


def load_image_module():
    _install_homeassistant_stubs()
    ensure_package("custom_components")
    ensure_package("custom_components.2n_intercom")
    load_module("custom_components.2n_intercom.const", CONST_PATH)
    coordinator_module = types.ModuleType("custom_components.2n_intercom.coordinator")
    coordinator_module.TwoNIntercomCoordinator = object
    coordinator_module.TwoNIntercomRuntimeData = object
    sys.modules["custom_components.2n_intercom.coordinator"] = coordinator_module
    load_module("custom_components.2n_intercom.entity", ENTITY_PATH)
    return load_module("custom_components.2n_intercom.image", IMAGE_PATH)


class FakeConfigEntry:
    def __init__(self, entry_id: str) -> None:
        self.entry_id = entry_id
        self.data = {"name": "Front Door"}
        self.options = {}


class FakeCoordinator:
    def __init__(self, snapshot=None, snapshot_time=None) -> None:
        self.ring_snapshot = snapshot
        self.ring_snapshot_time = snapshot_time
        self.last_update_success = True

    def get_device_info(self, entry_id, name):
        return {"entry_id": entry_id, "name": name}


class LastRingImageTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_image_module()

    def _entity(self, coordinator=None):
        coordinator = coordinator or FakeCoordinator()
        hass = types.SimpleNamespace(data={})
        return (
            self.module.TwoNIntercomLastRingImage(hass, coordinator, FakeConfigEntry("entry-1")),
            coordinator,
            hass,
        )

    async def test_setup_entry_adds_single_image(self) -> None:
        coordinator = FakeCoordinator()
        entry = FakeConfigEntry("entry-1")
        entry.runtime_data = types.SimpleNamespace(coordinator=coordinator)
        added: list[object] = []

        await self.module.async_setup_entry(
            types.SimpleNamespace(data={}),
            entry,
            lambda entities, update_before_add=False: added.extend(entities),
        )

        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]._attr_unique_id, "entry-1_last_ring")

    def test_static_attributes(self) -> None:
        entity, _coordinator, hass = self._entity()
        self.assertEqual(entity._attr_translation_key, "last_ring")
        self.assertEqual(entity._attr_content_type, "image/jpeg")
        self.assertTrue(entity._attr_has_entity_name)
        self.assertEqual(entity._attr_device_info, {"entry_id": "entry-1", "name": "Front Door"})
        self.assertIs(entity.hass, hass)
        self.assertTrue(entity.image_init_called)
        self.assertEqual(self.module.PARALLEL_UPDATES, 0)

    async def test_no_image_before_first_ring(self) -> None:
        entity, _coordinator, _hass = self._entity()
        self.assertIsNone(entity.image_last_updated)
        self.assertIsNone(await entity.async_image())

    async def test_initial_state_reflects_existing_snapshot(self) -> None:
        captured = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        entity, _coordinator, _hass = self._entity(FakeCoordinator(b"jpeg", captured))
        self.assertEqual(entity.image_last_updated, captured)
        self.assertEqual(await entity.async_image(), b"jpeg")

    async def test_coordinator_update_picks_up_new_snapshot(self) -> None:
        entity, coordinator, _hass = self._entity()
        captured = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        coordinator.ring_snapshot = b"new-jpeg"
        coordinator.ring_snapshot_time = captured

        entity._handle_coordinator_update()

        self.assertEqual(entity.image_last_updated, captured)
        self.assertEqual(entity.state_writes, 1)
        self.assertEqual(await entity.async_image(), b"new-jpeg")


if __name__ == "__main__":
    unittest.main()
