"""Executor-only event picture history, path safety, retention and restore."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from _stubs import CONST_PATH, INTEGRATION_DIR, ensure_package, install_dt_util_stub, load_module


def load_event_pictures_module():
    ensure_package("custom_components")
    ensure_package("custom_components.2n_intercom")
    load_module("custom_components.2n_intercom.const", CONST_PATH)
    return load_module(
        "custom_components.2n_intercom.event_pictures", INTEGRATION_DIR / "event_pictures.py"
    )


class ExecutorHass:
    def __init__(self) -> None:
        self.executor_calls = []
        self.executor_threads = []

    async def async_add_executor_job(self, func, *args):
        self.executor_calls.append((func, args))

        def execute():
            self.executor_threads.append(threading.get_ident())
            return func(*args)

        return await asyncio.to_thread(execute)


class PictureHelpersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_event_pictures_module()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.local_time = datetime(2026, 11, 21, 14, 38, 7, tzinfo=timezone(timedelta(hours=1)))
        self.device_dir = self.root / "2n_intercom" / "front_door"

    def _picture(self, filename, data=b"jpeg", mtime=None, folder="2026-11-21"):
        path = self.device_dir / folder / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def test_root_selection(self) -> None:
        resolve = self.module.resolve_media_root
        self.assertEqual(resolve({"local": "/media", "other": "/other"}), Path("/media"))
        self.assertEqual(resolve({"custom": "/custom"}), Path("/custom"))
        self.assertIsNone(resolve({}))
        self.assertIsNone(resolve({"a": "/a", "b": "/b"}))
        self.assertIsNone(resolve({"local": ""}))

    def test_slug_names_are_single_ascii_components(self) -> None:
        for title, expected in (
            ("../Front Door/", "front_door"), ("Vchod č.1", "vchod_1"),
            ("", "intercom"), ("../../", "intercom"), ("ABC-_DEF", "abc-_def"),
        ):
            with self.subTest(title=title):
                name = self.module.device_folder_name(title)
                self.assertEqual(name, expected)
                self.assertRegex(name, r"^[a-z0-9_-]+$")
                self.assertNotIn("..", name)

    def test_paths_use_local_time_and_increment_collision_suffix(self) -> None:
        for kind in ("ring", "access-granted", "access-denied"):
            with self.subTest(kind=kind):
                path = self.module.build_picture_path(self.root, "../Front Door/", kind, self.local_time)
                self.assertEqual(
                    path.relative_to(self.root).as_posix(),
                    f"2n_intercom/front_door/2026-11-21/143807-{kind}.jpg",
                )
                self.assertTrue(self.module.write_picture(path, b"jpeg"))
                second = self.module.build_picture_path(self.root, "front_door", kind, self.local_time)
                self.assertEqual(second.name, f"143807-{kind}-2.jpg")
                self.assertTrue(self.module.write_picture(second, b"second"))
                self.assertEqual(path.read_bytes(), b"jpeg")
                self.assertEqual(second.read_bytes(), b"second")
        self.assertEqual(list(self.root.rglob("*.tmp")), [])

    def test_unknown_kinds_are_rejected(self) -> None:
        for kind in ("../secret", "card-123", "RING", ""):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.module.build_picture_path(self.root, "door", kind, self.local_time)

    def test_symlink_paths_never_escape_or_touch_targets(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "2n_intercom").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.module.build_picture_path(self.root, "front_door", "ring", self.local_time)
        self.assertFalse(self.module.write_picture(
            self.root / "2n_intercom" / "front_door" / "2026-11-21" / "143807-ring.jpg", b"jpeg"
        ))
        self.assertEqual(list(outside.iterdir()), [])

    def test_device_and_date_symlinks_are_rejected(self) -> None:
        self.device_dir.parent.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        for link in (self.device_dir, self.device_dir / "2026-11-21"):
            with self.subTest(link=link.name):
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(outside, target_is_directory=True)
                with self.assertRaises(ValueError):
                    self.module.build_picture_path(self.root, "front_door", "ring", self.local_time)
                link.unlink()

    def test_media_root_symlink_is_not_used_as_a_write_or_cleanup_target(self) -> None:
        link = self.root / "linked_media"
        link.symlink_to(self.root, target_is_directory=True)
        self.assertFalse(self.module.is_writable(link))
        with self.assertRaises(ValueError):
            self.module.build_picture_path(link, "front_door", "ring", self.local_time)

    def test_write_failure_is_false_and_removes_temp_file(self) -> None:
        path = self.module.build_picture_path(self.root, "front_door", "ring", self.local_time)
        with patch.object(self.module.os, "replace", side_effect=OSError("private path")):
            self.assertFalse(self.module.write_picture(path, b"jpeg"))
        self.assertFalse(path.exists())
        self.assertEqual(list(path.parent.iterdir()), [])

    def test_writable_probe_requires_existing_directory(self) -> None:
        self.assertTrue(self.module.is_writable(self.root))
        self.assertFalse(self.module.is_writable(self.root / "missing"))
        file = self.root / "file"
        file.touch()
        self.assertFalse(self.module.is_writable(file))
        with patch.object(self.module.tempfile, "TemporaryFile", side_effect=PermissionError):
            self.assertFalse(self.module.is_writable(self.root))
        self.assertEqual(list(self.root.iterdir()), [file])

    def test_retention_only_removes_old_jpegs_and_empty_date_folders(self) -> None:
        cutoff = self.local_time.astimezone(timezone.utc)
        old = self._picture("120000-ring.jpg", mtime=cutoff.timestamp() - 1, folder="2026-11-20")
        new = self._picture("130000-access-granted.jpg", mtime=cutoff.timestamp() + 1)
        boundary = self._picture("140000-ring.jpg", mtime=cutoff.timestamp())
        text = self._picture("other.txt", mtime=0)
        outside = self.root / "outside.jpg"
        outside.write_bytes(b"outside")
        other_entry = self.root / "2n_intercom" / "other" / "2026-11-20"
        other_entry.mkdir(parents=True)
        (other_entry / "old.jpg").write_bytes(b"other")
        link = self.device_dir / "2026-11-21" / "120000-ring.jpg"
        link.symlink_to(outside)
        date_link = self.device_dir / "2026-11-19"
        date_link.symlink_to(other_entry, target_is_directory=True)
        count = self.module.cleanup_pictures(self.device_dir, cutoff)
        self.assertEqual(count, 1)
        self.assertFalse(old.exists())
        self.assertFalse(old.parent.exists())
        for path in (new, boundary, text, outside, other_entry / "old.jpg", link, date_link):
            self.assertTrue(path.exists(), path.name)

    def test_cleanup_and_restore_never_follow_device_symlink(self) -> None:
        path = self._picture("120000-ring.jpg", mtime=0)
        link = self.root / "linked_device"
        link.symlink_to(self.device_dir, target_is_directory=True)
        self.assertEqual(self.module.cleanup_pictures(link, self.local_time), 0)
        self.assertIsNone(self.module.newest_ring_picture(link))
        self.assertTrue(path.exists())

    def test_cleanup_skips_file_errors_with_private_data_free_debug(self) -> None:
        path = self._picture("120000-ring.jpg", mtime=0)
        with (
            patch.object(Path, "unlink", side_effect=PermissionError("private-person")),
            self.assertLogs(self.module._LOGGER, level="DEBUG") as logs,
        ):
            self.assertEqual(self.module.cleanup_pictures(self.device_dir, self.local_time), 0)
        self.assertTrue(path.exists())
        self.assertNotIn("private-person", "\n".join(logs.output))
        self.assertNotIn(str(self.root), "\n".join(logs.output))

    def test_restore_uses_newest_ring_name_and_utc_file_time_not_access(self) -> None:
        self._picture("235959-ring.jpg", b"older", mtime=200, folder="2026-11-20")
        self._picture("143807-ring.jpg", b"first", mtime=300)
        self._picture("143807-ring-2.jpg", b"second", mtime=400)
        self._picture("143807-ring-10.jpg", b"newest", mtime=100)
        self._picture("235959-access-granted.jpg", b"access", mtime=500)
        self._picture("235959-access-denied.jpg", b"denied", mtime=600)
        self._picture("235959-ring-secret.jpg", b"not a ring", mtime=700)
        result = self.module.newest_ring_picture(self.device_dir)
        self.assertEqual(result, (b"newest", datetime.fromtimestamp(100, timezone.utc)))

    def test_restore_ignores_symlink_and_empty_files(self) -> None:
        path = self._picture("143807-ring.jpg", b"image", mtime=100)
        self._picture("143808-ring.jpg", b"")
        (path.parent / "143809-ring.jpg").symlink_to(path)
        self.assertEqual(self.module.newest_ring_picture(self.device_dir)[0], b"image")
        self.assertIsNone(self.module.newest_ring_picture(self.root / "missing"))


class PictureStoreTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_event_pictures_module()
        cls.dt = install_dt_util_stub()

    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.hass = ExecutorHass()
        self.store = self.module.EventPictureStore(
            self.hass, types.SimpleNamespace(title="../Front Door/"), self.root, 2
        )
        await self.store.async_initialize()

    async def test_all_file_io_is_in_executor_and_not_event_loop_thread(self) -> None:
        now = datetime(2026, 11, 21, 14, 38, 7, tzinfo=timezone.utc)
        with patch.object(self.dt, "now", return_value=now):
            await self.store.async_save("ring", b"jpeg")
        loaded = await self.store.async_load_newest_ring()
        self.assertEqual(loaded[0], b"jpeg")
        with patch.object(self.dt, "utcnow", return_value=now):
            await self.store.async_cleanup()
        self.assertEqual(
            [func.__name__ for func, _ in self.hass.executor_calls],
            ["is_writable", "_save_picture", "newest_ring_picture", "cleanup_pictures"],
        )
        self.assertTrue(all(thread != threading.get_ident() for thread in self.hass.executor_threads))
        self.assertEqual(
            self.hass.executor_calls[-1][1],
            (self.root / "2n_intercom" / "front_door", now - timedelta(days=2)),
        )

    async def test_reservation_is_monotonic_from_start_and_shared(self) -> None:
        with patch.object(self.module.time, "monotonic", side_effect=[0, 0, 9.99, 10, 19.9, 20]):
            self.assertEqual(
                [self.store.try_reserve() for _ in range(6)],
                [True, False, False, True, False, True],
            )

    async def test_missing_and_unwritable_roots_warn_once_and_disable(self) -> None:
        for root in (None, self.root / "missing", self.root):
            with self.subTest(root=root):
                store = self.module.EventPictureStore(
                    self.hass, types.SimpleNamespace(title="Private Visitor"), root, 1
                )
                with (
                    patch.object(self.module, "is_writable", return_value=False),
                    self.assertLogs(self.module._LOGGER, level="WARNING") as logs,
                ):
                    await store.async_initialize()
                    await store.async_initialize()
                    self.assertFalse(store.try_reserve())
                    await store.async_save("ring", b"jpeg")
                    await store.async_cleanup()
                    self.assertIsNone(await store.async_load_newest_ring())
                self.assertEqual(len(logs.records), 1)
                self.assertNotIn("Private Visitor", "\n".join(logs.output))
                self.assertNotIn(str(self.root), "\n".join(logs.output))

    async def test_write_oserror_logs_warning_without_private_error_text(self) -> None:
        with (
            patch.object(self.module, "write_picture", side_effect=OSError("secret card at private path")),
            self.assertLogs(self.module._LOGGER, level="WARNING") as logs,
        ):
            await self.store.async_save("ring", b"jpeg")
        self.assertEqual(len(logs.records), 1)
        self.assertNotIn("secret card", "\n".join(logs.output))
        self.assertNotIn(str(self.root), "\n".join(logs.output))
