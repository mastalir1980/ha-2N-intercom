---
id: TASK-2.1
title: 'B1: use tz-aware timestamps in the coordinator instead of naive datetime.now()'
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-12 19:54'
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
1. custom_components/2n_intercom/coordinator.py: replace datetime.now() with dt_util.utcnow() at the four places (:354, :875, :1326, :1537). dt_util is already imported (line 19). Keep 'from datetime import timedelta, datetime' because datetime is used in type hints.
2. tests/test_coordinator.py: change the ring_active tests (~1537, ~1552) to use datetime.now(timezone.utc); add asserts/tests that _last_ring_time, _ring_pulse_until (after a ring CallStateChanged event, see existing ring tests for how to feed one) and _last_motion_time (after MotionDetected in) have tzinfo not None. tests/_stubs.py already makes dt_util.utcnow() return an aware UTC datetime.
3. tests/test_binary_sensor.py: add one test per sensor with an aware datetime (datetime(2026, 4, 12, 10, 0, tzinfo=timezone.utc)) asserting the attribute ends with '+00:00'. Leave the existing naive-input tests unchanged.
4. Do not change: api.py, binary_sensor.py (it already calls isoformat()), diagnostics.py, any e2e/ file, CHANGELOG/version (only release tasks). Architecture rules in CLAUDE.md (event-driven, dual auth) are untouched by this change.
5. Run: python3 -m unittest discover -s tests -t tests; python3 validate.py; python3 -m py_compile custom_components/2n_intercom/*.py.
<!-- SECTION:PLAN:END -->
