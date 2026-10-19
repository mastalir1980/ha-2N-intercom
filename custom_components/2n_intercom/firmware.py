"""Read-only, unauthenticated checks of the public 2N firmware catalog."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import quote

import aiohttp

from .const import FIRMWARE_CHANNEL_TRACKS, FIRMWARE_UPDATE_SERVER_URL


class FirmwareCheckError(Exception):
    """The catalog could not be reached or returned an invalid response."""


@dataclass(frozen=True)
class FirmwareRelease:
    """Only the public version and notes, never download URLs or tokens."""

    version: str
    release_notes: str


async def check(
    session: aiohttp.ClientSession,
    package: str,
    track: str,
    current_ver: str,
    lang: str = "en",
) -> FirmwareRelease | None:
    """Return a matching release, or None when the installed version is current."""
    if track not in FIRMWARE_CHANNEL_TRACKS.values():
        raise FirmwareCheckError("Invalid firmware track")
    if not package.strip() or not current_ver.strip():
        raise FirmwareCheckError("Missing firmware package or installed version")
    url = f"{FIRMWARE_UPDATE_SERVER_URL}/{quote(package, safe='')}/{track}/"
    try:
        async with asyncio.timeout(30):
            async with session.get(
                url,
                params={"current_ver": current_ver, "ui_lang": lang},
                allow_redirects=False,
            ) as response:
                if response.status == 204:
                    return None
                if response.status != 200:
                    raise FirmwareCheckError(
                        f"Firmware server returned HTTP {response.status}"
                    )
                payload = await response.json()
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        # Exception text can include response URLs; never propagate it to logs.
        raise FirmwareCheckError("Firmware server request failed") from err

    if not isinstance(payload, dict):
        raise FirmwareCheckError("Invalid firmware response")
    version = payload.get("version")
    release_type = payload.get("type")
    changelog = payload.get("changelog.md")
    flag = "lts" if track == "lts" else "stable"
    if (
        not isinstance(version, str)
        or not version.strip()
        or not isinstance(release_type, dict)
        or not isinstance(release_type.get(flag), bool)
        or not isinstance(changelog, list)
    ):
        raise FirmwareCheckError("Invalid firmware release metadata")
    notes: list[str] = []
    # The server lists the intervening releases oldest first, like the device UI.
    for item in reversed(changelog):
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("version"), str)
            or not isinstance(item.get("text"), str)
        ):
            raise FirmwareCheckError("Invalid firmware release notes")
        notes.append(item["text"])
    matches = release_type[flag] is (track != "early")
    if not matches:
        return None
    return FirmwareRelease(version.strip(), "\n\n".join(notes))
