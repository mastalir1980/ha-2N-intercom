"""Detect entity-registry entries orphaned by a previous deploy of a different branch.

Staging HA is shared by all branches. When a branch with an extra platform (e.g. `lock.py`)
was deployed, its entities stay in the registry after the next deploy and HA restores them
as `unavailable` with `restored: true`. Such an entry is an orphan only when the deployed
code has no platform module for its domain at all — restored entities of a platform that
still exists are a real regression and must stay visible to the tests.

Pure functions, no third-party imports, so they are unit-testable offline.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

NON_PLATFORM_MODULES = {"__init__"}


def platform_domains(file_names: Iterable[str]) -> set[str]:
    """Return entity domains that have a `<domain>.py` module in the integration dir."""
    out: set[str] = set()
    for name in file_names:
        base = name.rsplit("/", 1)[-1]
        if base.endswith(".py"):
            stem = base[:-3]
            if stem and stem not in NON_PLATFORM_MODULES:
                out.add(stem)
    return out


def select_orphans(
    registry: Iterable[dict[str, Any]],
    states: dict[str, dict[str, Any]],
    entry_id: str,
    domains: set[str],
) -> list[dict[str, Any]]:
    """Registry entries of `entry_id` that HA restored and whose domain has no platform."""
    orphans: list[dict[str, Any]] = []
    for ent in registry:
        if ent.get("config_entry_id") != entry_id:
            continue
        entity_id = ent.get("entity_id") or ""
        domain = entity_id.split(".", 1)[0]
        if not domain or domain in domains:
            continue
        state = states.get(entity_id)
        if not state or (state.get("attributes") or {}).get("restored") is not True:
            continue
        orphans.append(ent)
    return orphans


def restored_kept(
    registry: Iterable[dict[str, Any]],
    states: dict[str, dict[str, Any]],
    entry_id: str,
    domains: set[str],
) -> list[str]:
    """Restored entities of `entry_id` that are kept because their platform exists."""
    return [
        ent["entity_id"]
        for ent in registry
        if ent.get("config_entry_id") == entry_id
        and (ent.get("entity_id") or "").split(".", 1)[0] in domains
        and ((states.get(ent["entity_id"]) or {}).get("attributes") or {}).get("restored") is True
    ]
