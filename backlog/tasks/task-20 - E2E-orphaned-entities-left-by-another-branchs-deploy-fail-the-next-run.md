---
id: TASK-20
title: 'E2E: orphaned entities left by another branch''s deploy fail the next run'
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-12 07:11'
updated_date: '2026-10-12 08:08'
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
- [x] #4 `nightly.sh` no longer adds 'branch set changed' on every run, and `origin/main` runs before other branches
- [ ] #5 Only the staging HA (port 8124) is touched; the production HA and `reset-entry` are not used; `e2e/e2elib/twon.py` stays independent of the integration
- [x] #6 `e2e/README.md` documents the orphan-pruning step
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Branch task-20-e2e-orphan-entities from origin/e2e-pipeline in worktree ../ha2n-t20 (e2e/.env, e2e/.venv symlinked from main tree).
1. e2e/e2elib/orphans.py: dependency-free logic - platform_domains(file names) and select_orphans(registry, states, entry_id, domains): entries of the e2e entry whose state has attributes.restored == true and whose domain has no <domain>.py in the deployed code.
2. e2e/scripts/prune_orphans.py: staging-only guard, wait until the 2N entry is loaded, list deployed platform files (git ls-tree <ref> or the working tree), read registry + /api/states, remove orphans via WS config/entity_registry/remove, print removed ids and write JSON (--out).
3. e2e/run.sh: call it after deploy+settle, before pytest, with the same --ref/--worktree as deploy; output -> $REPORT/pruned_entities.json + prune.log; never aborts the run.
4. e2e/tests/conftest.py run_context: copy pruned list into context.json as pruned_entities (no test semantics changed; tests do not filter restored entities).
5. e2e/nightly.sh: branch-set change detected against state/last_nightly_branches instead of the always-true ' main ' check; origin/main first, then others sorted.
6. Offline unit tests e2e/unit/test_orphans.py (python3 -m unittest discover -s e2e/unit -t e2e); e2e/README.md documents pruning.
7. AC #3 live reproduction (deploy pr-7-savek-cc, then run --ref) needs the staging Pi - Jan runs E2E externally.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented on task-20-e2e-orphan-entities @ 1f732b3 (from origin/e2e-pipeline a9ab87f), pushed. Worktree ../ha2n-t20 with e2e/.env and e2e/.venv symlinked (git-ignored).
- e2e/e2elib/orphans.py: platform_domains() + select_orphans() (restored is True AND domain has no <domain>.py) + restored_kept().
- e2e/scripts/prune_orphans.py: assert_staging_url guard, waits for entry 'loaded' (--wait, default 120s), platform list from 'git ls-tree <ref>:custom_components/2n_intercom' or the working tree, removes via WS config/entity_registry/remove, prints removed ids, writes JSON (pruned, restored_kept, platform_domains, entry_state, error). Skips if != 1 2N entry. Any error -> exit 1 + JSON error; never aborts the run.
- run.sh: prune step after deploy+settle, same --ref/--worktree as deploy; prune.log + pruned_entities.json in report. conftest.run_context copies it to context.json pruned_entities (/ pruned_entities_error). Test semantics unchanged.
- nightly.sh: 'branch set changed' now compares against state/last_nightly_branches (saved after each triggered run); origin/main first, then others sorted; header comment fixed.
- Offline tests: e2e/unit/test_orphans.py (8 tests, python3 -m unittest discover -s e2e/unit -t e2e) OK. Verified with real refs: origin/pr-7-savek-cc has 'lock' platform, origin/e2e-pipeline/main/HEAD do not -> lock.2n_e2e would be pruned on e2e-pipeline. Error path checked against unreachable staging: exit 1, JSON {'error': 'timed out'}. Nightly ordering/branch-set snippet checked in isolation.
- Integration unit suite + validate.py green in the worktree; e2e/e2elib/twon.py untouched.
- NOT verified: AC #1/#2/#3/#5 live (staging Pi unreachable this morning; Jan runs E2E externally). Reproduction for AC #3: deploy origin/pr-7-savek-cc (bash e2e/scripts/deploy.sh --ref origin/pr-7-savek-cc), then from ../ha2n-t20: bash e2e/e2e.sh run --ref task-20-e2e-orphan-entities; check prune.log / context.json pruned_entities contains lock.2n_e2e.
- Follow-up: TASK-19 is an exact duplicate of TASK-20 (same title/description) - should be archived/closed by Claude/Jan.
- Note: e2e/unit is not run by run.sh stage 1 (out of scope); could be added later.
<!-- SECTION:NOTES:END -->
