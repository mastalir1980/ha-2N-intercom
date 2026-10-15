---
id: TASK-40
title: 'CI: run HACS/hassfest on push to main only and skip them for backlog-only PRs'
status: To Do
assignee:
  - '@copilot-mac'
created_date: '2026-10-15 14:23'
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
- [ ] #1 hacs.yml and hassfest.yml run on push only for main (plus pull_request and workflow_dispatch as today)
- [ ] #2 Their pull_request trigger uses the same path filter as e2e-pi.yml (skip when all changed files are under backlog/ except backlog/config.yml, or match docs/**/*.md)
- [ ] #3 A code PR (e.g. the next coder PR) still gets one hassfest and one HACS check each, both green; the coder's wait_checks still sees e2e-pi
- [ ] #4 Verified live: the next bship PR shows no failed check; result written to the task notes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. In both workflows: on.push.branches: [main]; on.pull_request.paths with the same ordered list as e2e-pi.yml ('**', '!backlog/**', '!docs/**/*.md', 'backlog/config.yml'). Nothing else in the jobs changes.
2. Extend tools/tests/test_bship.py E2EPathFilterTests (or a sibling test) to assert the same filter in all three workflows.
3. Note in e2e/ci/README.md (Czech) next to the e2e-pi filter. Keep hassfest/HACS out of required checks (path-filtered checks stay pending).
<!-- SECTION:PLAN:END -->
