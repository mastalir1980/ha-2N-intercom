---
id: TASK-45
title: >-
  Ring filter (Called ID): a specific peer blocks the ring because only the last
  peer seen is compared
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-15 19:16'
labels:
  - bug
  - coordinator
  - manual-close
milestone: m-0
dependencies: []
references:
  - custom_components/2n_intercom/coordinator.py
  - custom_components/2n_intercom/config_flow.py
  - custom_components/2n_intercom/binary_sensor.py
  - tests/test_coordinator.py
  - tests/test_config_flow.py
  - docs/ARCHITECTURE.md
  - >-
    backlog/tasks/task-31 -
    Ring-detection-only-calls-started-by-the-intercom-ring-the-doorbell-calls-into-the-intercom-never-do.md
priority: high
type: bug
ordinal: 52000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: on a production install (2026-10-15) the doorbell rings when Called ID is set to "All calls", but never rings when Called ID is set to a specific peer, although the call_state sensor shows "ringing" for the button press. Ring detection itself works (TASK-31); the peer filter rejects the ring.

Facts from the code (coordinator.py):
- The filter allows a ring only when `_last_called_peer == _ring_filter_peer` (ring_allowed in the call-event block). `_last_called_peer` is a single value: the peer of the LAST call event that carried a peer.
- Event peers are taken from `peer`/`address` and normalized by `_normalize_peer` (strip "sip:", cut at "@"). The selected Called ID comes from the options dropdown, filled with raw `callPos[].peer` values from dir/query (config_flow.py `_async_get_directory_choices`), normalized by the same function.
- The poll (`_async_update_data`, default 60 s) overwrites `_last_called_peer` with `calls[0].peer` of the first session from call/status, and sets it to None when no call is active.
- The `called_peer` attribute of the Doorbell entity exists only while `_last_called_peer` is set, so users cannot inspect it after the call; no call event is logged, so there is no evidence in the debug log either (production debug log 16:52-17:23 contains no call events at all).

Facts from the captured button press (TASK-29 notes, E2E intercom fw 3.x): only `CallStateChanged state=connecting direction=outgoing` carries the peer (`sip:<my2n-id>@proxy.my2n.com:5061`); the `ringing` events carry no peer.

Hypotheses (not yet distinguishable without logging, the fix must cover both):
1. The button calls more than one peer (group or parallel call, e.g. My2N app plus another phone); each CallStateChanged connecting overwrites `_last_called_peer`, so the last one called may not be the selected one.
2. The dropdown value (directory format) and the event value (call format, e.g. with port ":5061" or a different host) normalize to different strings.

Expected behaviour: a ring is allowed when the selected peer is ANY of the peers called in the current call session. The dropdown value and event values are compared in one canonical form. Every call event is logged at debug level so the next report carries evidence. "All calls" behaves exactly as today; incoming calls still never ring (TASK-31 rule unchanged).

Approach (for the implementer to confirm): keep a set of canonical peers per active call session, filled from CallStateChanged/CallSessionStateChanged peer/address and from all calls in call/status sessions (the poll adds to the set instead of overwriting it while a session is active); clear the set when the session ends. One canonical form: lower-case, drop "sip:"/"sips:" scheme, keep the user part before "@", drop any ";params" and ":port". Apply it to the stored option and to every event/status peer. Must not change: event-driven-only ring detection, TASK-31 direction/originator rule, snapshot deduplication, the doorbell pulse, config split (called_id stays in entry.options). No secrets in logs (peers are not secrets; never log credentials or URLs with credentials).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 With Called ID set to a specific peer, the replayed TASK-29 button-press sequence (peer only on CallStateChanged connecting) rings exactly once when that peer matches - unit test
- [ ] #2 A button press that calls two peers (two CallStateChanged connecting events with different peers in one session) rings when the selected peer is either the first or the second one; it does not ring when the selected peer is neither - unit tests
- [ ] #3 A poll during ringing (call/status with a different first call peer) does not remove a peer already seen in the active session - unit test
- [ ] #4 Peer forms "sip:X@proxy.my2n.com:5061", "sip:X@proxy-101.my2n.com", "X@host;transport=tls" and "X" all match a Called ID option stored as any of these forms - unit tests on the canonical form
- [ ] #5 Called ID "All calls" behaves as before; the incoming-call sequence from TASK-29 never rings with any Called ID - existing tests stay green
- [ ] #6 Every CallStateChanged and CallSessionStateChanged is logged at DEBUG with event name, state, direction, originator, session, canonical peer(s) of the session and the ring decision (rang / filtered by peer / not a ring) - unit test asserts the log line, no credentials in it
- [ ] #7 Full unit suite, validate.py and py_compile green on Python 3.12+; PR check e2e-pi green (no new E2E test: a ring needs a physical press)
- [ ] #8 Manual (Jan, label manual-close): with Called ID set to the specific peer, a button press turns the Doorbell on, and the debug log shows the call events with the peer and the decision
<!-- AC:END -->
