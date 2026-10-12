---
id: TASK-21.2
title: Merge e2e-pipeline into main (incl. local e2e changes and orphan fix)
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-12 07:12'
updated_date: '2026-10-12 07:12'
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
- [ ] #1 Local `e2e/` changes are reviewed and committed to the e2e-pipeline line; nothing from `e2e/.env`, `e2e/reports/`, `e2e/state/`, `.venv`, caches lands in git
- [ ] #2 The orphaned-entity fix is included
- [ ] #3 `bash e2e/e2e.sh run --ref <merged branch>` is green (read-only, no relays); tests that need features not yet on main (options-flow UX, access control) skip cleanly instead of failing
- [ ] #4 `main` contains `e2e/` and `run_tests.sh`; the nightly on the Pi picks up the scripts from `main`
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Branch `task-<id>-e2e-merge` from `origin/e2e-pipeline`; copy the local `e2e/` changes (diff each file against the branch, keep the newer intent; ask Jan if unclear).
2. Make `test_40_options_flow.py` / `test_50_access_control.py` skip when the deployed code lacks the feature (e.g. check for a service or step name) so the suite passes on current main.
3. Merge the orphaned-entity fix branch.
4. Run `e2e.sh run --ref` on the branch; then Jan merges `--no-ff` into `main`.
<!-- SECTION:PLAN:END -->
