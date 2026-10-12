---
id: TASK-21.3
title: Land the log-listener busy-loop fix from pr-7-savek-cc
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-12 07:12'
updated_date: '2026-10-12 07:12'
labels:
  - git
  - coordinator
dependencies:
  - TASK-21.2
references:
  - custom_components/2n_intercom/coordinator.py
  - tests/test_coordinator.py
  - docs/API_REFERENCE.md
parent_task_id: TASK-21
priority: high
type: bug
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`origin/pr-7-savek-cc` commit `48375d2` changes the log/pull loop in `coordinator.py`: on an empty pull it sleeps `LOG_LISTENER_IDLE_DELAY = 1` s instead of `asyncio.sleep(0)`, because some 2N firmware returns from `/api/log/pull` immediately despite `timeout=1`. That turns the listener into a busy loop. `main` still has `await asyncio.sleep(0)` (`coordinator.py` ~line 522). The rest of the branch is 33 commits behind and on the old layout (it still has `lock.py`), so the branch itself must not be merged. The fix has no unit test.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 On an empty pull the listener waits `LOG_LISTENER_IDLE_DELAY` (1 s) before the next pull; on a pull with events it only yields (`sleep(0)`)
- [ ] #2 Unit test in `tests/test_coordinator.py` covers both paths (empty pull -> delay, events -> no delay) with patched `asyncio.sleep`
- [ ] #3 Ring detection and the subscription/backoff behaviour are unchanged; full unit suite and `validate.py` green
- [ ] #4 `bash e2e/e2e.sh wip` green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Branch `task-<id>-log-listener-idle-delay` from `origin/main`; `git cherry-pick 48375d2` (merge-tree shows no conflict) and adapt the comment to main's code.
2. Add the unit test.
3. Do not take anything else from `pr-7-savek-cc`.
4. CHANGELOG entry only in the next release task.
<!-- SECTION:PLAN:END -->
