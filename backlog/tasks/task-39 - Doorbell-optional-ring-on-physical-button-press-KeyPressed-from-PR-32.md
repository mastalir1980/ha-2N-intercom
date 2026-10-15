---
id: TASK-39
title: 'Doorbell: optional ring on physical button press (KeyPressed), from PR #32'
status: To Do
assignee: []
created_date: '2026-10-15 13:01'
updated_date: '2026-10-15 13:15'
labels:
  - doorbell
  - coordinator
  - github-pr
  - on-hold
dependencies:
  - TASK-31
references:
  - 'https://github.com/mastalir1980/ha-2N-intercom/pull/32'
  - custom_components/2n_intercom/coordinator.py
  - docs/API_REFERENCE.md
priority: low
type: feature
ordinal: 46000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
External PR #32 (vemboy200, port of jasonjhofmann's savek-cc#1) adds ring_on_keypress: subscribe to the KeyPressed log event (only when /api/log/caps lists it) and pulse the doorbell on a physical button press. Why it is useful: a button with no call destination (empty directory) emits only KeyPressed, never a call event, so today it never rings. The PR's second option ring_on_call is NOT taken: TASK-31 fixes the false ring from issue #10 at the source.

Decided with Jan 2026-10-15: keep the idea, not now (on-hold until Jan schedules it). Preferred route: vemboy200 rebases PR #32 on main after TASK-31, drops ring_on_call and addresses the review below; otherwise the coder implements it from this task, crediting PR #32 / savek-cc#1.

Review points agreed so far (draft review, not yet posted):
- Off by default: with it on, a called_id filter would be bypassed (no call, so the peer filter cannot apply).
- KeyPressed is believed to fire for keypad keys too; only call buttons may ring (key values to be confirmed from a real device).
- After TASK-31 a press that starts a call already rings via CallStateChanged direction=outgoing; KeyPressed for the same press must not cause a second pulse or snapshot.
- A KeyPressed-only ring should capture the ring snapshot like the call path.
Open question before this is ready: which key values the E2E intercom (fw 3.x) and the PR author's Control4 unit emit for call buttons vs keypad (capture /api/log/caps and a KeyPressed sequence). Related: DRAFT-1 (per-button doorbell, last_key_pressed).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 New option ring_on_keypress (entry.options, default off) in the options flow with strings.json and en/de/cs translations; existing installs keep today's behaviour
- [ ] #2 KeyPressed is added to the log subscription only when the option is on and /api/log/caps lists it; a device without it keeps a working subscription - unit test
- [ ] #3 A KeyPressed for a call button pulses the doorbell and clears it after the pulse duration without waiting for a poll - unit test
- [ ] #4 KeyPressed for keypad keys (digits, *, #) never rings - unit test
- [ ] #5 Full sequence KeyPressed + CallStateChanged(outgoing) + CallSessionStateChanged for one press gives exactly one ring and one snapshot - unit test
- [ ] #6 A KeyPressed-only ring captures the ring snapshot when ring snapshots are enabled - unit test
- [ ] #7 README options table documents the option, that called_id does not apply to button presses, and the keypad behaviour
- [ ] #8 Full unit suite, validate.py, py_compile green; PR check e2e-pi green; Jan verifies a press on the E2E intercom with the option on and off (manual-close)
<!-- AC:END -->
