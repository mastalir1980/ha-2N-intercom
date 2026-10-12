---
id: TASK-21.2
title: Merge e2e-pipeline into main (incl. local e2e changes and orphan fix)
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-12 07:12'
updated_date: '2026-10-12 10:42'
labels:
  - git
  - maintenance
  - e2e
dependencies:
  - TASK-20
  - TASK-21.1
references:
  - e2e/README.md
  - e2e/nightly.sh
  - e2e/tests/
parent_task_id: TASK-21
priority: high
type: chore
ordinal: 23000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`origin/e2e-pipeline` (0 behind / 3 ahead of main) contains the E2E pipeline (TASK-11). The local `e2e/` working copy on Jan's Mac has newer, uncommitted work that the nightly run on the Pi does not have: `e2e/tests/test_40_options_flow.py` and `e2e/tests/test_50_access_control.py` exist only locally, and `.env.example`, `e2e.sh`, `e2elib/ha.py`, `e2elib/twon.py`, `nightly.sh`, `run.sh` differ from the branch. The orphaned-entity bug must be fixed on this line before it reaches `main`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Local `e2e/` changes are reviewed and committed to the e2e-pipeline line; nothing from `e2e/.env`, `e2e/reports/`, `e2e/state/`, `.venv`, caches lands in git
- [x] #2 The orphaned-entity fix is included
- [x] #3 `bash e2e/e2e.sh run --ref <merged branch>` is green (read-only, no relays); tests that need features not yet on main (options-flow UX, access control) skip cleanly instead of failing
- [ ] #4 `main` contains `e2e/` and `run_tests.sh`; the nightly on the Pi picks up the scripts from `main`
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Worktree ../ha2n-t212, branch task-21.2-e2e-merge from origin/e2e-pipeline (a9ab87f).
2. Merge task-20-e2e-orphan-entities (orphan pruning, nightly fixes) and origin/main (21.1 project files).
3. Take Jan's new local e2e pieces from the main tree: tests/test_40_options_flow.py, tests/test_50_access_control.py, ha.py options-flow helpers, twon.py log helpers, .env.example E2E_GRANT_USER_UUID. Keep branch versions of e2e.sh, nightly.sh, run.sh (local copies are older: pre-1e9561d venv python, pre-a9ab87f multi-branch nightly).
4. test_40/test_50: skip cleanly when the deployed integration lacks the feature (options flow without go_back/last_step; no access_control in diagnostics / no grant_access service / no last-ring image).
5. Remove deploy_test.sh (deploys to production HA, against project rules - Jan's decision); keep run_tests.sh and drop its pointer to deploy_test.sh.
6. Verify: py_compile, bash -n, e2e/unit tests, integration unit tests, validate.py, no secrets/reports/state/venv staged. Push, Jan runs e2e.sh run --ref task-21.2-e2e-merge on the Pi.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Branch task-21.2-e2e-merge (worktree ../ha2n-t212, pushed, HEAD 7b820c7):
- ff-merged task-20-e2e-orphan-entities (1f732b3) + merged origin/main (6621eff) so the branch is not behind main.
- From Jan's untracked main-tree e2e/: took test_40_options_flow.py, test_50_access_control.py, ha.py options-flow helpers, twon.py log helpers, .env.example E2E_GRANT_USER_UUID. Did NOT take local e2e.sh/nightly.sh/run.sh - they are older than the branch (pre-1e9561d venv python, pre-a9ab87f multi-branch nightly/hermes). Local README identical to branch base.
- Skips: test_40 skips when the options flow reports last_step=null (pre-TASK-14). test_50: access-events test skips without access_control in diagnostics; last-ring image test skips when /api/config components lacks '2n_intercom.image'; grant_access (relay, manual only) skips without the service.
- Removed deploy_test.sh (deployed to production HA :8123 - Jan's decision); run_tests.sh kept, its deploy pointer dropped. Note: 43d4b27 message overstates its content (only the deletion); 7b820c7 completes it.
- Verified: bash -n, py_compile, e2e/unit OK, integration unit tests OK, validate.py OK, pytest --collect-only 17 tests. No .env/.venv/reports/state committed (.env/.venv are gitignored symlinks).
- Pending: Jan runs 'bash e2e/e2e.sh run --ref task-21.2-e2e-merge' on the Pi (expected: test_40 + test_50 skipped on main code). AC4 after Jan's --no-ff merge; Pi nightly must pull scripts from main.

E2E report 20261012-111534 (run on the Pi by Jan): status passed, ref task-21.2-e2e-merge, deployed_sha 7b820c7, 11 passed / 6 skipped. Skips as expected: test_40 (last_step not set, TASK-14 not deployed), test_50 access events (no access_control diagnostics), test_50 last-ring image (no image platform), relay tests (no --relays), SIP sensor disabled. Prune step ran, nothing to prune. AC1-3 checked; AC4 waits for Jan's --no-ff merge into main and the Pi nightly switched to main.
<!-- SECTION:NOTES:END -->
