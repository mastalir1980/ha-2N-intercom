---
id: TASK-21.6
title: Commit and land the TASK-4/8/9 working-tree changes as separate branches
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-12 07:12'
updated_date: '2026-10-12 07:58'
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
<!-- SECTION:NOTES:END -->
