"""Lifecycle: reloading the entry must bring everything back without errors."""

from __future__ import annotations

from test_00_setup import integration_errors


def test_reload_entry(ha, entry, registry):
    errors_before = len(integration_errors(ha))
    ha.reload_entry(entry["entry_id"])
    ha.wait_for(
        lambda: next((e for e in ha.entries() if e["entry_id"] == entry["entry_id"]), {}).get("state") == "loaded",
        timeout=60, what="entry loaded after reload",
    )
    enabled = [e["entity_id"] for e in registry if not e.get("disabled_by")]
    ha.wait_for(
        lambda: all(ha.state(eid)["state"] != "unavailable" for eid in enabled),
        timeout=60, what="entities available after reload",
    )
    assert len(integration_errors(ha)) == errors_before, "reload produced new integration errors"
