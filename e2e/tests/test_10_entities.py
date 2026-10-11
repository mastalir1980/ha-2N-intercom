"""Read-only checks: HA entities mirror the real device state (safe for nightly runs)."""

from __future__ import annotations

import re

import pytest

from conftest import find_by_suffix


def enabled(registry):
    return [e for e in registry if not e.get("disabled_by")]


def test_entities_available(ha, registry):
    assert registry, "integration created no entities"
    bad = {}
    for ent in enabled(registry):
        st = ha.state(ent["entity_id"])["state"]
        if st == "unavailable":
            bad[ent["entity_id"]] = st
    assert not bad, f"unavailable entities: {bad}"


def test_camera_snapshot_is_jpeg(ha, entry, registry):
    cam = find_by_suffix(registry, entry["entry_id"], "camera")
    if cam is None or cam.get("disabled_by"):
        pytest.skip("camera entity not enabled")
    r = ha.get(f"/api/camera_proxy/{cam['entity_id']}")
    assert r.status_code == 200, f"camera_proxy -> {r.status_code}"
    assert r.content[:2] == b"\xff\xd8", "snapshot is not a JPEG"
    assert len(r.content) > 5_000, f"snapshot suspiciously small ({len(r.content)} B)"


def _relay_entities(registry, entry_id):
    pat = re.compile(rf"^{re.escape(entry_id)}_switch_(\d+)$")
    out = {}
    for e in registry:
        m = pat.match(e.get("unique_id", ""))
        if m:
            out[int(m.group(1))] = e
    return out


def test_switch_entities_match_device_caps(registry, entry, twon):
    device_relays = {c["switch"] for c in twon.switch_caps() if c.get("enabled")}
    ha_relays = set(_relay_entities(registry, entry["entry_id"]))
    assert ha_relays == device_relays, f"HA relays {sorted(ha_relays)} != device {sorted(device_relays)}"


def test_switch_state_matches_device(ha, registry, entry, twon):
    device = {s["switch"]: bool(s.get("active")) for s in twon.switch_status()}
    for number, ent in _relay_entities(registry, entry["entry_id"]).items():
        if ent.get("disabled_by"):
            continue
        st = ha.state(ent["entity_id"])["state"]
        assert (st == "on") == device.get(number, False), f"relay {number}: HA={st} device={device.get(number)}"


def test_sip_registration_matches_device(ha, registry, twon):
    ent = next((e for e in registry if e.get("unique_id", "").endswith("sip_registration")), None)
    if ent is None or ent.get("disabled_by"):
        pytest.skip("SIP registration sensor not enabled")
    accounts = [a for a in twon.phone_status() if a.get("registrationEnabled")]
    if not accounts:
        expected = "disabled"
    else:
        expected = "registered" if any(a.get("registered") for a in accounts) else "unregistered"
    assert ha.state(ent["entity_id"])["state"] == expected


def test_input1_matches_device(ha, registry, entry, twon):
    ent = find_by_suffix(registry, entry["entry_id"], "input1")
    if ent is None or ent.get("disabled_by"):
        pytest.skip("input1 sensor not enabled")
    port = next((p for p in twon.io_status() if p.get("port") == "input1"), None)
    if port is None:
        pytest.skip("device has no input1")
    expected = "on" if port.get("state") in (1, True, "1", "on", "true") else "off"
    assert ha.state(ent["entity_id"])["state"] == expected
