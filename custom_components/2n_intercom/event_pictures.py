"""Opt-in JPEG history in Home Assistant's local media directory."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
import logging
import os
from pathlib import Path
import re
import tempfile
import time
from typing import TYPE_CHECKING

from .const import EVENT_PICTURE_FOLDER, EVENT_PICTURE_MIN_INTERVAL

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
_KINDS = {"ring", "access-granted", "access-denied"}
_DATE_FOLDER = re.compile(r"\d{4}-\d{2}-\d{2}")
_RING_FILE = re.compile(r"(\d{6})-ring(?:-(\d+))?\.jpg")


def resolve_media_root(media_dirs: dict[str, str]) -> Path | None:
    """Prefer My media's local root, otherwise use an unambiguous root."""
    if "local" in media_dirs:
        return Path(media_dirs["local"]) if media_dirs["local"] else None
    if len(media_dirs) == 1:
        value = next(iter(media_dirs.values()))
        return Path(value) if value else None
    return None


def device_folder_name(title: str) -> str:
    """Make a credential-free, single ASCII path component from the title."""
    return re.sub(r"[^a-z0-9_-]+", "_", title.lower()).strip("_-") or "intercom"


def _has_symlink(path: Path) -> bool:
    return any(part.is_symlink() for part in (path, *path.parents))


def build_picture_path(
    root: Path, device_folder: str, kind: str, local_time: datetime
) -> Path:
    """Build a confined local-time JPEG path, avoiding same-second collisions."""
    if kind not in _KINDS:
        raise ValueError("Unknown event picture kind")
    if _has_symlink(root):
        raise ValueError("Event picture media root contains a symlink")
    base = root.resolve() / EVENT_PICTURE_FOLDER
    folder = base / device_folder_name(device_folder) / local_time.strftime("%Y-%m-%d")
    stem = f"{local_time:%H%M%S}-{kind}"
    path = folder / f"{stem}.jpg"
    suffix = 2
    while path.exists() or path.is_symlink():
        if path.is_symlink():
            raise ValueError("Event picture path contains a symlink")
        path = folder / f"{stem}-{suffix}.jpg"
        suffix += 1
    if _has_symlink(path) or not path.resolve().is_relative_to(base):
        raise ValueError("Event picture path escapes its media folder")
    return path


def write_picture(path: Path, data: bytes) -> bool:
    """Atomically write a JPEG; disk failures must not affect event handling."""
    temporary: Path | None = None
    try:
        if _has_symlink(path):
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=path.parent, suffix=".tmp", delete=False
        ) as file:
            temporary = Path(file.name)
            file.write(data)
        os.replace(temporary, path)
        temporary = None
        return True
    except OSError:
        return False
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                _LOGGER.debug("Could not remove an event picture temporary file")


def _picture_files(device_dir: Path) -> Iterator[Path]:
    """Walk regular JPEGs in date folders without following any symlinks."""
    if _has_symlink(device_dir) or not device_dir.is_dir():
        return
    for folder in device_dir.iterdir():
        try:
            if (
                folder.is_symlink()
                or not _DATE_FOLDER.fullmatch(folder.name)
                or not folder.is_dir()
            ):
                continue
            for path in folder.iterdir():
                if path.suffix == ".jpg" and not path.is_symlink() and path.is_file():
                    yield path
        except OSError:
            _LOGGER.debug("Could not scan an event picture date folder")


def cleanup_pictures(device_dir: Path, older_than: datetime) -> int:
    """Remove expired JPEGs and empty date folders in this entry only."""
    removed = 0
    try:
        for path in _picture_files(device_dir):
            try:
                if path.stat().st_mtime < older_than.timestamp():
                    path.unlink()
                    removed += 1
            except OSError:
                _LOGGER.debug("Could not remove an expired event picture")
        if _has_symlink(device_dir) or not device_dir.is_dir():
            return removed
        for folder in device_dir.iterdir():
            try:
                if (
                    not folder.is_symlink()
                    and _DATE_FOLDER.fullmatch(folder.name)
                    and folder.is_dir()
                ):
                    if not any(folder.iterdir()):
                        folder.rmdir()
            except OSError:
                _LOGGER.debug("Could not remove an empty event picture date folder")
    except OSError:
        _LOGGER.debug("Could not scan the event picture folder for retention")
    return removed


