"""Read-only SSDP identity and HA MAC-backfill checks."""

from __future__ import annotations

import json
from pathlib import Path


def test_ssdp_identity_matches_manifest_and_device(twon):
    manifest_path = (
        Path(__file__).resolve().parents[2]
        / "custom_components" / "2n_intercom" / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    description = twon.ssdp_description()
    manufacturers = {matcher["manufacturer"] for matcher in manifest["ssdp"]}
    assert description["manufacturer"] in manufacturers, (
        "device SSDP manufacturer does not match the HA discovery matcher"
    )

    info = twon.system_info()
    announced_mac = description["serialNumber"].replace(":", "").replace("-", "").strip().upper()
    api_mac = str(info.get("macAddr", "")).replace(":", "").replace("-", "").strip().upper()
    identities_match = bool(announced_mac) and bool(api_mac) and announced_mac == api_mac
    # Assert only a boolean so pytest never renders either private identifier.
    assert identities_match, "SSDP identity does not match the device API MAC"


def test_entry_diagnostics_contains_redacted_mac(ha, entry):
    diagnostics = ha.get_json(f"/api/diagnostics/config_entry/{entry['entry_id']}")
    entry_data = diagnostics["data"]["entry"]["data"]
    mac_present = "mac_address" in entry_data
    assert mac_present, "HA entry has no MAC address after setup/backfill"
    mac_redacted = entry_data["mac_address"] == "**REDACTED**"
    assert mac_redacted, "HA entry diagnostics expose the MAC address"
