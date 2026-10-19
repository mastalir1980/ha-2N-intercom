---
id: TASK-62
title: >-
  Headless coder: coerce mislabelled [tester]/[jan] criteria to manual and
  untick criteria that are not proven
status: To Do
assignee:
  - '@copilot-mac'
created_date: '2026-10-18 16:40'
labels:
  - agent
  - infra
  - manual-path
dependencies: []
references:
  - tools/coder/run-task.sh
  - tools/coder/prompts/review.md
  - tools/coder/tests/test_run_task.py
priority: low
type: enhancement
ordinal: 67000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from the review of PR #86 (TASK-36). (1) tools/coder/run-task.sh review(): when the reviewer reports a [tester] or [jan] criterion as proven, an assert fails and the whole review counts as failed, so the run ends in state review without a fix round although nothing is wrong with the change. Expected: the status is coerced to manual (logged in the review comment) and the review continues. (2) close_task only ticks proven criteria but never unticks: implement.md forbids the coder to tick criteria, yet nothing enforces it, so a criterion the coder ticked stays ticked even when the reviewer reports it unproven or manual. Expected: every criterion that is not proven is unticked in the closing commit.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A reviewer criterion with status proven on a [tester]/[jan] criterion is stored as manual, the review comment says so, and the review is not failed; stub test [unit]
- [ ] #2 close_task unticks every criterion whose status is not proven (--uncheck-ac) and ticks every proven one; stub test with a criterion the coder ticked but the reviewer reported unproven [unit]
- [ ] #3 Existing coder stub suite stays green; bash -n clean [unit]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
tools/coder/run-task.sh: in the review() Python block replace the assert on tag tester/jan with a coercion to manual plus a note appended to the comment; in close_task emit unproven/manual ids on a third line of close-evidence.txt and pass them as --uncheck-ac. Tests in tools/coder/tests/test_run_task.py next to test_manual_tags_cannot_be_reported_as_proven (rename/adjust it). Must not change: the backlog-only guard of the closing commit, stale-evidence check, auto-merge rules.
<!-- SECTION:PLAN:END -->
