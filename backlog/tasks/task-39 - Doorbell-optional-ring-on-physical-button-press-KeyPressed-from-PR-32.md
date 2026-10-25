---
id: TASK-39
title: 'Doorbell: optional ring on physical button press (KeyPressed), from PR #32'
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-15 13:01'
updated_date: '2026-10-25 16:16'
labels:
  - doorbell
  - coordinator
  - github-pr
milestone: m-1
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
1. Carry PR #32 commits e3b4d6d and 3aab1b7 onto the checked-out task branch, preserving vemboy200 authorship and the jasonjhofmann co-author trailer.
2. Resolve conflicts against current log-capability filtering and the doorbell event entity; preserve call-origin and called_id semantics, default-off behavior, and graceful subscription degradation.
3. Extend focused unit coverage for the option, supported call-button keys, privacy, both event orders, snapshot deduplication, and immediate event-entity delivery; add read-only E2E coverage for the default-off option. Update directly related docs only.
4. Run focused tests, then the full Python 3.12 unit suite, validate.py, and py_compile. Record evidence and contributor/PR-body handoff notes without checking criteria or finalizing status. Commit locally with TASK-39 messages; do not push or access devices.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 (Jan): v1.6.0 work starts after the v1.5.0 release; on-hold removed, assigned @copilot. Coordinate with TASK-71 (v1.5.1, filters every subscribed event by /api/log/caps): KeyPressed must follow the same caps rule. If TASK-71 is merged first, rebase on it.

Carried PR #32 commits e3b4d6d and 3aab1b7 as b566ebe and 5350d8a, preserving vemboy200 authorship (original Git author spelling vemboy20), author dates, and the original jasonjhofmann/Claude co-author trailers. Commit subjects use the required TASK-39 prefix. The only merge conflict was the subscription-builder docstring; retained current TASK-71 filtering of every event against non-empty log caps.
Review fixes: never log any KeyPressed value (including call-button values), accept only documented call-button keys %1 through %54, and retain the pending press guard across initialized/connecting events so the subsequent call cannot produce a second ring/snapshot. The new regression reproduced a double ring before this fix. Call-origin rules and called_id matching for calls are unchanged; press rings intentionally bypass the peer filter.
Extended contributor tests for current caps filtering, empty/failed caps, caps changes, all 54 call buttons, every keypad digit, malformed/out-of-range keys, privacy, event ordering including call initialization, filtered calls, timer cleanup, snapshot deduplication, default-off setup/options wiring, and immediate event-entity delivery through the real log-pull publisher without polling. Added read-only E2E assertions for the options form and default-off subscription versus the independent device log/caps. Updated architecture/API docs; contributor README and en/de/cs translations retained.
Local validation on Python 3.12.15: focused coordinator/subscription/event/options/setup suites passed (414 tests); full unittest discovery passed (791 tests); validate.py passed; py_compile passed for all integration modules and both modified E2E test files. Existing RuntimeWarnings originate from unchanged coroutine mocks in tests/test_api.py. No devices, E2E runners, relay actions, or protected paths were accessed/modified.
AC #1: tests/test_config_flow.py::OptionsFlowTests.test_ring_on_keypress_defaults_off_and_is_saved and tests/test_init.py::IntegrationSetupTests.test_setup_passes_default_off_and_saved_keypress_option pass. strings.json and all three translations contain the option; existing translation consistency tests pass.
AC #2: tests/test_coordinator_keypress.py::KeyPressedSubscriptionTests passes for enabled/disabled options, supported/unsupported/empty/failed caps, and capability changes while preserving the TASK-71 subscription filter.
AC #3: KeyPressedRingTests.test_keypad_keys_never_ring, test_pin_entry_does_not_ring and test_key_values_are_never_logged pass; no key values are used as logging arguments.
AC #4: KeyPressedRingTests.test_press_that_starts_a_call_rings_once proves one ring and one snapshot with key-first/call-first/interleaved events and initialized/connecting events. DoorbellEventTests.test_keypress_and_both_call_events_emit_one_ring_in_each_order proves one event with separate or batched publication.
AC #5: KeyPressedRingTests.test_call_button_press_rings_once_with_snapshot and test_call_button_press_without_snapshot_option pass.
AC #6: README Options table documents ring_on_keypress=false, keypad exclusion, called_id bypass and the accepted missing-called_peer trade-off.
AC #7: all 791 unit tests, validate.py and py_compile passed locally. E2E evidence remains pending: e2e-pi must run on the orchestrator PR with the option off. New read-only coverage is in e2e/tests/test_40_options_flow.py and test_50_access_control.py.
AC #8: manual, pending Jan. Press the call button with the option on/off and record the device-reported key value/event order privately; integration logs deliberately never reveal keys. No physical action was attempted.
AC #9: tests/test_event.py::DoorbellEventTests.test_keypress_log_pull_fires_event_without_polling passes using the real coordinator pull/publish path and event entity; it also proves called_id bypass and removal of a previous called_peer.
PR body handoff (required for the orchestrator): Carries PR #32 by @vemboy200, based on the original contribution by @jasonjhofmann in savek-cc/ha-2N-intercom#1. Original contributor authorship and co-author credits are preserved. Includes only current-main compatibility, review fixes, tests, and documentation for TASK-39.

Closes #32

Task remains In Progress; no acceptance criteria were checked and no final status was set. No push or PR creation was attempted; the orchestrator owns that step.
<!-- SECTION:NOTES:END -->
