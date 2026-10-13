---
id: TASK-2.1
title: 'B1: use tz-aware timestamps in the coordinator instead of naive datetime.now()'
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-12 19:54'
updated_date: '2026-10-13 12:16'
labels:
  - tech-debt
  - coordinator
dependencies: []
references:
  - docs/IMPROVEMENTS.md
  - custom_components/2n_intercom/coordinator.py
  - custom_components/2n_intercom/binary_sensor.py
  - tests/test_coordinator.py
  - tests/test_binary_sensor.py
  - tests/_stubs.py
parent_task_id: TASK-2
priority: medium
type: task
ordinal: 31000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: docs/IMPROVEMENTS.md B1. The coordinator stores ring/motion times with naive datetime.now() (no timezone). binary_sensor.py:125 and :242 export them with .isoformat() as the entity attributes last_ring / last_motion, so Home Assistant users get a timestamp without an offset that is ambiguous across time zones and inconsistent with HA, which works in tz-aware UTC (homeassistant.util.dt). The project rule in CLAUDE.md is: timestamps tz-aware via homeassistant.util.dt, no naive datetime.now(). The same file already uses dt_util.utcnow() for the ring snapshot (coordinator.py:529, :744), so this makes it consistent.

Current behaviour (evidence: grep in custom_components/2n_intercom/coordinator.py): naive datetime.now() at :354 (_last_motion_time on MotionDetected), :875 (_last_ring_time on ring, also the base of _ring_pulse_until), :1326 (ring_active compares now with _ring_pulse_until), :1537 (snapshot cache age in async_get_snapshot).
Expected behaviour: all four use dt_util.utcnow(); last_ring and last_motion attributes carry an offset (e.g. 2026-04-12T10:00:00+00:00); ring pulse and snapshot cache keep working exactly as before.

This is the first task for the headless coder (TASK-23): small, unit-testable, no new E2E test needed — the existing E2E suite on the Pi (check e2e-pi) must stay green.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 No naive datetime.now() remains in custom_components/2n_intercom (grep finds none); the four places use dt_util.utcnow()
- [ ] #2 After a ring event coordinator._last_ring_time and _ring_pulse_until are tz-aware (tzinfo is not None) — new unit test in tests/test_coordinator.py
- [ ] #3 After a MotionDetected 'in' event coordinator._last_motion_time is tz-aware — new unit test (extend test_motion_detected_in_event or add one)
- [ ] #4 ring_active still returns True within the pulse and False after it, with tz-aware _ring_pulse_until (update the two existing ring_active tests at tests/test_coordinator.py ~1537 and ~1552 to datetime.now(timezone.utc); do not delete them)
- [ ] #5 Doorbell and motion binary sensors expose last_ring / last_motion with a UTC offset when given a tz-aware time — new unit tests in tests/test_binary_sensor.py; the existing tests stay as they are
- [ ] #6 Full unit suite, validate.py and py_compile green on Python 3.12+; PR check e2e-pi green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. coordinator.py: replace datetime.now() with dt_util.utcnow() at the four places (motion :354, ring :875, ring_active compare :1326, snapshot cache :1537). Keep datetime import for type hints.
2. tests/test_coordinator.py: update ring_active tests to use datetime.now(timezone.utc); add/extend tests asserting _last_ring_time, _ring_pulse_until, _last_motion_time are tz-aware (tzinfo is not None).
3. tests/test_binary_sensor.py: add tests with aware datetime (timezone.utc) asserting last_ring/last_motion isoformat ends with +00:00; keep existing naive tests.
4. Run unittest discover, validate.py, py_compile until green.
5. Record notes, commit, do not tick ACs or set Done.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented: replaced the four naive datetime.now() call sites in coordinator.py (motion :354, ring :875, ring_active compare :1326, snapshot cache :1537) with dt_util.utcnow(); dt_util was already imported, datetime import kept for type hints. grep confirms no datetime.now() remains in custom_components/2n_intercom. Updated tests/test_coordinator.py: test_ring_active_false_when_pulse_expired and test_ring_active_true_within_pulse now use datetime.now(timezone.utc); test_process_call_state_event_sets_ring_and_active_session asserts _last_ring_time.tzinfo and _ring_pulse_until.tzinfo are not None; test_motion_detected_in_event asserts _last_motion_time.tzinfo is not None. Added tests/test_binary_sensor.py::test_doorbell_extra_state_attributes_tz_aware_last_ring and test_motion_sensor_extra_state_attributes_tz_aware asserting the last_ring/last_motion isoformat strings end with +00:00; existing naive-input tests left unchanged. Verified: python3 -m unittest discover -s tests -t tests (565 tests, OK), python3 validate.py (all checks passed), python3 -m py_compile custom_components/2n_intercom/*.py (OK). Did not run e2e.sh per headless rules; e2e-pi PR check will validate on the Pi. Committed on branch task-2.1-b1-use-tz-aware-timestamps-in-the-coordi, not pushed.
<!-- SECTION:NOTES:END -->
