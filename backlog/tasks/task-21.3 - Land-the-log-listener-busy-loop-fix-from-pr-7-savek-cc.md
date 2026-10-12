---
id: TASK-21.3
title: Land the log-listener busy-loop fix from pr-7-savek-cc
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-12 07:12'
updated_date: '2026-10-12 10:51'
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
- [x] #1 On an empty pull the listener waits `LOG_LISTENER_IDLE_DELAY` (1 s) before the next pull; on a pull with events it only yields (`sleep(0)`)
- [x] #2 Unit test in `tests/test_coordinator.py` covers both paths (empty pull -> delay, events -> no delay) with patched `asyncio.sleep`
- [x] #3 Ring detection and the subscription/backoff behaviour are unchanged; full unit suite and `validate.py` green
- [x] #4 `bash e2e/e2e.sh wip` green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Branch task-21.3-log-listener-idle-delay from origin/main (main tree).
2. git cherry-pick -x 48375d2 (clean; comment already matches main's loop).
3. Unit tests in tests/test_coordinator.py LogListenerTests: patched asyncio.sleep, empty pulls -> LOG_LISTENER_IDLE_DELAY, pulls with events -> sleep(0).
4. Note the firmware quirk in docs/API_REFERENCE.md. Nothing else from pr-7-savek-cc; CHANGELOG in the release task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
- Cherry-picked 48375d2 cleanly: LOG_LISTENER_IDLE_DELAY = 1 in coordinator.py; _async_run_log_subscription sleeps 1 s after an empty pull, sleep(0) after a pull with events. Error path (LOG_LISTENER_PULL_ERROR_DELAY + raise), subscribe/backoff and ring handling untouched.
- Tests: test_empty_pull_waits_idle_delay, test_pull_with_events_only_yields (helper _sleeps_for_pulls patches coordinator asyncio.sleep with AsyncMock, stops the loop via _log_listener_stopped). Verified both fail against the pre-fix coordinator.
- docs/API_REFERENCE.md: firmware quirk 'log/pull may not block' added.
- Full suite 454 OK, validate.py OK, py_compile OK. E2E deferred to Jan (Pi unreachable from the Mac).

E2E report 20261012-115020 (Jan, on the Pi, e2e.sh run --ref task-21.3-log-listener-idle-delay instead of wip): passed, deployed_sha 0ae1d14, 11 passed / 6 skipped (same skips as main: SIP sensor disabled, relays, TASK-14/8/9 features not deployed). Log listener kept working - ring/state tests passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Landed the log-listener busy-loop fix from pr-7-savek-cc (cherry-pick of 48375d2 as a7da51d): after an empty /api/log/pull the listener waits LOG_LISTENER_IDLE_DELAY (1 s), after a pull with events it only yields. Added two unit tests with patched asyncio.sleep (fail without the fix) and documented the firmware quirk in docs/API_REFERENCE.md. Nothing else taken from pr-7-savek-cc. Unit suite (454), validate.py and E2E 20261012-115020 green. CHANGELOG entry left for the release task.
<!-- SECTION:FINAL_SUMMARY:END -->
