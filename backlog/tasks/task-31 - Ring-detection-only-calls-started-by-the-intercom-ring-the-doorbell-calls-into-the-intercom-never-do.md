---
id: TASK-31
title: >-
  Ring detection: only calls started by the intercom ring the doorbell, calls
  into the intercom never do
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-13 19:54'
updated_date: '2026-10-15 14:46'
labels:
  - bug
  - coordinator
  - manual-close
milestone: m-0
dependencies: []
references:
  - custom_components/2n_intercom/coordinator.py
  - tests/test_coordinator.py
  - tests/test_init.py
  - docs/ARCHITECTURE.md
  - docs/API_REFERENCE.md
  - 'https://github.com/mastalir1980/ha-2N-intercom/issues/10'
priority: high
type: bug
ordinal: 39000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: GitHub issue #10 point 4 - when Control4 (or the My2N app, or a SIP phone) calls INTO the door station, the HA doorbell turns on: a false ring. Investigation in TASK-29 also showed that a real button press rings today only by accident.

Evidence (TASK-29 notes, captured on E2E intercom fw 3.x; direction is from the intercom's point of view, see docs/API_REFERENCE.md firmware quirks):
- Button press: CallStateChanged state=ringing direction=outgoing; CallSessionStateChanged state=ringing originator=button info="1" (no direction key).
- Call into the intercom: CallStateChanged state=ringing direction=incoming; CallSessionStateChanged state=ringing originator=incoming.

Current behaviour (coordinator.py, call-event block that sets _ring_detected, `is_ringing = state in self._RING_STATES and direction != "outgoing"`):
- button press: CallStateChanged is ignored (outgoing); CallSessionStateChanged rings only because it has no direction (empty string passes the check).
- call into the intercom: both events pass -> false ring.
- _RING_STATES also contains "incoming" as a state value.

Expected behaviour (decided with Jan 2026-10-13: "everything the intercom started rings"):
- CallStateChanged rings when state is a ring state AND direction == "outgoing".
- CallSessionStateChanged rings when state is a ring state AND originator is present AND originator != "incoming". Without originator it is not a ring signal (CallStateChanged covers it).
- Nothing with direction=incoming or originator=incoming rings.
- The called_id peer filter keeps working as today.

Out of scope: per-button doorbell (DRAFT-1), new entities, polling-based ring detection.
Label manual-close: a ring needs a physical button press, so Jan verifies on the E2E intercom after/at review and closes the task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 CallStateChanged ringing + direction=outgoing sets the ring (ring_active True, last_ring_time set, ring snapshot captured once) - unit test
- [ ] #2 CallStateChanged ringing + direction=incoming does NOT ring - unit test (replaces test_outgoing_ring_does_not_trigger)
- [ ] #3 CallSessionStateChanged ringing + originator=button rings; originator=incoming does not; missing originator does not - unit tests
- [ ] #4 Replay of the full captured sequences from TASK-29 notes: button-press sequence rings exactly once (one snapshot), the incoming-call sequence never rings - unit tests
- [ ] #5 called_id filter still blocks a non-matching peer and allows a matching peer on an outgoing ring - existing tests updated to direction=outgoing and green
- [ ] #6 "incoming" is no longer in _RING_STATES; call_state sensor and active_session_id tracking behave as before for both sequences - unit test
- [ ] #7 docs/ARCHITECTURE.md ring-detection section describes the new rule (direction/originator from the intercom's point of view)
- [ ] #8 Full unit suite, validate.py and py_compile green on Python 3.12+; PR check e2e-pi green (no new E2E test: ring needs a physical press)
- [ ] #9 Manual (Jan, E2E intercom on staging): button press -> doorbell on; call into the intercom from My2N -> doorbell stays off
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Update coordinator.py call-event ring eligibility: CallStateChanged requires a ring state and outgoing direction; CallSessionStateChanged requires a ring state and a nonempty originator other than incoming. Remove incoming from _RING_STATES without changing polling session extraction, peer/session handling, snapshot deduplication, ring pulse or reset behavior.
2. Update visitor-ring fixtures in coordinator/setup and related snapshot tests to outgoing direction or button originator. Add direction/originator rejection and normalization coverage, matching/non-matching called_id coverage, and both complete TASK-29 sequence replays with synthetic peers and assertions for snapshots, ring state, call state and active session tracking.
3. Update only the ring-detection section of docs/ARCHITECTURE.md to explain the rule from the intercom point of view. No KeyPressed handling, new options, entities or E2E tests.
4. Run targeted coordinator/setup regressions, then the full unittest suite, validate.py and integration py_compile with Python 3.12+. Record implementation notes, retain unchecked criteria and In Progress status for manual-close, and commit locally without pushing. E2E remains the orchestrator PR check e2e-pi and physical verification remains with Jan.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-14 (Claude): put on hold while external PR #32 (ring_on_call + ring_on_keypress) was undecided.
2026-10-15 (Jan): decided - this task goes ahead now and is ready for the headless coder. From PR #32 ring_on_call is not taken (this task fixes the false ring at the source); ring_on_keypress is tracked separately as TASK-39 (later). Do not add any KeyPressed handling or new options here.

Implemented event-specific ring eligibility: CallStateChanged now requires outgoing direction, and CallSessionStateChanged requires a nonempty originator other than incoming. Removed incoming from _RING_STATES; polling extraction, peer/session handling, snapshot deduplication, pulse and reset logic remain unchanged.
Updated visitor-ring fixtures in test_coordinator.py and test_init.py. Also updated the directly affected existing RingSnapshotTests in test_coordinator_access.py to outgoing/button events and inverted their no-capture incoming-call regression. Added coverage for direction/originator normalization and missing values, all ring states, both called_id outcomes, and both full TASK-29 sequences using synthetic peers. Replays assert each event state, active session tracking, ring transitions and snapshot counts (button: exactly one; incoming: zero). Updated docs/ARCHITECTURE.md with the intercom-perspective rule.
Validation on Python 3.12.15: targeted coordinator/access/setup run passed 237 tests; full python3 -m unittest discover -s tests -t tests passed 593 tests; python3 validate.py passed; python3 -m py_compile custom_components/2n_intercom/*.py passed. The full suite emitted RuntimeWarnings from untouched API failure-test mocks, with no failures.
No E2E commands or device access were performed in headless mode. PR e2e-pi remains for the orchestrator; Jan must verify a physical button press and an incoming My2N call on staging. Task remains In Progress with all acceptance criteria unchecked because it is manual-close. No KeyPressed handling, options, new entities, release changes or protected-path edits.
<!-- SECTION:NOTES:END -->
