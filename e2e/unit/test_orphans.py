"""Offline tests for e2elib.orphans (no HA, no network).

    python3 -m unittest discover -s e2e/unit -t e2e
"""

from __future__ import annotations

import unittest

from e2elib.orphans import platform_domains, restored_kept, select_orphans

ENTRY = "entry1"


def reg(entity_id: str, entry_id: str = ENTRY) -> dict:
    return {"entity_id": entity_id, "config_entry_id": entry_id, "platform": "2n_intercom"}


def state(entity_id: str, restored: bool | None = None, value: str = "unavailable") -> dict:
    attrs = {} if restored is None else {"restored": restored}
    return {"entity_id": entity_id, "state": value, "attributes": attrs}


class PlatformDomainsTest(unittest.TestCase):
    def test_py_modules_except_init(self) -> None:
        files = ["__init__.py", "api.py", "switch.py", "cover.py", "manifest.json", "translations"]
        self.assertEqual(platform_domains(files), {"api", "switch", "cover"})

    def test_accepts_paths(self) -> None:
        self.assertEqual(platform_domains(["custom_components/2n_intercom/lock.py"]), {"lock"})


class SelectOrphansTest(unittest.TestCase):
    domains = {"switch", "cover", "camera", "binary_sensor", "sensor"}

    def test_restored_entity_without_platform_is_orphan(self) -> None:
        registry = [reg("lock.2n_e2e"), reg("switch.2n_e2e_door")]
        states = {
            "lock.2n_e2e": state("lock.2n_e2e", restored=True),
            "switch.2n_e2e_door": state("switch.2n_e2e_door", value="off"),
        }
        orphans = select_orphans(registry, states, ENTRY, self.domains)
        self.assertEqual([o["entity_id"] for o in orphans], ["lock.2n_e2e"])

    def test_restored_entity_with_existing_platform_is_kept(self) -> None:
        registry = [reg("switch.2n_e2e_gone")]
        states = {"switch.2n_e2e_gone": state("switch.2n_e2e_gone", restored=True)}
        self.assertEqual(select_orphans(registry, states, ENTRY, self.domains), [])
        self.assertEqual(restored_kept(registry, states, ENTRY, self.domains), ["switch.2n_e2e_gone"])

    def test_live_entity_without_platform_is_kept(self) -> None:
        registry = [reg("lock.2n_e2e")]
        states = {"lock.2n_e2e": state("lock.2n_e2e", restored=False, value="locked")}
        self.assertEqual(select_orphans(registry, states, ENTRY, self.domains), [])

    def test_entity_without_state_is_kept(self) -> None:
        registry = [reg("lock.2n_e2e")]  # e.g. disabled entity: registry entry, no state
        self.assertEqual(select_orphans(registry, {}, ENTRY, self.domains), [])

    def test_other_config_entry_is_ignored(self) -> None:
        registry = [reg("lock.other", entry_id="entry2")]
        states = {"lock.other": state("lock.other", restored=True)}
        self.assertEqual(select_orphans(registry, states, ENTRY, self.domains), [])

    def test_restored_must_be_true_not_truthy(self) -> None:
        registry = [reg("lock.2n_e2e")]
        states = {"lock.2n_e2e": {"entity_id": "lock.2n_e2e", "attributes": {"restored": "yes"}}}
        self.assertEqual(select_orphans(registry, states, ENTRY, self.domains), [])


if __name__ == "__main__":
    unittest.main()
