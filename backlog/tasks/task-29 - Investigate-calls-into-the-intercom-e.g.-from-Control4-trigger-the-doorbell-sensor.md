---
id: TASK-29
title: >-
  Investigate: calls into the intercom (e.g. from Control4) trigger the doorbell
  sensor
status: To Do
assignee: []
created_date: '2026-10-13 19:03'
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
- [ ] #1 Raw log events for a button press and for a call into the intercom are recorded on fw 3.3.x (secrets redacted) and attached to the task notes
- [ ] #2 Notes state which field(s) reliably distinguish a visitor ring from a call into the intercom, or that none exists
- [ ] #3 A follow-up task (bug or enhancement) is created with the proposed ring-detection change, or the task records why the called_id filter is the answer
- [ ] #4 docs/API_REFERENCE.md records the observed direction semantics as a firmware fact
<!-- AC:END -->
