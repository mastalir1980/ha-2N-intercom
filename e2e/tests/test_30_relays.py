"""PHYSICAL relay tests — they open real doors/gates. Run only manually: `make e2e-relays`.

Covers the full loop: HA service -> /api/switch/ctrl -> device relay ->
SwitchStateChanged event -> HA state, and the auto-off after the pulse.
"""

from __future__ import annotations

import pytest

from conftest import CFG
from test_10_entities import _relay_entities

ALLOWED = [int(x) for x in CFG.get("E2E_RELAY_NUMBERS", "").replace(" ", "").split(",") if x]


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
