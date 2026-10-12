---
id: TASK-21.4
title: Push and merge task-14-15-options-flow-ux
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-12 07:12'
updated_date: '2026-10-12 11:07'
labels:
  - git
  - config-flow
dependencies:
  - TASK-21.3
references:
  - custom_components/2n_intercom/config_flow.py
  - custom_components/2n_intercom/strings.json
parent_task_id: TASK-21
priority: high
type: chore
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-14/15 (options-flow Next/Submit labels, back navigation, clearer credential fields) are Done in the backlog, but their branch `task-14-15-options-flow-ux` exists only locally (worktree `/private/tmp/ha2n-t1415`) and is not on GitHub. It is 0 behind / 3 ahead of main and merges cleanly with e2e-pipeline. It must land before the revize branch, which touches the same `config_flow.py` and translations.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Branch is pushed to origin and rebased on current `main` (after project files, e2e and busy-loop subtasks)
- [x] #2 The `backlog/` files from this branch merge cleanly with the ones already on main (no duplicate TASK-14/15 files, `config.yml` identical or reconciled)
- [x] #3 Unit suite + `validate.py` green; `bash e2e/e2e.sh run --ref origin/task-14-15-options-flow-ux` green including `test_40_options_flow.py`
- [x] #4 Merged `--no-ff` into `main` by Jan; the `/private/tmp/ha2n-t1415` worktree is removed
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. In /private/tmp/ha2n-t1415: move the untracked, obsolete e2e/ copy aside (it would block the rebase now that main tracks e2e/), git rebase origin/main.
2. Check backlog overlaps (TASK-14/15 files, config.yml).
3. Unit suite, validate.py, py_compile, JSON check; push to origin.
4. Jan runs e2e.sh run --ref task-14-15-options-flow-ux on the Pi (test_40 must run, not skip), Jan merges --no-ff.
5. git worktree remove /private/tmp/ha2n-t1415 after the merge.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- Untracked e2e/ in the worktree (older subset of main's e2e/: no orphan pruning, no test_50, test_40 without skip; reports 20261011-213353 failed / 20261012-084900 deploy error) moved to /private/tmp/ha2n-t1415-e2e-untracked-backup, not deleted. Contains only symlinks to the main tree's .env/.venv, no secret copies.
- git rebase origin/main (0828af0): clean, no conflicts. d01afac->d08492d, 6ac5ad2->9ecd973, 2f87eeb->bad0011.
- Backlog: config.yml identical to main after rebase; TASK-14/15 files only on this branch, no duplicates.
- Unit suite 469 OK, validate.py OK, py_compile OK, strings/translations JSON valid. Pushed origin/task-14-15-options-flow-ux (new on origin).

E2E report 20261012-120017 (Jan, on the Pi): passed, ref task-14-15-options-flow-ux, deployed_sha 421dc3b, 12 passed / 5 skipped. test_40_options_flow ran and PASSED (Next/Submit last_step, go_back, masked RTSP password, options unchanged). Skips: SIP sensor disabled, relays, test_50 TASK-8/9 features not deployed. Warnings only InsecureRequestWarning from the E2E 2N client (self-signed device cert). AC1-3 checked; AC4 after Jan's --no-ff merge + worktree removal.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
task-14-15-options-flow-ux (TASK-14 options-flow Next/Submit + back navigation, TASK-15 credential field clarity) rebased cleanly onto main, pushed to origin for the first time and merged --no-ff by Jan (e36c496). Backlog config.yml identical to main, no duplicate TASK-14/15 files. Unit suite 469, validate.py and E2E 20261012-120017 green with test_40_options_flow actually running. The obsolete untracked e2e/ copy from the worktree was moved to /private/tmp/ha2n-t1415-e2e-untracked-backup (not deleted); worktree /private/tmp/ha2n-t1415 removed.
<!-- SECTION:FINAL_SUMMARY:END -->
