#!/usr/bin/env python3
"""Remove entity-registry entries left behind by another branch's deploy (staging only).

Run after deploy + HA restart, before pytest. Removes entries of the e2e 2N config entry
that HA restored (`restored: true`) and whose domain has no platform module in the
deployed code. Restored entities of an existing platform are kept, so a real regression
still fails `test_entities_available`.

    prune_orphans.py (--ref <git-ref> | --worktree) [--out <file.json>] [--wait <seconds>]

Exit code: 0 ok (also when nothing was pruned), 1 HA/git error (details in the JSON).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from e2elib import env  # noqa: E402
from e2elib.ha import HA  # noqa: E402
from e2elib.orphans import platform_domains, restored_kept, select_orphans  # noqa: E402

REPO_DIR = env.E2E_DIR.parent
COMPONENT = "custom_components/2n_intercom"


def deployed_files(ref: str | None, worktree: bool) -> list[str]:
    if worktree:
        return [p.name for p in (REPO_DIR / COMPONENT).iterdir() if p.is_file()]
    out = subprocess.run(
        ["git", "-C", str(REPO_DIR), "ls-tree", "--name-only", f"{ref}:{COMPONENT}"],
        check=True, capture_output=True, text=True,
    )
    return out.stdout.split()


def wait_loaded(ha: HA, timeout: float) -> list[dict]:
    deadline = time.monotonic() + timeout
    entries = ha.entries()
    while time.monotonic() < deadline:
        if entries and all(e.get("state") == "loaded" for e in entries):
            return entries
        time.sleep(3)
        entries = ha.entries()
    return entries


def prune(ref: str | None, worktree: bool, wait: float) -> dict:
    cfg = env.load()
    env.assert_staging_url(cfg["HA_URL"])
    ha = HA(cfg["HA_URL"], cfg.get("HA_TOKEN"))
    result: dict = {"source": "worktree" if worktree else ref, "pruned": []}

    domains = platform_domains(deployed_files(ref, worktree))
    result["platform_domains"] = sorted(domains)

    entries = wait_loaded(ha, wait)
    if len(entries) != 1:
        result["skipped"] = f"expected exactly one 2N config entry on staging, got {len(entries)}"
        return result
    entry = entries[0]
    result["entry_id"] = entry["entry_id"]
    result["entry_state"] = entry.get("state")
    if entry.get("state") != "loaded":
        print(f"[prune] warning: 2N entry is {entry.get('state')!r}, not 'loaded' after {wait:.0f}s")

    registry = ha.entity_registry()
    states = {s["entity_id"]: s for s in ha.get_json("/api/states")}
    for ent in select_orphans(registry, states, entry["entry_id"], domains):
        ha.ws({"type": "config/entity_registry/remove", "entity_id": ent["entity_id"]})
        result["pruned"].append(ent["entity_id"])
        print(f"[prune] removed orphaned {ent['entity_id']} (no {ent['entity_id'].split('.', 1)[0]}.py deployed)")
    result["restored_kept"] = restored_kept(registry, states, entry["entry_id"], domains)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--ref", help="git ref that was deployed")
    src.add_argument("--worktree", action="store_true", help="the working tree was deployed")
    ap.add_argument("--out", type=Path, help="write the result as JSON here")
    ap.add_argument("--wait", type=float, default=120, help="seconds to wait for the entry to load")
    args = ap.parse_args()

    rc = 0
    try:
        result = prune(args.ref, args.worktree, args.wait)
    except Exception as err:  # noqa: BLE001 — pruning must never abort the pipeline; logged + in JSON
        result = {"source": "worktree" if args.worktree else args.ref, "pruned": [], "error": str(err)}
        print(f"[prune] error: {err}")
        rc = 1
    if not result.get("error"):
        print(f"[prune] pruned: {result['pruned'] or 'nothing'}")
        if result.get("skipped"):
            print(f"[prune] skipped: {result['skipped']}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(main())
