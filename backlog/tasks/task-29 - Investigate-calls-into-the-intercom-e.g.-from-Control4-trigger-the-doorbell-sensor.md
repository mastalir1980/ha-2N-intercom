---
id: TASK-29
title: >-
  Investigate: calls into the intercom (e.g. from Control4) trigger the doorbell
  sensor
status: Done
assignee:
  - '@claude'
created_date: '2026-10-13 19:03'
updated_date: '2026-10-13 19:55'
labels:
  - ring-detection
  - github-issue
dependencies: []
references:
  - custom_components/2n_intercom/coordinator.py
  - docs/ARCHITECTURE.md
  - tests/test_coordinator.py
  - 'https://github.com/mastalir1980/ha-2N-intercom/issues/10'
priority: medium
type: spike
ordinal: 37000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GitHub issue #10, comment 2026-04-25 point 4: when a Control4 user starts an intercom call to the DS2 door station, the HA doorbell binary sensor turns on - a false ring.

Fact from code: `coordinator.py` treats a call event as a ring when state is in `_RING_STATES` and `direction != "outgoing"` (see the ring detection block that sets `_ring_detected`; docs/ARCHITECTURE.md ring section; unit tests `test_outgoing_ring_does_not_trigger` in tests/test_coordinator.py). A call coming INTO the intercom is direction incoming and ringing, so it passes the same test as a button press. Only the optional `called_id` peer filter can separate them today.

Hypothesis to verify (not yet confirmed): on a real button press the 2N reports the call from its own point of view, and the direction value for a button press vs. a call into the intercom differs from what the code assumes. Our tests only use synthetic events, and the docs were validated on IP Verso fw 2.50.

Goal of the spike: capture real log events (CallStateChanged, CallSessionStateChanged, and any button/key events) on the ground-truth IP Force 2.0 fw 3.3.x for (a) a visitor button press and (b) a call placed into the intercom (e.g. from the 2N app or a SIP phone), then decide how ring detection should tell them apart. Output is a decision plus a follow-up feature/bug task, not code.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Raw log events for a button press and for a call into the intercom are recorded on fw 3.3.x (secrets redacted) and attached to the task notes
- [x] #2 Notes state which field(s) reliably distinguish a visitor ring from a call into the intercom, or that none exists
- [x] #3 A follow-up task (bug or enhancement) is created with the proposed ring-detection change, or the task records why the called_id filter is the answer
- [x] #4 docs/API_REFERENCE.md records the observed direction semantics as a firmware fact
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Captured 2026-10-13 on IP Force 2.0 fw 3.3.x with e2e/scripts/capture_call_events.py (read-only log subscribe/pull). Peers redacted.

(a) Visitor button press (sessions 31, 32):
- CallSessionStateChanged state=initialized session=32 originator=button info="1"
- CallStateChanged state=connecting direction=outgoing session=32 peer=sip:<my2n-id>@proxy.my2n.com:5061
- CallSessionStateChanged state=connecting originator=button info="1"
- CallStateChanged state=ringing direction=outgoing session=32
- CallSessionStateChanged state=ringing originator=button info="1"   (no direction key)
- CallStateChanged state=terminated direction=outgoing reason=normal
- CallSessionStateChanged state=terminated originator=button info="1"

(b) Call INTO the intercom from the My2N app (session 33), auto-answered within the same second:
- CallSessionStateChanged state=initialized session=33 originator=incoming (no info)
- CallStateChanged state=ringing direction=incoming session=33 peer=sip:<my2n-id>@proxy-101.my2n.com
- CallSessionStateChanged state=ringing originator=incoming
- CallStateChanged state=connected direction=incoming
- CallSessionStateChanged state=connected originator=incoming
- CallStateChanged state=terminated direction=incoming reason=normal
- CallSessionStateChanged state=terminated originator=incoming

Findings (fact):
- direction is from the intercom's point of view: button press = outgoing, call into the intercom = incoming.
- CallSessionStateChanged has no direction; it carries originator (button | incoming seen) and info (button number for originator=button).
- Replaying (a) through current coordinator._process_log_event: CallStateChanged ringing/outgoing is ignored; CallSessionStateChanged ringing (empty direction) passes `direction != "outgoing"` and sets the ring. So the doorbell today works only via CallSessionStateChanged, by accident.
- (b) passes the same check twice (CallStateChanged incoming + CallSessionStateChanged) -> false ring. This is issue #10 point 4.

Open (needs Jan): which originator values count as a ring (only "button", or anything except "incoming"); other originator values (keypad, display/directory, api) not observed yet. Unknown whether fw 2.50 sends originator.

Decision (Jan, 2026-10-13): everything the intercom started rings - CallStateChanged ringing+outgoing, or CallSessionStateChanged ringing with originator present and != incoming; anything incoming never rings. Rejected: originator=button only (would risk keypad/display calls whose originator we have not seen). Follow-ups: TASK-31 (bug, ring-detection fix, @copilot), DRAFT-1 (per-button doorbell, needs design).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Captured real call events on IP Force 2.0 fw 3.3.x for a button press and a call into the intercom (notes). direction/originator are from the intercom's point of view; the current check rings on incoming calls and on button presses only via CallSessionStateChanged without direction. Rule decided with Jan; fix in TASK-31, per-button doorbell in DRAFT-1; firmware fact added to docs/API_REFERENCE.md.
<!-- SECTION:FINAL_SUMMARY:END -->
