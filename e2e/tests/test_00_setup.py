"""Does the freshly deployed integration load cleanly and identify the device?"""

from __future__ import annotations

OWN_LOGGERS = ("custom_components.2n_intercom",)


def integration_errors(ha) -> list[dict]:
    errors = []
    for rec in ha.system_log():
        if rec.get("level") not in ("ERROR", "CRITICAL"):
            continue
        text = " ".join(str(m) for m in rec.get("message", [])) + " " + str(rec.get("exception", ""))
        if rec.get("name", "").startswith(OWN_LOGGERS) or "2n_intercom" in text:
            errors.append(rec)
    return errors


def test_config_entry_loaded(entry):
    assert entry["state"] == "loaded", f"entry state={entry['state']} reason={entry.get('reason')}"


def test_no_integration_errors_in_log(ha):
    errors = integration_errors(ha)
    summary = [
        f"{e.get('level')} {e.get('name')}: {(e.get('message') or [''])[0][:200]} (x{e.get('count', 1)})"
        for e in errors
    ]
    assert not errors, "integration logged errors:\n" + "\n".join(summary)


def test_device_registry_matches_device(ha, entry, twon):
    info = twon.system_info()
    devices = ha.devices(entry["entry_id"])
    assert len(devices) == 1, f"expected one device, got {len(devices)}"
    dev = devices[0]
    assert dev.get("sw_version") == info.get("swVersion"), "firmware in HA differs from device"
    if info.get("serialNumber"):
        assert dev.get("serial_number") == str(info["serialNumber"])


def test_services_registered(ha):
    services = {s["domain"]: s["services"] for s in ha.get_json("/api/services")}
    assert "2n_intercom" in services, "integration services not registered"
    for name in ("answer_call", "hangup_call"):
        assert name in services["2n_intercom"], f"service 2n_intercom.{name} missing"


def test_device_accepts_integration_requests(ha):
    """The integration must actually get data, not just 'load'.

    2N answers e.g. code 7 'invalid connection type' (service needs HTTPS) or
    auth errors; the integration only logs these as WARNING and stays 'available',
    so without this test a silently dead integration would look green.
    """
    rejected = [
        rec for rec in ha.system_log()
        if rec.get("name", "").startswith("custom_components.2n_intercom")
        and any("rejected by device" in str(m) for m in rec.get("message", []))
    ]
    lines = [str(m)[:160] for rec in rejected for m in rec.get("message", [])][:8]
    assert not rejected, "device rejects the integration's requests:\n" + "\n".join(lines)
