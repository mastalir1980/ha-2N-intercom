"""Access control (TASK-4/8) and last-ring image (TASK-9): HA says X <-> 2N API says X.

Each test skips when the deployed integration lacks the feature (no
``access_control`` diagnostics section, no ``image`` platform, no
``grant_access`` service), so the suite stays green on branches without it.
"""

from __future__ import annotations

import time

import pytest

from conftest import CFG, find_by_suffix

# Kept independent of the integration's const.py on purpose (ground truth side).
ACCESS_EVENTS = {
    "CardEntered",
    "CodeEntered",
    "MobKeyEntered",
    "FingerEntered",
    "UserAuthenticated",
    "UserRejected",
    "AccessTaken",
    "AccessBlocked",
    "AccessLimited",
    "ApiAccessRequested",
}


def _diagnostics(ha, entry_id: str) -> dict:
    return ha.get_json(f"/api/diagnostics/config_entry/{entry_id}")["data"]


def test_subscribed_access_events_match_device_log_caps(ha, entry, twon):
    if "access_control" not in _diagnostics(ha, entry["entry_id"]):
        pytest.skip("deployed integration has no access_control diagnostics (TASK-8 not deployed)")
    device_supported = ACCESS_EVENTS & set(twon.log_caps())

    def subscribed():
        events = _diagnostics(ha, entry["entry_id"]).get("access_control", {}).get("subscribed_events")
        return events if events else None

    events = ha.wait_for(subscribed, timeout=60, what="log subscription reported in diagnostics")
    assert ACCESS_EVENTS & set(events) == device_supported, (
        f"HA subscribed {sorted(ACCESS_EVENTS & set(events))}, "
        f"device log/caps supports {sorted(device_supported)}"
    )
    if "DirectoryChanged" in twon.log_caps():
        assert "DirectoryChanged" in events


def test_last_ring_image_follows_camera(ha, entry, registry):
    # HA records each set-up entity platform as "<integration>.<platform>".
    if "2n_intercom.image" not in ha.config().get("components", []):
        pytest.skip("deployed integration has no image platform (TASK-9 not deployed)")
    cam = find_by_suffix(registry, entry["entry_id"], "camera")
    image = find_by_suffix(registry, entry["entry_id"], "last_ring")
    if cam is None:
        assert image is None, "last-ring image exists although the camera is disabled"
        return
    assert image is not None, "camera enabled but no last-ring image entity"
    if image.get("disabled_by"):
        pytest.skip("last-ring image entity disabled")
    assert image["entity_id"].startswith("image.")
    assert ha.state(image["entity_id"])["state"] != "unavailable"


@pytest.mark.relay
def test_grant_access_is_logged_by_device(ha, entry, twon):
    """PHYSICAL: opens access point 0. Run only manually with --relays."""
    user = CFG.get("E2E_GRANT_USER_UUID", "").strip()
    if not user:
        pytest.skip("E2E_GRANT_USER_UUID not set")
    services = {s.get("domain"): s.get("services", {}) for s in ha.get_json("/api/services")}
    if "grant_access" not in services.get("2n_intercom", {}):
        pytest.skip("deployed integration has no grant_access service (TASK-4 not deployed)")
    if "ApiAccessRequested" not in twon.log_caps():
        pytest.skip("device does not report ApiAccessRequested in log/caps")

    sub_id = twon.log_subscribe(["ApiAccessRequested"])
    try:
        ha.call_service(
            "2n_intercom",
            "grant_access",
            {"config_entry_id": entry["entry_id"], "access_point": 0, "user": user},
        )
        deadline = time.monotonic() + 10
        events: list[dict] = []
        while time.monotonic() < deadline and not events:
            events = [e for e in twon.log_pull(sub_id, timeout=2) if e.get("event") == "ApiAccessRequested"]
        assert events, "device logged no ApiAccessRequested after HA grant_access"
        # Documented params: "ap, valid" always, "session, uuid" conditionally.
        params = events[-1].get("params", {})
        assert str(params.get("ap")) == "0"
        assert str(params.get("valid")).lower() == "true"
        if params.get("uuid"):
            assert str(params["uuid"]).lower() == user.lower()
    finally:
        twon.log_unsubscribe(sub_id)
