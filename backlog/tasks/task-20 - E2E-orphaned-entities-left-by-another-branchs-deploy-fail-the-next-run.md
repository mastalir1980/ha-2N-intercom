---
id: TASK-20
title: 'E2E: orphaned entities left by another branch''s deploy fail the next run'
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-12 07:11'
updated_date: '2026-10-15 12:47'
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
Nightly run `20261012-033028` (branch `origin/e2e-pipeline` @ a9ab87f, HA 2026.10.1, E2E intercom fw 3.x) failed 2 tests, both on the same entity:

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
- [x] #1 After each deploy to staging, entity-registry entries of the e2e config entry that HA restored (`restored: true`) and whose entity domain has no platform module in the deployed code are removed; the removed entity_ids are logged and written to the run report (`context.json`)
- [x] #2 Restored entities whose platform DOES exist in the deployed code are NOT removed (a real regression where the integration stops creating an entity must still fail `test_entities_available`)
- [x] #3 Reproduction is green: deploy `origin/pr-7-savek-cc`, then run `bash e2e/e2e.sh run --ref origin/e2e-pipeline`; the second run passes and its report lists `lock.2n_e2e` as pruned (read-only, no relays)
- [x] #4 `nightly.sh` no longer adds 'branch set changed' on every run, and `origin/main` runs before other branches
- [x] #5 Only the staging HA (port 8124) is touched; the production HA and `reset-entry` are not used; `e2e/e2elib/twon.py` stays independent of the integration
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

Live E2E by Jan on the Pi (report 20261012-092517, run from ~/ha2n-t20, PI_SSH=local): ref task-20-e2e-orphan-entities, deployed_sha 1f732b3, HA 2026.10.1, E2E intercom fw 3.x, status passed (11 passed, 2 skipped: SIP sensor disabled, relay test). prune.log: 'removed orphaned lock.2n_e2e (no lock.py deployed)'; pruned_entities.json: pruned [lock.2n_e2e], entry_state loaded, restored_kept []; context.json pruned_entities [lock.2n_e2e]. ha_url http://localhost:8124 (staging), no relays, no reset-entry. Deviation from AC #3 wording: second run used --ref task-20-e2e-orphan-entities instead of origin/e2e-pipeline - same platform set (no lock.py), and the branch is needed for run.sh to include the prune step. AC #2 is proven by the offline unit tests (test_restored_entity_with_existing_platform_is_kept); the live run had no such entity (restored_kept empty).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added an orphan-pruning step to the E2E pipeline: after each staging deploy, scripts/prune_orphans.py removes restored entities of the e2e entry whose domain has no platform module in the deployed code (kept otherwise), logs them and records them in context.json pruned_entities. Fixed nightly.sh branch-set detection and main-first ordering; README documented. Verified with 8 offline tests, unit suite + validate.py, and a green live E2E run on the Pi (20261012-092517) that pruned lock.2n_e2e left by pr-7-savek-cc. Branch task-20-e2e-orphan-entities (1f732b3) lands with TASK-21.2.
<!-- SECTION:FINAL_SUMMARY:END -->
