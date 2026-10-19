---
id: TASK-63
title: >-
  Coder stub test test_run_without_started_field_uses_the_run_id_time fails in a
  clean Linux container
status: To Do
assignee:
  - '@copilot-mac'
created_date: '2026-10-18 16:40'
labels:
  - agent
  - infra
  - manual-path
  - test
dependencies: []
references:
  - tools/coder/tests/test_run_task.py
  - tools/coder/run-task.sh
priority: low
type: bug
ordinal: 68000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
tools/coder/tests/test_run_task.py::RunTaskCloneTests::test_run_without_started_field_uses_the_run_id_time fails on main (commit 0a2ea26 and after PR #86) in a clean Linux container with Python 3.13 (also with TZ=Europe/Prague): self._drain() returns [] instead of ['TASK-2']. The same suite passes on Jan's Mac and on the Pi, so the test depends on the environment (likely file or commit timestamps vs the run directory name built with time.localtime). All other 69 coder tests pass in the same container.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Root cause identified and written in the task notes [unit]
- [ ] #2 The test passes in a clean Linux container (UTC and Europe/Prague) and still passes on macOS; no other coder test weakened [unit]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Reproduce in a Linux container: python3 -m unittest discover -s tools/coder/tests -t tools/coder/tests. Compare how run-task.sh derives the start time from the legacy run directory name (no started= field) with how the test builds it (time.strftime on time.localtime(added + 600)) and with the committed_at of the edit commit. Fix the test or the parsing so both use the same clock and timezone.
<!-- SECTION:PLAN:END -->
