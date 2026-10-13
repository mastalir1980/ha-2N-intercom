"""Capture raw call events from the intercom log channel (read-only).

Prints event name, state, direction, session and peer for every
CallStateChanged / CallSessionStateChanged event, so we can see what the
device really sends for a button press vs. a call *to* the intercom.
Does not touch relays. Reads INTERCOM_* from e2e/.env, never prints secrets.

Usage (from repo root):  e2e/.venv/bin/python e2e/scripts/capture_call_events.py [seconds]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from e2elib.twon import TwoN  # noqa: E402

EVENTS = ["CallStateChanged", "CallSessionStateChanged"]
KEYS = ("state", "status", "direction", "session", "sessionNumber", "peer", "address", "originator", "info", "reason")


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main() -> None:
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    env = load_env(ROOT / ".env")
    twon = TwoN(
        env["INTERCOM_HOST"],
        env["INTERCOM_USER"],
        env["INTERCOM_PASSWORD"],
        protocol=env.get("INTERCOM_PROTOCOL", "https") or "https",
        verify=env.get("INTERCOM_VERIFY_SSL", "false").lower() in ("1", "true", "yes"),
    )
    caps = twon.log_caps()
    events = [e for e in EVENTS if e in caps]
    print(f"device log caps include: {events} (missing: {[e for e in EVENTS if e not in caps]})")
    sub = twon.log_subscribe(events)
    print(f"listening {duration}s — now (a) press the call button, wait, hang up; "
          f"then (b) call the intercom from My2N/SIP phone. Ctrl+C to stop.\n")
    end = time.time() + duration
    try:
        while time.time() < end:
            for ev in twon.log_pull(sub, timeout=5):
                params = ev.get("params") or {}
                picked = {k: params[k] for k in KEYS if k in params}
                extra = sorted(set(params) - set(KEYS))
                print(f"{time.strftime('%H:%M:%S')} {ev.get('event'):<24} {json.dumps(picked)}"
                      + (f"  other_keys={extra}" if extra else ""))
    except KeyboardInterrupt:
        pass
    finally:
        twon.log_unsubscribe(sub)
        print("\nunsubscribed")


if __name__ == "__main__":
    main()
