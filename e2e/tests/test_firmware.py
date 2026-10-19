"""Read-only firmware comparison: HA <-> device info <-> public 2N catalog."""
from __future__ import annotations

from urllib.parse import quote, urlsplit

import requests

from conftest import find_by_suffix


def _catalog_latest_version(package: str, channel: str, installed: str) -> str:
    """Check the public server independently of the integration's parser."""
    track = {"active_track": "newest", "lts": "lts", "beta": "early"}[channel]
    url = f"https://update.2n.cz/hip/{quote(package, safe='')}/{track}/"
    # Never reuse HA/2N clients or implicit netrc credentials for this public GET.
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(
            url,
            params={"current_ver": installed, "ui_lang": "en"},
            timeout=30,
            allow_redirects=False,
        )
    if response.status_code == 204:
        return installed
    assert response.status_code == 200, "public firmware catalog did not return 200/204"
    payload = response.json()
    assert isinstance(payload, dict), "public firmware catalog returned invalid JSON"
    flags = payload.get("type")
    assert isinstance(flags, dict), "public firmware catalog is missing release type"
    flag = flags.get("lts" if track == "lts" else "stable")
    assert isinstance(flag, bool), "public firmware catalog has an invalid release type"
    if flag != (track != "early"):
        return installed
    version = payload.get("version")
    assert isinstance(version, str) and version.strip(), "catalog version is missing"
    return version.strip()


def test_firmware_versions_and_device_web_ui_link(ha, twon, entry, registry):
    """Compare versions without downloading firmware or calling device updates."""
    info = twon.system_info()
    entity = find_by_suffix(registry, entry["entry_id"], "firmware")
    if not info.get("firmwarePackage"):
        assert entity is None, "firmware entity must not exist without firmwarePackage"
        return
    assert entity is not None, "firmware update entity was not created"
    assert entity["entity_id"].startswith("update.")
    assert not entity.get("disabled_by"), "firmware update entity is disabled"
    assert len([item for item in registry if item["entity_id"].startswith("update.")]) == 1

    diagnostics = ha.get_json(f"/api/diagnostics/config_entry/{entry['entry_id']}")["data"]
    channel = diagnostics["entry"]["options"].get("firmware_channel", "active_track")
    expected_latest = _catalog_latest_version(
        info["firmwarePackage"], channel, info["swVersion"]
    )
    ha.call_service("homeassistant", "update_entity", {"entity_id": entity["entity_id"]})
    state = ha.state(entity["entity_id"])
    attributes = state["attributes"]
    assert state["state"] not in ("unavailable", "unknown"), "firmware state is not available"
    installed_matches = attributes.get("installed_version") == info["swVersion"]
    latest_matches = attributes.get("latest_version") == expected_latest
    # Boolean assertions avoid exposing the E2E device's exact firmware build.
    assert installed_matches, "HA installed firmware differs from the independent device API"
    assert latest_matches, "HA latest firmware differs from the independent public catalog"
    assert attributes["device_class"] == "firmware"
    assert attributes["supported_features"] == 16, "only RELEASE_NOTES may be supported"
    release_url = attributes["release_url"]
    parsed = urlsplit(release_url)
    configured_host = diagnostics["entry"]["data"]["host"].strip("[]")
    host_matches = parsed.hostname == configured_host.lower()
    assert host_matches, "release link does not point to the configured intercom"
    assert parsed.username is None and parsed.password is None
    device = next(device for device in ha.devices(entry["entry_id"]) if device["id"] == entity["device_id"])
    links_match = device.get("configuration_url") == release_url
    assert links_match, "device page and update entity must link to the same web UI"
