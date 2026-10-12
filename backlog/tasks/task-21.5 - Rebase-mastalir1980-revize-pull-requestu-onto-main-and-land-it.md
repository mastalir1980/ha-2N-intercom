---
id: TASK-21.5
title: Rebase mastalir1980-revize-pull-requestu onto main and land it
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-12 07:12'
updated_date: '2026-10-12 07:12'
labels:
  - git
  - config-flow
  - auth
dependencies:
  - TASK-21.4
references:
  - custom_components/2n_intercom/config_flow.py
  - custom_components/2n_intercom/coordinator.py
  - custom_components/2n_intercom/__init__.py
  - custom_components/2n_intercom/api.py
parent_task_id: TASK-21
priority: medium
type: chore
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`origin/mastalir1980-revize-pull-requestu` (base 1.3.1, 4 behind / 4 ahead) carries work that main does not have:
- `e42bb45`: tolerate transient auth errors before triggering reauth (main reauths on the first 401)
- `fe158c1`: hassfest fixes incl. `CONFIG_SCHEMA` (missing in main `__init__.py`); the translation-placeholder part may duplicate main's `b463fe1`
- `46d6350`: preserve HA sessions and startup reauth during auth recovery
- `8dd8b6c`: draft-preserving back navigation in the setup wizard

Conflicts measured with `git merge-tree`: 8 hunks against main, 59 against main+TASK-14/15 (`config_flow.py`, `strings.json`, the three translations, `tests/test_config_flow.py`, `tests/test_init.py`, `README.md`, `CHANGELOG.md`). TASK-14 introduced `CONF_GO_BACK`-based back navigation for the options flow. The setup-wizard back navigation must reuse that mechanism, not add a second one.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Auth-recovery changes (e42bb45, 46d6350) land as their own branch/PR with their unit tests, on top of current main
- [ ] #2 `CONFIG_SCHEMA` is declared and hassfest passes; duplicate placeholder changes already in main are dropped
- [ ] #3 Setup-wizard back navigation lands as a second branch/PR, sharing the TASK-14 back-navigation helper/constants; strings and all three translations stay in sync
- [ ] #4 Version stays 1.4.x (no version/CHANGELOG bump outside a release task)
- [ ] #5 Each PR: unit suite + `validate.py` green, `bash e2e/e2e.sh wip` green
- [ ] #6 `origin/mastalir1980-revize-pull-requestu` is deleted after both PRs are merged (with Jan's OK)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Branch A `task-<id>-auth-recovery` from main: cherry-pick e42bb45, fe158c1, 46d6350; resolve conflicts keeping main's 1.4.0 secure-connection defaults (TASK-1) and the dual Basic/Digest auth.
2. Branch B `task-<id>-setup-wizard-back` from main after A: re-implement 8dd8b6c on top of the TASK-14 back-navigation code; do not copy its version bump/CHANGELOG.
3. Claude reviews each; Jan merges `--no-ff`.
<!-- SECTION:PLAN:END -->
