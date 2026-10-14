---
id: TASK-31
title: >-
  Ring detection: only calls started by the intercom ring the doorbell, calls
  into the intercom never do
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-13 19:54'
updated_date: '2026-10-14 14:48'
labels:
  - bug
  - coordinator
  - manual-close
  - on-hold
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

Evidence (TASK-29 notes, captured on IP Force 2.0 fw 3.3.x; direction is from the intercom's point of view, see docs/API_REFERENCE.md firmware quirks):
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
Label manual-close: a ring needs a physical button press, so Jan verifies on the IP Force after/at review and closes the task.
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
- [ ] #9 Manual (Jan, IP Force on staging): button press -> doorbell on; call into the intercom from My2N -> doorbell stays off
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. coordinator.py, call-event handling (the block after `if event_name not in {"CallStateChanged", "CallSessionStateChanged"}`): read `originator` (lower-cased, optional) from params; compute is_ringing per event type as in the description. Keep session/peer/active_session handling, snapshot-once logic, ring pulse and the reset branch unchanged.
2. Remove "incoming" from _RING_STATES. Do not touch _extract_active_session_id (polling path).
3. tests/test_coordinator.py: switch ring-path fixtures from direction incoming to outgoing (lines ~106-408, ~675, ~819; tests/test_init.py ~221) where the test means a visitor ring; invert test_outgoing_ring_does_not_trigger into an incoming test; add the CallSessionStateChanged originator tests and the two full-sequence replays (copy the sequences from TASK-29 notes, peers fake).
4. docs/ARCHITECTURE.md lines ~115-117: new rule. docs/API_REFERENCE.md already has the firmware fact.
5. Must not change: event-driven ring only (no polling-based ring), graceful handling of unknown/malformed call events, tz-aware timestamps (dt_util.utcnow), called_id semantics.
6. Run unittest discover, validate.py, py_compile.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-14 (Claude): ON HOLD until PR #32 (external, vemboy200) is decided. #32 adds ring_on_call (a toggle for the same false ring) and ring_on_keypress. Recommendation to Jan: land this task's rule fix and take only ring_on_keypress from #32 (opt-in). The headless coder and the grooming agent must not start this task while the label on-hold is set.
<!-- SECTION:NOTES:END -->
