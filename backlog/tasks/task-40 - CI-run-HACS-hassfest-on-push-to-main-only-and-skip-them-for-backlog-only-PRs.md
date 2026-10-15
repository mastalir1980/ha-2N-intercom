---
id: TASK-40
title: 'CI: run HACS/hassfest on push to main only and skip them for backlog-only PRs'
status: In Progress
assignee:
  - '@copilot-mac'
created_date: '2026-10-15 14:23'
updated_date: '2026-10-15 14:40'
labels:
  - ci
  - infra
  - manual-path
dependencies: []
priority: low
type: task
ordinal: 47000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Every bship PR now shows a red HACS check: bship merges and deletes the backlog-<timestamp> branch seconds after pushing, and hacs/action then fails with 'Repository ... not loaded properly in HACS' / 'Not Found' (seen on PR #48, both the push run 38750574439 and the pull_request run 38750585325; HACS on main is green). Both .github/workflows/hacs.yml and hassfest.yml trigger on push to every branch and on pull_request, so every PR branch runs each validation twice; that is also why the coder's final summary lists 'validate=pass' four times. Backlog and Markdown docs changes cannot affect HACS or hassfest results.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 hacs.yml and hassfest.yml run on push only for main (plus pull_request and workflow_dispatch as today)
- [x] #2 Their pull_request trigger uses the same path filter as e2e-pi.yml (skip when all changed files are under backlog/ except backlog/config.yml, or match docs/**/*.md)
- [x] #3 A code PR (e.g. the next coder PR) still gets one hassfest and one HACS check each, both green; the coder's wait_checks still sees e2e-pi
- [ ] #4 Verified live: the next bship PR shows no failed check; result written to the task notes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. In both workflows: on.push.branches: [main]; on.pull_request.paths with the same ordered list as e2e-pi.yml ('**', '!backlog/**', '!docs/**/*.md', 'backlog/config.yml'). Nothing else in the jobs changes.
2. Extend tools/tests/test_bship.py E2EPathFilterTests (or a sibling test) to assert the same filter in all three workflows.
3. Note in e2e/ci/README.md (Czech) next to the e2e-pi filter. Keep hassfest/HACS out of required checks (path-filtered checks stay pending).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed .github/workflows/hacs.yml and hassfest.yml: added push trigger limited to main; pull_request paths copied from e2e-pi.yml (backlog/** except backlog/config.yml, docs/**/*.md); workflow_dispatch kept. Jobs unchanged. Added test_hacs_and_hassfest_push_only_main_and_skip_backlog_only_prs in tools/tests/test_bship.py. Validation: tools/tests 16 OK, tests/ 587 OK, validate.py OK, py_compile OK, both YAML files parsed with Ruby (PyYAML and actionlint not installed). Czech note added to e2e/ci/README.md after TASK-32. Open: AC 3 and 4 need live runs (next bship PR and a code PR). Follow-up: CLAUDE.md and .github/copilot-instructions.md do not mention the new trigger rule; tools/coder/run-task.sh comments still mention hassfest/HACS. Not committed.

2026-10-15 (Claude): AC #3 live: PR #51 (TASK-40 itself, changes .github/) got exactly one hassfest and one HACS run, both from pull_request, plus e2e-pi; no push runs on the branch. PR #50 (cut before #51) still had push runs, as expected. AC #4: checked on the bship PR that ships this note.
<!-- SECTION:NOTES:END -->
