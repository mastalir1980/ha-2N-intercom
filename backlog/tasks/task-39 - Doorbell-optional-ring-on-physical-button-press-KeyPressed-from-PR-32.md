---
id: TASK-39
title: 'Doorbell: optional ring on physical button press (KeyPressed), from PR #32'
status: To Do
assignee:
  - '@copilot'
created_date: 2026-10-15 13:01
updated_date: '2026-10-24T08:28:00Z'
labels:
  - doorbell
  - coordinator
  - github-pr
milestone: m-1
dependencies:
  - TASK-31
references:
  - https://github.com/mastalir1980/ha-2N-intercom/pull/32
  - custom_components/2n_intercom/coordinator.py
  - docs/API_REFERENCE.md
priority: low
type: feature
ordinal: 46000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
External PR #32 (vemboy200, port of jasonjhofmann's savek-cc#1) adds ring_on_keypress: subscribe to the KeyPressed log event (only when /api/log/caps lists it) and pulse the doorbell on a physical call-button press. Why it is useful: a button with no call destination (empty directory) emits only KeyPressed, never a call event, so today it never rings. The PR's former second option ring_on_call is NOT taken: TASK-31 fixes the false ring from issue #10 at the source.

Status 2026-10-21: vemboy200 reworked PR #32 per this task (commits e3b4d6d, 3aab1b7, rebased on main, mergeable): ring_on_call dropped, option off by default, only call-button keys ("%1".."%54") ring, keypad digits/*/# never ring and the key value is never logged, one ring and one snapshot per press in both event orders, snapshot on a KeyPressed-only ring, called_peer cleared on a press ring, README + en/cs/de translations, new tests/test_coordinator_keypress.py (739 unit tests pass per the PR). Key values come from the 2N Logged Events manual and his Control4 DS2 / DS2 Mini (fw 2.43). Claude reviewed the diff: all review points from 15 Oct are covered.

Decided with Jan 2026-10-21: ship in v1.6.0 (not v1.5.0, which is in release). Accepted trade-off: when KeyPressed arrives before the call events, the single ring has no called_peer (documented in README; option is opt-in). Route as for TASK-49 / PR #30: the headless coder carries PR #32 because e2e-pi does not run on fork PRs - cherry-pick both commits keeping vemboy200 as author (and the jasonjhofmann co-author line), resolve conflicts with main, add nothing beyond review fixes, PR body credits the contributor and says "Closes #32". Jan told vemboy200 the plan on PR #32. Keep the on-hold label until v1.6.0 work starts (after the v1.5.0 release), then remove it and assign @copilot.

Open: confirm the call-button key value and event order of a press that places a call on the E2E intercom (IP Force, fw 3.x) during the AC #8 manual check. Related: DRAFT-1 (per-button doorbell, last_key_pressed).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 New option ring_on_keypress (entry.options, default off) in the options flow with strings.json and en/de/cs translations; existing installs keep today's behaviour [unit]
- [ ] #2 KeyPressed is added to the log subscription only when the option is on and /api/log/caps lists it; a device without it keeps a working subscription - unit test [unit]
- [ ] #3 KeyPressed for keypad keys (digits, *, #) never rings and the key value is never logged - unit test [unit]
- [ ] #4 Full sequence KeyPressed + CallStateChanged(outgoing) + CallSessionStateChanged for one press gives exactly one ring and one snapshot - unit test [unit]
- [ ] #5 A KeyPressed-only ring captures the ring snapshot when ring snapshots are enabled - unit test [unit]
- [ ] #6 README options table documents the option, that called_id does not apply to button presses, and the keypad behaviour [unit]
- [ ] #7 Full unit suite, validate.py and py_compile green; PR check e2e-pi green with the option off (default) [e2e]
- [ ] #8 Jan presses the call button on the E2E intercom with the option on (one ring) and off (behaviour as in 1.5.0), and records the key value and event order seen [jan]
- [ ] #9 A KeyPressed for a call button fires one ring on the doorbell event entity, the same way an intercom-started call does, without waiting for a poll - unit test [unit]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Branch task-39-… from origin/main; cherry-pick PR #32 commits e3b4d6d and 3aab1b7 keeping vemboy200 as author and the jasonjhofmann Co-authored-by line.
2. Resolve conflicts with main (TASK-71 log-caps filtering if merged, 1.5.0 doorbell event entity instead of the removed binary_sensor: a press ring must fire the doorbell event entity ring exactly like a call ring).
3. Add only review fixes and verifier-tag evidence; no new behaviour beyond the ACs.
4. Unit suite (tests/test_coordinator_keypress.py from the PR plus existing), validate.py, py_compile.
5. PR body credits vemboy200 and jasonjhofmann and says "Closes #32".
Must not change: ring detection for calls (TASK-31/45/47), called_id filter semantics for calls, graceful degradation of the log subscription.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 (Jan): v1.6.0 work starts after the v1.5.0 release; on-hold removed, assigned @copilot. Coordinate with TASK-71 (v1.5.1, filters every subscribed event by /api/log/caps): KeyPressed must follow the same caps rule. If TASK-71 is merged first, rebase on it.
<!-- SECTION:NOTES:END -->
