"""PHYSICAL relay tests — they open real doors/gates. Run only manually: `make e2e-relays`.

Covers the full loop: HA service -> /api/switch/ctrl -> device relay ->
SwitchStateChanged event -> HA state, and the auto-off after the pulse.
Explicitly allowed physical IO outputs instead latch on until turned off;
their tests always turn them off in finally.
"""

from __future__ import annotations

import pytest

from conftest import CFG
from test_10_entities import _io_output_entities, _io_port_on, _relay_entities

ALLOWED = [int(x) for x in CFG.get("E2E_RELAY_NUMBERS", "").replace(" ", "").split(",") if x]
ALLOWED_IO_OUTPUTS = list(dict.fromkeys(
    port.strip() for port in CFG.get("E2E_IO_OUTPUTS", "").split(",") if port.strip()
))


@pytest.mark.relay
@pytest.mark.parametrize("number", ALLOWED or [pytest.param(0, marks=pytest.mark.skip("E2E_RELAY_NUMBERS empty"))])
def test_relay_roundtrip(ha, registry, entry, twon, number):
    ent = _relay_entities(registry, entry["entry_id"]).get(number)
    if ent is None:
        pytest.fail(f"no switch entity for relay {number}")
    eid = ent["entity_id"]
    assert not twon.relay_active(number), "relay already active before the test"

    ha.call_service("switch", "turn_on", {"entity_id": eid})

    ha.wait_for(lambda: twon.relay_active(number), timeout=3, what=f"device relay {number} active")
    ha.wait_for(lambda: ha.state(eid)["state"] == "on", timeout=3, what=f"{eid} on in HA (event path)")
    ha.wait_for(lambda: not twon.relay_active(number), timeout=30, what=f"device relay {number} released")
    ha.wait_for(lambda: ha.state(eid)["state"] == "off", timeout=10, what=f"{eid} back off in HA")


@pytest.mark.relay
@pytest.mark.parametrize(
    "port",
    ALLOWED_IO_OUTPUTS or [pytest.param("", marks=pytest.mark.skip("E2E_IO_OUTPUTS empty"))],
)
def test_io_output_roundtrip(ha, registry, entry, twon, port):
    """PHYSICAL: latch only explicitly allowed outputs on, then always release them."""
    assert port != "led_secured", "E2E_IO_OUTPUTS must not include the device-managed led_secured"
    outputs = {
        cap["port"]
        for cap in twon.io_caps()
        if isinstance(cap, dict)
        and cap.get("type") == "output"
        and isinstance(cap.get("port"), str)
        and cap["port"]
    }
    assert port in outputs, f"E2E_IO_OUTPUTS port {port!r} is not an output in /api/io/caps"

    def device_on():
        status = next(
            (p for p in twon.io_status() if isinstance(p, dict) and p.get("port") == port),
            None,
        )
        assert status is not None, f"E2E_IO_OUTPUTS port {port!r} is absent from /api/io/status"
        return _io_port_on(status)

    initially_on = device_on()
    ent = _io_output_entities(registry, entry["entry_id"]).get(port)
    assert ent is not None, f"no switch entity with unique ID {entry['entry_id']}_io_{port}"
    eid = ent["entity_id"]
    assert eid.startswith("switch."), f"physical output {port} is not a switch: {eid}"
    if ent.get("disabled_by"):
        pytest.skip(
            f"{eid} disabled_by={ent['disabled_by']!r}; manually enable this IO output "
            "in HA Settings > Devices & services > Entities before rerunning with --relays "
            "(direct output control bypasses logical relay timing)"
        )
    assert not initially_on, f"IO output {port} already on before the test; refusing to actuate it"
    assert ha.state(eid)["state"] == "off", f"{eid} is not off in HA before the test"

    try:
        ha.call_service("switch", "turn_on", {"entity_id": eid})
        ha.wait_for(device_on, timeout=3, what=f"device IO output {port} on")
        ha.wait_for(lambda: ha.state(eid)["state"] == "on", timeout=3, what=f"{eid} on in HA")
    finally:
        # Even a failed turn_on request may have reached the device.
        ha.call_service("switch", "turn_off", {"entity_id": eid})
        ha.wait_for(lambda: not device_on(), timeout=3, what=f"device IO output {port} off")
        ha.wait_for(lambda: ha.state(eid)["state"] == "off", timeout=10, what=f"{eid} off in HA")
