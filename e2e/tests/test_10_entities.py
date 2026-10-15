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


def _io_output_entities(registry, entry_id):
    prefix = f"{entry_id}_io_"
    return {
        ent["unique_id"][len(prefix):]: ent
        for ent in registry
        if ent.get("unique_id", "").startswith(prefix)
        and ent["entity_id"].startswith("switch.")
    }


def _io_port_on(port):
    return port.get("state") in (1, True, "1", "on", "true")


def test_io_output_entities_match_device(ha, registry, entry, twon):
    device = {
        port["port"]: port
        for port in twon.io_status()
        if isinstance(port, dict) and isinstance(port.get("port"), str)
    }
    outputs = {
        cap["port"]
        for cap in twon.io_caps()
        if isinstance(cap, dict)
        and cap.get("type") == "output"
        and isinstance(cap.get("port"), str)
        and cap["port"]
        and cap["port"] != "led_secured"
    }
    missing_status = outputs - set(device)
    entities = _io_output_entities(registry, entry["entry_id"])
    expected_ids = {f"{entry['entry_id']}_io_{port}" for port in outputs}
    actual_ids = {ent["unique_id"] for ent in entities.values()}
    assert actual_ids == expected_ids, (
        f"HA IO output unique IDs {sorted(actual_ids)} != device outputs {sorted(expected_ids)}; "
        f"caps outputs absent from /api/io/status: {sorted(missing_status)} "
        "(integration discovery legitimately requires both caps and status)"
    )
    assert not missing_status, (
        f"caps outputs absent from /api/io/status: {sorted(missing_status)}; "
        "integration discovery legitimately requires both caps and status"
    )
    for port, ent in entities.items():
        eid = ent["entity_id"]
        assert eid.startswith("switch."), f"physical output {port} is not a switch: {eid}"
        disabled_by = ent.get("disabled_by")
        if disabled_by is not None:
            assert disabled_by == "integration", (
                f"{eid}: disabled_by={disabled_by!r}, expected 'integration' for disabled "
                "physical outputs; a user disable does not verify the integration's default"
            )
            continue
        expected = "on" if _io_port_on(device[port]) else "off"
        state = ha.state(eid)["state"]
        assert state == expected, f"IO output {port}: HA={state} device={expected}"


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


def test_io_input_entities_match_device(ha, registry, entry, twon):
    device = {
        port["port"]: port
        for port in twon.io_status()
        if isinstance(port, dict) and isinstance(port.get("port"), str)
    }
    inputs = {
        cap["port"]
        for cap in twon.io_caps()
        if isinstance(cap, dict)
        and cap.get("type") == "input"
        and isinstance(cap.get("port"), str)
        and cap["port"]
        and cap["port"] in device
    }
    entry_id = entry["entry_id"]
    expected_ids = {
        f"{entry_id}_input1" if port == "input1" else f"{entry_id}_io_{port}": port
        for port in inputs
    }
    entities = {
        ent["unique_id"]: ent
        for ent in registry
        if ent["entity_id"].startswith("binary_sensor.")
        and (
            ent.get("unique_id") == f"{entry_id}_input1"
            or ent.get("unique_id", "").startswith(f"{entry_id}_io_")
        )
    }
    assert set(entities) == set(expected_ids), (
        f"HA input unique IDs {sorted(entities)} != device inputs {sorted(expected_ids)}"
    )
    for uid, port in expected_ids.items():
        ent = entities[uid]
        assert not ent.get("disabled_by"), f"input {port} is disabled: {ent['disabled_by']}"
        expected = "on" if _io_port_on(device[port]) else "off"
        state = ha.state(ent["entity_id"])["state"]
        assert state == expected, f"IO input {port}: HA={state} device={expected}"
