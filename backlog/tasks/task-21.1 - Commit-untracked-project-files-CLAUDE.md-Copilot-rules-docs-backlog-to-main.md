---
id: TASK-21.1
title: >-
  Commit untracked project files (CLAUDE.md, Copilot rules, docs/, backlog/) to
  main
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-12 07:12'
updated_date: '2026-10-12 08:27'
labels:
  - git
  - maintenance
  - docs
dependencies: []
references:
  - CLAUDE.md
  - .github/copilot-instructions.md
  - backlog/config.yml
  - .gitignore
parent_task_id: TASK-21
priority: high
type: chore
ordinal: 22000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`CLAUDE.md`, `.github/copilot-instructions.md`, `docs/` and the whole `backlog/` tree (tasks 2–21, `config.yml`, `archive/`) exist only as untracked files in Jan's working tree. They are not in any commit or on GitHub, so a checkout or merge can overwrite them, and both agents depend on them. `task-14-15-options-flow-ux` also adds `backlog/config.yml` and the TASK-14/15 files, so these must be in `main` first to make that merge a normal merge, not an add/add clash with untracked files. `custom_components/2n_intercom.zip` is a stray build artifact.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `main` contains `CLAUDE.md`, `.github/copilot-instructions.md`, `docs/` and `backlog/` exactly as they are in the working tree today
- [x] #2 `custom_components/2n_intercom.zip` is not committed and `*.zip` plus Python caches (`__pycache__/`, `.pytest_cache/`) are in `.gitignore`
- [x] #3 No integration code (`custom_components/`, `tests/`) and no `e2e/` file is part of this commit; the uncommitted TASK-4/8/9 working-tree changes stay untouched
- [x] #4 `validate.py` and the unit suite stay green on the resulting `main`
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Per Jan's instruction (overrides worktree step): git switch -c task-21.1-project-files origin/main in the main working tree; untracked files stay in place.
2. Add *.zip to .gitignore (__pycache__/ and .pytest_cache/ already present).
3. git add only CLAUDE.md, .github/copilot-instructions.md, docs/, backlog/, .gitignore; commit 'chore: add project rules, docs and backlog'.
4. Verify no custom_components/, tests/, e2e/ or zip in the commit; run unit suite + validate.py; push branch. Jan merges --no-ff.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- Branch created in the main working tree per Jan's instruction (not a separate worktree as the plan said).
- .gitignore: added *.zip; __pycache__/ and .pytest_cache/ were already present.
- Secret scan: no e2e/.env secret values in committed files. Only matches: HA_CONTAINER name (not secret) and Jan's nickname in CLAUDE.md, which equals the intercom username (not a password) - flagged to Jan.

Committed f3873e1 on task-21.1-project-files (parent origin/main 369e923), pushed to origin. 37 files, only CLAUDE.md, .github/copilot-instructions.md, docs/, backlog/, .gitignore; verified no custom_components/, tests/, e2e/ or *.zip paths in the commit. Untracked e2e/ and the zip remain in the working tree untouched; TASK-4/8/9 work is safe on wip/task-4-8-9-backup (91a58b8).
Validation on the branch (Python 3.14.3): unittest 452 tests OK, validate.py exit 0, py_compile OK. E2E not run (Jan runs it externally; branch has no code change).
Open: AC #1 and #4 refer to main - pending Jan's --no-ff merge. Task-file status/notes edits made after the commit are uncommitted in the tree.

Jan merged --no-ff into main (94d6f4c, includes e114768 backlog notes) and pushed. Verified on origin/main: project files identical to the branch, no custom_components/, tests/ or e2e/ changes vs 369e923, unittest OK, validate.py exit 0.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Committed CLAUDE.md, .github/copilot-instructions.md, docs/ and backlog/ (plus *.zip in .gitignore) on task-21.1-project-files; merged by Jan into main as 94d6f4c. Verified: no code/e2e paths in the change, unit suite + validate.py green on main.
<!-- SECTION:FINAL_SUMMARY:END -->
