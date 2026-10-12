---
id: TASK-21.6
title: Commit and land the TASK-4/8/9 working-tree changes as separate branches
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-12 07:12'
updated_date: '2026-10-12 12:16'
labels:
  - git
  - access-control
dependencies:
  - TASK-21.5
references:
  - custom_components/2n_intercom/coordinator.py
  - custom_components/2n_intercom/image.py
  - >-
    backlog/tasks/task-4 -
    Subscribe-to-access-control-events-from-the-2N-log-channel.md
parent_task_id: TASK-21
priority: high
type: chore
ordinal: 27000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The access-control, grant_access and ring-snapshot work (TASK-4 Done, TASK-8 In Progress, TASK-9 Done) exists only as uncommitted changes in Jan's working tree on branch `task-4-8-9-access-control-ring-snapshot` (= main 369e923 + ~1650 changed lines in `__init__.py`, `api.py`, `config_flow.py`, `const.py`, `coordinator.py`, `diagnostics.py`, `services.yaml`, `strings.json`, translations, tests, plus new `image.py`, `tests/test_coordinator_access.py`, `tests/test_image.py`, `tests/test_translations.py`). It is not backed up anywhere. The project rule is one task per branch. These changes overlap with the config-flow and auth subtasks, so they must be rebased after them.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The current working-tree state is committed immediately to a backup branch (`wip/task-4-8-9-backup`) and pushed, before any other subtask touches the tree
- [ ] #2 The work is split into `task-4-…`, `task-8-…`, `task-9-…` branches (dependency order 4 -> 9 -> 8 or as the code requires), each rebased on the then-current main
- [ ] #3 Each branch: unit suite + `validate.py` green, E2E test for the feature in `e2e/tests/` (incl. `test_50_access_control.py`), `bash e2e/e2e.sh wip` green; no relay tests
- [ ] #4 TASK-8 is finished per its own acceptance criteria before its branch merges
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Now: `git switch -c wip/task-4-8-9-backup && git add -A custom_components tests validate.py && git commit -m "wip: TASK-4/8/9 backup"` and push (excluding the zip, backlog/, docs/, e2e/ handled elsewhere).
2. After the revize subtask: split by `git checkout -p` / path into three branches from main.
3. Review per branch, Jan merges `--no-ff`.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Step 1 (backup) done 2026-10-12:
- Plan vs reality: the TASK-4/8/9 work was NOT uncommitted any more. Jan had already committed it as 91a58b8 'Add access-control events, grant_access service and last-ring image' on task-4-8-9-access-control-ring-snapshot (24 files incl. README.md; parent 369e923), but it was not pushed anywhere. custom_components/, tests/, validate.py had no uncommitted changes (only untracked custom_components/2n_intercom.zip, deliberately excluded).
- So step 1 = 'git switch -c wip/task-4-8-9-backup' at 91a58b8 (no new commit needed) + 'git push -u origin wip/task-4-8-9-backup'. origin/wip/task-4-8-9-backup = 91a58b81e1d0f0b7ef7958fab2346eea085743a4 (verified via ls-remote).
- Validation on 91a58b8 (Python 3.14.3): unittest 530 tests OK, validate.py exit 0, py_compile OK.
- e2e.sh wip NOT green: deploy stage failed, 'ssh: connect to host 192.168.88.28 port 22: Operation timed out'; ping to the Pi also 100% loss -> staging Pi unreachable (infrastructure, not code). Report: e2e/reports/20261012-092514. Needs rerun once the Pi is back.
- Steps 2-3 not started (blocked by TASK-21.5 dependency and Jan's review).

E2E deferred: Jan will run e2e.sh externally (instruction 2026-10-12).

Step 2, branch 1 of 3 (task-4) done 2026-10-12:
- Worktree ../ha2n-t216 from origin/main 29c6773; cherry-pick -n 91a58b8 had only two trivial union conflicts (coordinator.py: LOG_LISTENER_IDLE_DELAY + access constants/AccessEvent; config_flow.py imports: CONF_GO_BACK + CONF_GRANT_ACCESS_USER). Combined tree: 563 tests OK.
- Split by stripping hunks from the combined tree: minus TASK-8 (grant_access service, GrantAccessResult/async_grant_access/TwoNDeviceRejectedError, grant-user option in options flow, services.yaml, access_point selector, grant_access_* strings, README grant sections, validate.py feature line) = 4+9 tree (539 tests OK); minus TASK-9 (image.py, ring snapshot capture/fields/properties in coordinator, image platform + ring_snapshot_enabled in __init__, diagnostics ring_snapshot, entity.image strings/icon, README image lines) = TASK-4 tree.
- Branch task-4-access-control-events = 90e7fd7 (pushed). 528 tests OK, validate.py OK, py_compile OK. In test_coordinator_access.py the combined RingSnapshotTests.test_update_data_carries_event_state is replaced on this branch by UpdateDataTests.test_update_data_carries_access_event (access part only); task-9 restores the combined test.
- Also fixed the swapped TASK labels in e2e/tests/test_50_access_control.py skip messages (access_control = TASK-4, grant_access = TASK-8).
- docs/API_REFERENCE.md already covers all three features (landed with TASK-21.1); no docs change.
- Intermediate trees kept as patches against 29c6773 in the agent session files (4+9 tree 0a40ec8, full tree 3c70f9a) for task-9 / task-8.
- Pending: E2E run by Jan (e2e.sh run --ref task-4-access-control-events; expect test_50 access_control part to run, image/grant skipped), review, merge.

task-4 E2E: report 20261012-123306 passed at 81d8787 (13 passed, 4 skipped). test_subscribed_access_events_match_device_log_caps ran for the first time and passed (HA subscription = device log/caps). Skips as expected: SIP sensor disabled, relays, image (TASK-9 not deployed), grant_access (relay). Warnings only InsecureRequestWarning from the E2E client.

Step 2, branch 2 of 3 (task-9) 2026-10-12: task-9-last-ring-image from origin/main 3c55e54 (task-4 merged) + diff 90e7fd7..0a40ec8 (the 4+9 tree) on custom_components/tests/README; resulting tree identical to the saved 4+9 tree. 539 tests OK, validate.py OK, py_compile OK. Restores the combined RingSnapshotTests.test_update_data_carries_event_state. E2E check: test_50 test_last_ring_image_follows_camera. Pending: E2E by Jan, review, merge.

task-9 E2E: report 20261012-123947 passed at 64fe19c (14 passed, 3 skipped). test_last_ring_image_follows_camera ran and passed (image entity exists with camera enabled, not unavailable); access-control test still passes. Skips: SIP sensor disabled, relays, grant_access (relay).

Step 2, branch 3 of 3 (task-8) 2026-10-12: task-8-grant-access from origin/main 4e4a3cf (task-4 + task-9 merged) + diff 0a40ec8..3c70f9a (4+9 tree -> full tree) on custom_components/tests/README/validate.py; resulting tree identical to the full cherry-picked tree of 91a58b8 (e2e/ kept from main, so the fixed test_50 labels stay). 563 tests OK, validate.py OK, py_compile OK. AC4: TASK-8 AC6 (relay E2E test_grant_access_is_logged_by_device, already in main) still needs Jan's manual relay run before merge.

task-8 relay E2E: report 20261012-124448 at 3670c44 with --relays: passed (15 passed, 2 skipped); test_relay_roundtrip[1] passed. But test_grant_access_is_logged_by_device SKIPPED: E2E_GRANT_USER_UUID not set in e2e/.env on the Pi, so TASK-8 AC6 is NOT verified yet. Needs a rerun with the UUID set.

task-8 relay E2E rerun: report 20261012-131421 at 3670c44 (--relays, E2E_GRANT_USER_UUID set) passed 16, skipped 1 (SIP sensor). test_grant_access_is_logged_by_device passed -> TASK-8 AC6 checked, TASK-8 Done (AC4 of this task satisfied).
<!-- SECTION:NOTES:END -->
