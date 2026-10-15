---
id: TASK-36
title: >-
  Headless coder: set "To Test" instead of Done when a task needs manual
  verification
status: To Do
assignee:
  - '@copilot-mac'
created_date: '2026-10-15 12:13'
updated_date: '2026-10-15 12:13'
labels:
  - agent
  - infra
  - manual-path
dependencies: []
references:
  - tools/coder/run-task.sh
  - tools/coder/README.md
  - CLAUDE.md
priority: medium
type: task
ordinal: 44000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Backlog statuses are now To Do / In Progress / To Test / Done (decision by Jan, 15 Oct 2026). To Test = merged on main, automated checks green, waiting for Jan to verify on the real device (ring button, relays, Control4 ...) before the version is released. The coder today skips tasks with the label manual-close entirely (TASK-25), so they stay In Progress after the merge and the board shows them as unfinished work. With To Test they show up in the right column and the release can see what still needs a manual check.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 After green checks, close_task sets status To Test (instead of skipping) for a task with the label manual-close or with at least one acceptance criterion marked as manual (text contains "Manual" or "relay"); it ticks only the criteria that are not manual and writes the summary as today
- [ ] #2 All other tasks are set Done exactly as today
- [ ] #3 Stub simulation covers: normal task -> Done; manual-close task -> To Test with only automated criteria ticked; already Done/To Test task left alone
- [ ] #4 Rules in sync (CLAUDE.md, .github/copilot-instructions.md, tools/coder/README.md): meaning of To Test, label manual-close kept as an explicit marker
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. run-task.sh close_task(): read labels/criteria from $DIR/task.txt; decide target status (To Test vs Done); when To Test, only --check-ac for criteria without the manual markers; keep the backlog-only-diff guard and the never-fail-a-green-run rule.
2. Extend the stub simulation from TASK-25.
3. Rules/docs.
Must not change: protected paths, token handling, the single closing commit.
<!-- SECTION:PLAN:END -->
