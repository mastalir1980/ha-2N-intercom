---
id: TASK-36
title: >-
  Headless coder: per-criterion evidence from the reviewer; tick only proven
  criteria, To Test when any remain
status: To Do
assignee:
  - '@copilot-mac'
created_date: '2026-10-15 12:13'
updated_date: '2026-10-18 15:47'
labels:
  - agent
  - infra
  - manual-path
dependencies: []
references:
  - tools/coder/run-task.sh
  - tools/coder/README.md
  - CLAUDE.md
priority: high
type: task
ordinal: 44000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
close_task in tools/coder/run-task.sh (around line 478-514) ticks every unchecked criterion (line 495) without any evidence, and for manual-close tasks it ticks nothing. Result: TASK-31/45/47/49 reached Done with 0 of 8-9 criteria ticked although most were proven by unit tests. review.md already tells the reviewer that a criterion without proof is blocking, but its JSON only carries verdict + findings, so the per-criterion result is lost. Fix: the reviewer returns a status and evidence for every criterion; close_task ticks only proven ones and sets To Test when anything is left.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 review.md output contract adds criteria: [{id, status: proven|manual|unproven, evidence}] covering every criterion of the task; run-task.sh validates it (all ids present, known status, evidence non-empty for proven); invalid output = review failed as today
- [ ] #2 The reviewer uses the verifier tag at the end of a criterion when present: [unit]/[e2e] must be proven in the diff or by a green check, [tester]/[jan] are reported as manual; an unproven [unit]/[e2e] criterion is a blocking finding
- [ ] #3 close_task ticks only proven criteria and appends one line per criterion (AC #n: evidence) to the final summary; without a configured review-model nothing is ticked
- [ ] #4 Status after green checks: Done when every criterion is proven and the task has no manual-close label; otherwise To Test; tasks already Done or To Test are left alone
- [ ] #5 Stub simulation in tools/coder/tests covers: all proven -> Done, all ticked; mixed -> To Test, only proven ticked; manual-close -> To Test; malformed criteria -> review failed, nothing ticked
- [ ] #6 Rules in sync (CLAUDE.md, .github/copilot-instructions.md, tools/coder/README.md): meaning of To Test, evidence lines in the final summary, manual-close kept as explicit marker
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. run-task.sh close_task(): read labels/criteria from $DIR/task.txt; decide target status (To Test vs Done); when To Test, only --check-ac for criteria without the manual markers; keep the backlog-only-diff guard and the never-fail-a-green-run rule.
2. Extend the stub simulation from TASK-25.
3. Rules/docs.
Must not change: protected paths, token handling, the single closing commit.
<!-- SECTION:PLAN:END -->
