---
id: TASK-20
title: 'E2E: orphaned entities left by another branch''s deploy fail the next run'
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-12 07:11'
updated_date: '2026-10-12 07:11'
labels:
  - e2e
  - bug
dependencies:
  - TASK-11
references:
  - e2e/reports/20261012-033028 (on the Pi)
  - e2e/tests/conftest.py
  - e2e/tests/test_10_entities.py
  - e2e/tests/test_20_lifecycle.py
  - e2e/run.sh
  - e2e/scripts/deploy.sh
  - e2e/nightly.sh
  - e2e/agent/triage.md
priority: high
type: bug
ordinal: 20000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Nightly run `20261012-033028` (branch `origin/e2e-pipeline` @ a9ab87f, HA 2026.10.1, IP Force 2.0 fw 3.3.1.82.4) failed 2 tests, both on the same entity:

- `test_entities_available`: `unavailable entities: {'lock.2n_e2e': 'unavailable'}`
- `test_reload_entry`: `timeout after 60s waiting for entities available after reload`

No current branch has a lock platform (`origin/main`, `e2e-pipeline`, `security/*`, `mastalir1980-revize-pull-requestu`, `task-14-15-options-flow-ux` have only `switch.py`/`cover.py`). Only `origin/pr-7-savek-cc` has `lock.py`: it is 33 commits behind main and still uses the old layout. The previous multi-branch run (see commit a9ab87f: "pr-7-savek-cc failed 3 tests") deployed it to staging, and that added `lock.2n_e2e` to the entity registry under the same e2e config entry. The next deploy without a lock platform leaves the registry entry behind, HA restores it as `unavailable` (`restored: true`), and the `registry` fixture (`e2e/tests/conftest.py:67`) includes every registry entry of the entry. This is test-environment pollution, not an integration bug. It will hit every run that follows a branch with a different platform set, and the nightly now tests all origin branches on one shared staging HA.

The same review of `e2e/nightly.sh` found two small bugs:
- `[[ " ${BRANCHES} " != *" main "* ]]` is always true (refs are `origin/main`), so every trigger says "branch set changed".
- The comment says "main always first", but branches run in alphabetical order.

Not verified directly: Claude could not read the report on the Pi. The diagnosis is based on code and branch history. Check: `lock.2n_e2e` has `restored: true` in its state attributes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 After each deploy to staging, entity-registry entries of the e2e config entry that HA restored (`restored: true`) and whose entity domain has no platform module in the deployed code are removed; the removed entity_ids are logged and written to the run report (`context.json`)
- [ ] #2 Restored entities whose platform DOES exist in the deployed code are NOT removed (a real regression where the integration stops creating an entity must still fail `test_entities_available`)
- [ ] #3 Reproduction is green: deploy `origin/pr-7-savek-cc`, then run `bash e2e/e2e.sh run --ref origin/e2e-pipeline`; the second run passes and its report lists `lock.2n_e2e` as pruned (read-only, no relays)
- [ ] #4 `nightly.sh` no longer adds 'branch set changed' on every run, and `origin/main` runs before other branches
- [ ] #5 Only the staging HA (port 8124) is touched; the production HA and `reset-entry` are not used; `e2e/e2elib/twon.py` stays independent of the integration
- [ ] #6 `e2e/README.md` documents the orphan-pruning step
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add `e2e/scripts/prune_orphans.py` (uses `e2elib.ha`): wait until the e2e entry is `loaded`, list `config/entity_registry/list` for platform `2n_intercom` and the e2e entry, read each state, and select entries with `attributes.restored == true` whose domain (`entity_id` prefix) has no `<domain>.py` in the deployed `custom_components/2n_intercom/`. Remove them with WS `config/entity_registry/remove`. Print and return the removed list.
2. Call it from `e2e/run.sh` (or the end of `e2e/scripts/deploy.sh`) after HA restart and before pytest; store the result in the report `context.json` under `pruned_entities`.
3. `e2e/nightly.sh`: fix the branch-set check (`origin/main`) and run `origin/main` first, then the other branches sorted.
4. Do not change `e2e/tests/test_10_entities.py`/`test_20_lifecycle.py` semantics; do not filter restored entities inside tests.
5. Work on a branch from `origin/e2e-pipeline` (`task-<id>-e2e-orphan-entities`); this lands with the e2e-pipeline merge.
<!-- SECTION:PLAN:END -->
