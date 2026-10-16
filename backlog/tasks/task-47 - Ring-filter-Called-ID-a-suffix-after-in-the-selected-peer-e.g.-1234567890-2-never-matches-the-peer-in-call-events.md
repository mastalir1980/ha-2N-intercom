---
id: TASK-47
title: >-
  Ring filter (Called ID): a suffix after "/" in the selected peer (e.g.
  "1234567890/2") never matches the peer in call events
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-16 14:40'
updated_date: '2026-10-16 15:07'
labels:
  - bug
  - coordinator
  - manual-close
milestone: m-0
dependencies: []
references:
  - custom_components/2n_intercom/coordinator.py
  - tests/test_coordinator.py
  - docs/ARCHITECTURE.md
  - README.md
  - TASK-45
  - TASK-31
  - TASK-29
priority: high
type: bug
ordinal: 54000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: on a production install (main at e96c963, debug log 2026-10-16) the doorbell rings only when Called ID is set to the peer without a suffix. With Called ID "1234567890/2" (value picked from the dropdown, i.e. `callPos[].peer` from dir/query) every button press is logged as `decision=filtered by peer`, although all call events of the press carry `peers=['1234567890']`.

Facts:
- Debug log: the same button-press event sequence was replayed four times; it rang twice and was filtered twice. The only difference was the saved Called ID (with and without "/2"; entry reloaded after each options update).
- `_normalize_peer` (coordinator.py) lower-cases, strips "sip:"/"sips:" and cuts at "@", ";" and ":", but NOT at "/". "1234567890/2" therefore stays "1234567890/2" and never equals the event peer "1234567890".
- Event peers from the device carry no "/" suffix (TASK-29 capture, the debug log above). The directory value carries the suffix. "/N" selects which SIP account of the intercom places the call (e.g. "/2" = the second SIP account, used for calls to My2N); it is not part of the called peer.
- The DEBUG call-event line logs the canonical peers of the session and the decision, but not the configured Called ID, so a "filtered by peer" decision cannot be explained from the log alone.

Expected: the suffix after "/" is ignored when matching (decided by Jan 2026-10-16). "1234567890/2", "1234567890/1", "1234567890" and "sip:1234567890@proxy.my2n.com:5061" all canonicalize to "1234567890" and match each other. The part after "/" is never relevant for matching the called peer (it only names the intercom's own SIP account), so it is always dropped.

Must not change: event-driven-only ring detection, TASK-31 direction/originator rule, TASK-45 per-session peer-set logic, "All calls" behaviour, config split (called_id stays in entry.options, stored raw; no migration of stored values).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Called ID "1234567890/2" rings on a button press whose call events carry peer "1234567890" - unit test replaying the TASK-29 button-press sequence
- [ ] #2 Called ID "1234567890/2" does not ring for an incoming call (TASK-31 rule) - unit test
- [ ] #3 Canonical form: "1234567890/2", "1234567890/1", "1234567890", "sip:1234567890@proxy.my2n.com:5061" and "1234567890@host;transport=tls" all canonicalize to "1234567890" - unit test on `_normalize_peer`
- [ ] #4 No over-matching: Called ID "1234567891" (with or without "/2") does not match event peer "1234567890" and filters the ring - unit test
- [ ] #5 The DEBUG call-event line includes the canonical configured Called ID ("all" for All calls); no raw URL, no credentials - unit test asserts the line
- [ ] #6 "All calls" behaviour unchanged; existing tests stay green
- [ ] #7 Full unit suite, validate.py and py_compile green on Python 3.12+; PR check e2e-pi green (no new E2E test: a ring needs a physical press)
- [ ] #8 docs/ARCHITECTURE.md and README.md state in one sentence that the Called ID part after "/" is ignored when matching
- [ ] #9 Manual (Jan, label manual-close): with Called ID set to a peer with a "/" suffix, a button press turns the Doorbell on and the debug log shows the configured filter and decision "rang"
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. coordinator.py `_normalize_peer`: also cut at the first "/" (after the scheme removal, together with the "@", ";" and ":" cuts). Keep all other rules. The stored option stays raw; only the canonical form changes.
2. coordinator.py call-event DEBUG line (the one that logs canonical session peers and the ring decision): add the canonical configured filter (`self._ring_filter_peer`, or "all" when None). No raw URL, no credentials.
3. tests/test_coordinator.py: extend the `_normalize_peer` cases (AC #3, #4) and add ring replays with Called ID "1234567890/2" for the button-press sequence (TASK-29 pattern, peer only on CallStateChanged connecting) and for the incoming-call sequence (AC #1, #2); assert the DEBUG line (AC #5).
4. docs/ARCHITECTURE.md (ring filter section) and README.md (Called ID option): one sentence that the part after "/" is ignored when matching.

Must not change: see Description. Architecture rules in CLAUDE.md that apply: event-driven first; config split (entry.options); no secrets in logs.
<!-- SECTION:PLAN:END -->