def newest_ring_picture(device_dir: Path) -> tuple[bytes, datetime] | None:
    """Read the newest named ring JPEG, using its mtime as tz-aware UTC."""
    try:
        candidates = [
            path for path in _picture_files(device_dir) if _RING_FILE.fullmatch(path.name)
        ]

        def picture_order(path: Path) -> tuple[str, str, int]:
            match = _RING_FILE.fullmatch(path.name)
            assert match is not None
            return path.parent.name, match[1], int(match[2] or 1)

        for path in sorted(candidates, key=picture_order, reverse=True):
            try:
                data = path.read_bytes()
                if data:
                    return data, datetime.fromtimestamp(
                        path.stat().st_mtime, timezone.utc
                    )
            except OSError:
                _LOGGER.debug("Could not read a saved ring picture")
    except OSError:
        _LOGGER.debug("Could not scan the saved ring pictures")
    return None


def is_writable(root: Path) -> bool:
    """Probe an existing media directory, without leaving a probe file behind."""
    try:
        if _has_symlink(root) or not root.is_dir():
            return False
        with tempfile.TemporaryFile(dir=root):
            pass
        return True
    except OSError:
        return False


def _save_picture(
    root: Path, folder: str, kind: str, local_time: datetime, data: bytes
) -> bool:
    try:
        return write_picture(build_picture_path(root, folder, kind, local_time), data)
    except (OSError, ValueError):
        return False


class EventPictureStore:
    """Executor-only storage with one shared capture reservation per entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        media_root: Path | None,
        retention_days: int,
    ) -> None:
        self.hass = hass
        self.media_root = media_root
        self.device_folder = device_folder_name(entry.title)
        self.retention_days = retention_days
        self.enabled = False
        self._initialized = False
        self._last_capture: float | None = None

    async def async_initialize(self) -> None:
        """Disable unavailable storage, warning only once for this setup."""
        if self._initialized:
            return
        self._initialized = True
        self.enabled = (
            self.media_root is not None
            and await self.hass.async_add_executor_job(is_writable, self.media_root)
        )
        if not self.enabled:
            _LOGGER.warning("Event pictures disabled: no writable Home Assistant media folder")

    def try_reserve(self) -> bool:
        """Reserve before requesting a snapshot, never after its completion."""
        if not self.enabled:
            return False
        now = time.monotonic()
        if (
            self._last_capture is not None
            and now - self._last_capture < EVENT_PICTURE_MIN_INTERVAL
        ):
            return False
        self._last_capture = now
        return True

    async def async_save(self, kind: str, data: bytes) -> None:
        """Save without exposing paths, credentials, or OS error text in logs."""
        if not self.enabled or self.media_root is None:
            return
        from homeassistant.util import dt as dt_util

        try:
            saved = await self.hass.async_add_executor_job(
                _save_picture, self.media_root, self.device_folder,
                kind, dt_util.now(), data,
            )
        except OSError:
            saved = False
        if not saved:
            _LOGGER.warning("Could not save an event picture")

    async def async_cleanup(self, _now: datetime | None = None) -> None:
        """Apply retention outside the event loop."""
        if not self.enabled or self.media_root is None:
            return
        from homeassistant.util import dt as dt_util

        await self.hass.async_add_executor_job(
            cleanup_pictures,
            self.media_root / EVENT_PICTURE_FOLDER / self.device_folder,
            dt_util.utcnow() - timedelta(days=self.retention_days),
        )

    async def async_load_newest_ring(self) -> tuple[bytes, datetime] | None:
        """Restore the image cache without using access pictures."""
        if not self.enabled or self.media_root is None:
            return None
        return await self.hass.async_add_executor_job(
            newest_ring_picture, self.media_root / EVENT_PICTURE_FOLDER / self.device_folder
        )
