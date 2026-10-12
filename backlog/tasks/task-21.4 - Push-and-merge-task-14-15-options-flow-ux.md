---
id: TASK-21.4
title: Push and merge task-14-15-options-flow-ux
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-12 07:12'
updated_date: '2026-10-12 07:12'
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
- [ ] #1 Branch is pushed to origin and rebased on current `main` (after project files, e2e and busy-loop subtasks)
- [ ] #2 The `backlog/` files from this branch merge cleanly with the ones already on main (no duplicate TASK-14/15 files, `config.yml` identical or reconciled)
- [ ] #3 Unit suite + `validate.py` green; `bash e2e/e2e.sh run --ref origin/task-14-15-options-flow-ux` green including `test_40_options_flow.py`
- [ ] #4 Merged `--no-ff` into `main` by Jan; the `/private/tmp/ha2n-t1415` worktree is removed
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. In the worktree: `git rebase origin/main`; resolve `backlog/` overlaps by keeping main's copies plus the TASK-14/15 files.
2. Push, run E2E on the ref, Claude reviews, Jan merges.
3. `git worktree remove /private/tmp/ha2n-t1415`.
<!-- SECTION:PLAN:END -->
