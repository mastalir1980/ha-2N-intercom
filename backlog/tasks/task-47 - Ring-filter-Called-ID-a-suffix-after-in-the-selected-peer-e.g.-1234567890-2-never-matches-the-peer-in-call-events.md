---
id: TASK-47
title: >-
  Ring filter (Called ID): a suffix after "/" in the selected peer (e.g.
  "1234567890/2") never matches the peer in call events
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-16 14:40'
updated_date: '2026-10-18 16:09'
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
- [x] #1 Called ID "1234567890/2" rings on a button press whose call events carry peer "1234567890" - unit test replaying the TASK-29 button-press sequence
- [x] #2 Called ID "1234567890/2" does not ring for an incoming call (TASK-31 rule) - unit test
- [x] #3 Canonical form: "1234567890/2", "1234567890/1", "1234567890", "sip:1234567890@proxy.my2n.com:5061" and "1234567890@host;transport=tls" all canonicalize to "1234567890" - unit test on `_normalize_peer`
- [x] #4 No over-matching: Called ID "1234567891" (with or without "/2") does not match event peer "1234567890" and filters the ring - unit test
- [x] #5 The DEBUG call-event line includes the canonical configured Called ID ("all" for All calls); no raw URL, no credentials - unit test asserts the line
- [x] #6 "All calls" behaviour unchanged; existing tests stay green
- [x] #7 Full unit suite, validate.py and py_compile green on Python 3.12+; PR check e2e-pi green (no new E2E test: a ring needs a physical press)
- [x] #8 docs/ARCHITECTURE.md and README.md state in one sentence that the Called ID part after "/" is ignored when matching
- [x] #9 Manual (Jan, label manual-close): with Called ID set to a peer with a "/" suffix, a button press turns the Doorbell on and the debug log shows the configured filter and decision "rang"
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Extend coordinator._normalize_peer to discard everything after the first slash alongside the existing delimiters, without rewriting the stored Called ID option.
2. Include the canonical configured filter (or all) in call-event DEBUG messages while retaining the existing ring decisions, direction/originator checks and per-session peer sets.
3. Extend coordinator unit tests with slash normalization, captured button-press and incoming-call replays, non-matching peers, and canonical-only DEBUG logging assertions.
4. Document slash-suffix matching in README.md and docs/ARCHITECTURE.md.
5. Run the Python 3.12 local gates, record implementation notes and commit locally. Leave acceptance criteria unchecked and status In Progress; e2e-pi and the manual-close device check remain external gates.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented slash-suffix removal in _normalize_peer after SIP scheme removal; the stored Called ID option is unchanged. All call-event DEBUG paths now include the canonical configured filter (filter=all for All calls), without raw SIP URLs, host names or passwords.

Extended the TASK-29 button-press replay with 1234567890/1 and /2, exact non-matches 1234567891 and 1234567891/2, and decision assertions. Extended the incoming-call replay with 1234567890/2, preserving the TASK-31 direction/originator rule. Added normalization coverage, slash-form interchangeability and canonical-only logging assertions for both event types and malformed events. Existing per-session peer-set and polling behavior is unchanged.

README.md and docs/ARCHITECTURE.md document that the Called ID suffix after / is ignored, and describe the canonical filter in DEBUG logs.

Local gates passed on Python 3.12.15: python3 -m unittest discover -s tests -t tests (612 tests); python3 validate.py; python3 -m py_compile custom_components/2n_intercom/*.py. The full suite also emitted RuntimeWarnings from existing API failure-test mocks outside the changed code; no unrelated fixes were made.

No E2E command was run on the VM and no new E2E test was added, as specified by the task: a ring requires a physical press. The PR e2e-pi gate and Jan manual-close verification remain pending. Acceptance criteria are left unchecked and status remains In Progress.

Merged in PR #63 (2026-10-16). Label manual-close: moved to To Test by Claude after the merge; waits for Jan's check on the real device.

AC evidence (tester review 2026-10-18): #1-#6 unit tests (suffix replay, canonical forms, negative peers, debug line); #7 e2e-pi green on PR #63; #8 ARCHITECTURE.md + README. #9 manual (Jan).

AC evidence (tester review 2026-10-18): #1-#6 unit tests (suffix replay, canonical forms, negative peers, debug line); #7 e2e-pi green on PR #63; #8 ARCHITECTURE.md + README; #9 verified manually by Jan.
<!-- SECTION:NOTES:END -->
