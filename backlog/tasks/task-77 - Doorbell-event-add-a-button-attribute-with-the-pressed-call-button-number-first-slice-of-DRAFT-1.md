---
id: TASK-77
title: >-
  Doorbell event: add a button attribute with the pressed call button number
  (first slice of DRAFT-1)
status: Done
assignee:
  - '@copilot'
created_date: '2026-11-01T19:26:00Z'
updated_date: '2026-11-21 12:37'
labels:
  - ring-detection
  - doorbell
milestone: m-1
dependencies: []
references:
  - custom_components/2n_intercom/coordinator.py
  - custom_components/2n_intercom/event.py
  - tests/test_coordinator.py
  - tests/test_coordinator_keypress.py
  - tests/test_event.py
  - README.md
  - docs/ARCHITECTURE.md
  - docs/API_REFERENCE.md
  - backlog/docs/analysis/doc-1 - Analysis-DRAFT-1-per-button-doorbell.md
  - 'https://github.com/mastalir1980/ha-2N-intercom/issues/10'
priority: medium
type: feature
ordinal: 83000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: an intercom with more than one call button cannot tell an automation which button was pressed. The doorbell `ring` event carries `called_peer`, `caller_name` and `caller_number`, but not the button. The only workaround is the `called_id` peer filter, which is one filter per config entry. This is the first slice of DRAFT-1 (option A in `doc-1`): one new `button` attribute on the existing `ring` event. DRAFT-1 stays as the place for the later design questions (one event type per button, button names, per-button filter).

**Current behaviour (fact from code).** `coordinator.py` `_process_log_event` reads `originator` of `CallSessionStateChanged` but never reads `info`. The button number is dropped. `_process_key_pressed_event` matches `%1`..`%54` with `_CALL_BUTTON_KEY` and throws the key away after the match. `event.py` `_handle_coordinator_update` builds the `ring` attributes only from `called_peer` and `caller_info`.

**Evidence (facts, captured read-only on the E2E intercom, fw 3.x).** A visitor press of the only button sends `CallSessionStateChanged` with `originator="button"` and `info="1"` in all four session events (`initialized`, `connecting`, `ringing`, `terminated`). `CallStateChanged` has no `info` (its keys are `call`, `sipAccount`, `sipAccountType`, `sipCallId`, `startTime`, `uuid`, plus state, direction, session and peer). The session events have no other keys. First capture: TASK-29 (2026-10-13). Second capture by the tester agent: 2026-11-01, same result. The `info` value is only ever the button number in these captures.

**Not verified (hypotheses).** (H1) `info` is `"2"`, `"3"`, ... for other buttons: only button 1 exists on the E2E intercom and nobody with a multi-button unit has been found. (H2) fw 2.50 does not send `originator`/`info`, so the ring still works and only the button is missing. (H3) Keypad, display directory and API calls use other `originator` values without a button number. The code must therefore treat `button` as optional and never depend on it for ring detection.

**Expected behaviour.**
- When a ring is detected and its button is known, the `ring` event has the attribute `button` (an integer, for example `2`). When the button is unknown, the attribute is absent, exactly like `called_peer` today.
- The button comes from `info` of the `CallSessionStateChanged` events of the same session when `originator` is `button` and `info` is a plain number. With `ring_on_keypress` on, a `KeyPressed` call-button key `%n` gives button `n`.
- A ring never reports the button of an earlier press (stale values are cleared).
- Ring detection, the `called_id` filter, the snapshot and the number of entities do not change.
- The README states that the button number is read from the intercom event and that only button 1 has been verified on real hardware.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A press sequence with `originator=button` and `info="1"` on `CallSessionStateChanged` makes the emitted `ring` event carry `button` = 1 (int); the same sequence with `info="2"` and `info="12"` gives 2 and 12; unit tests replay the captured event order [unit]
- [x] #2 A ring that is counted on the `CallStateChanged` ringing event, before the session ringing event, still reports the button stored from the earlier `initialized` session event of the same session [unit]
- [x] #3 Without a valid button the `ring` event has no `button` attribute and is otherwise unchanged: no `info`, empty, non-numeric (`"abc"`) and out-of-range (`"0"`, `"151"`) values are ignored without an error, and a call into the intercom (`originator=incoming`) still never rings [unit]
- [x] #4 A ring never reports the button of an earlier press: a second press without `info` after a press with `info="2"` has no `button`; two sessions at the same time keep their own buttons; the stored session button is removed on the terminal session state [unit]
- [x] #5 With `ring_on_keypress` on, `KeyPressed` key `%2` rings with `button` = 2; keypad keys still never ring; when call events and `KeyPressed` of one press arrive in either order there is one ring and the button is unchanged by the second event [unit]
- [x] #6 The doorbell event entity adds `button` to the `ring` attributes only when the coordinator has one, next to `called_peer`, `caller_name` and `caller_number`; no new entity, event type, option or translation key is added (checked in the PR diff) [unit]
- [x] #7 The debug line of the call-event branch includes `button`; no keypad key value is logged (`test_key_values_are_never_logged` stays green); `called_id` filter tests and the TASK-31 ring tests stay green unchanged [unit]
- [x] #8 README.md, docs/ARCHITECTURE.md and docs/API_REFERENCE.md describe the `button` attribute and state that only button 1 has been verified on real hardware (checked in the PR diff) [unit]
- [x] #9 The existing E2E doorbell entity checks stay green on the E2E intercom (`test_10_entities::test_doorbell_event_is_available_and_shares_camera_device`); the unit and E2E suites and `validate.py` pass [e2e]
- [x] #10 After the merge, the staging HA system log shows no error from `2n_intercom` about the log subscription or the doorbell event entity after a restart [tester]
- [x] #11 On the real intercom Jan presses the call button once: the doorbell event in Home Assistant shows the attribute `button: 1`, also with `ring_on_keypress` on; a second press shows it again and a call into the intercom from My2N does not ring [jan]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add optional per-session button storage and last_ring_button, parse only plain numeric session info in range 1..150, and clear session storage on terminal states. Preserve ring detection, called_id filtering, keypress matching and deduplication; set button only when a new ring is counted and include it in the existing call-event debug line. 2. Expose the optional integer button attribute on the existing doorbell ring event without new entities, options, event types or translations. 3. Extend coordinator, keypress and event unit tests for captured event ordering, invalid/missing values, isolation, cleanup and both keypress/call orders; retain the existing read-only E2E doorbell entity check required by AC #9. 4. Update README.md, docs/ARCHITECTURE.md and docs/API_REFERENCE.md with the optional attribute, automation example and real-hardware limitation. 5. Run the full Python unit suite, validate.py and integration py_compile, record implementation evidence in notes, and commit locally without checking criteria or finalizing the task. E2E and manual checks remain with the orchestrator, tester and Jan.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Approved by Jan in Telegram, 2026-11-01. Facts: button press on fw 3.x sends originator=button and info="1" on CallSessionStateChanged only (TASK-29 capture 2026-10-13; read-only capture by the tester agent 2026-11-01). Not verified: info for buttons 2 and up, fw 2.50. Out of scope (stay in DRAFT-1): one event type or entity per button, button names, per-button filter, migration of called_id.

Implemented optional session button metadata and last_ring_button. Only plain numeric string info from originator=button session events is accepted (trimmed, 1-3 ASCII digits, 1..150); invalid or missing values remain optional and never affect ring detection. A counted ring takes its own session button or None, terminal session states remove stored buttons, and accepted KeyPressed call buttons provide their integer number only when counting a new ring. The existing call-event debug line now includes the stored button. No ring rules, called_id filtering, key matching/hold, snapshots, entities, event types, options, translations, version or CHANGELOG were changed.

Unit evidence: SessionButtonTests and DoorbellEventTests replay the TASK-29 captured order for 1, 2 and 12, including the earlier initialized event and CallStateChanged ringing before session ringing. Missing/invalid info, wrong originators, non-string values, sessionless metadata, trimmed/range-boundary values, a second press without info, concurrent session isolation and every terminal state are covered. KeyPressedRingTests and DoorbellEventTests cover %2, both keypress/call event orders, stable metadata after a duplicate event and preserving one ring/snapshot. Existing TASK-31 and called_id tests remain unchanged; test_key_values_are_never_logged remains unchanged and passes.

README.md, docs/ARCHITECTURE.md and docs/API_REFERENCE.md describe the optional integer attribute, session storage/cleanup, info being absent from CallStateChanged, and only button 1 being verified on real hardware. The README automation uses the correct HA event-entity state-trigger path trigger.to_state.attributes.button (matching the existing blueprint), and explicitly distinguishes it from the plan wording trigger.event.attributes.button.

Local gates passed with Python 3.12.15: python3 -m unittest discover -s tests -t tests (811 tests), python3 validate.py and python3 -m py_compile custom_components/2n_intercom/*.py. The full suite still emits warnings from existing API failure-test mocks outside this task; those files were not changed.

AC #9: the existing read-only E2E test_10_entities::test_doorbell_event_is_available_and_shares_camera_device is retained unchanged, as requested by the task. E2E was not run from the VM; e2e-pi must provide the remaining evidence. New button metadata is proven locally by unit replay; a real press is intentionally the manual AC #11, not an automated device action. AC #10 remains with the tester after merge, and AC #11 remains with Jan. No acceptance criteria were checked and the task remains In Progress for independent review and orchestration.

2026-11-21: Jan confirmed in the conversation that he checked the whole v1.6.0 on staging and the real intercom; the outstanding manual criteria are closed on that statement.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented by the headless coder. Checks green on 14d4c62ef after 0 fix round(s): e2e-pi=pass, validate=pass, validate=pass. PR: https://github.com/mastalir1980/ha-2N-intercom/pull/119. To Test takes effect when the PR is merged.
AC #1: tests/test_coordinator.py SessionButtonTests.test_captured_button_sequences_store_integer_for_first_ring replays the captured 7-event order (_button_press_sequence) with info 1, 2, 12 and asserts int button from the ring onward, None before it. tests/test_event.py test_captured_sequences_emit_optional_integer_button_with_caller_metadata checks the emitted ring carries the int. Full suite (811 tests) passes locally. (proven)
AC #2: SessionButtonTests.test_call_ringing_uses_earlier_initialized_session_button: initialized session event stores the button, then CallStateChanged ringing counts the ring and last_ring_button == 12; debug line contains button=12. The replay test also rings on CallStateChanged (index 3) before the session ringing event. (proven)
AC #3: test_missing_and_invalid_info_leave_button_unknown covers missing, None, '', ' ', 'abc', '0', '151', '1234', non-strings and more: no button, no exception, ring_count still 1. test_only_button_session_events_store_info covers originator=incoming (ring_count 0, no button). test_event shows no 'button' key in the emitted attributes for those values; otherwise attributes are unchanged. (proven)
AC #4: test_next_press_without_info_clears_previous_button (second press after info '2' gives None, same and different session id), test_concurrent_sessions_keep_their_own_buttons (42-&gt;2, 43-&gt;12), test_terminal_session_state_removes_button_not_individual_call_end (_session_buttons empty after terminal session event), plus test_event test_second_press_without_info_does_not_emit_previous_button. Code: _last_ring_button is reassigned on every counted ring and the session entry is popped on a terminal session state. (proven)
AC #5: tests/test_coordinator_keypress.py: the assertion for %2 gives last_ring_button 2 (int); test_keypad_keys_never_ring asserts ring_count 0 and button None; test_all_documented_call_button_keys_ring checks the number per key; test_button_is_fixed_when_keypress_and_call_events_arrive_in_either_order and test_duplicate_event_does_not_replace_counted_button assert exactly one ring and an unchanged button in both orders. The existing '_ring_detected' guard remains first in _process_key_pressed_event. (proven)
AC #6: event.py diff adds only `if self.coordinator.last_ring_button is not None: attributes['button'] = ...` next to called_peer/caller_*. The diff has no change to strings.json, translations/*, icons.json, const.py or platform registration. tests/test_event.py asserts the attribute is present as an int when known and absent otherwise. (proven)
AC #7: The final debug line in the call-event branch now includes button=%r (asserted in test_call_ringing_uses_earlier_initialized_session_button and the invalid-info test via 'button=None'); the other debug lines are unchanged. test_key_values_are_never_logged is unchanged and green; the only changed existing test lines are the intentional {} -&gt; {'button': 1} expectation in test_event for a captured sequence with info; the called_id filter and TASK-31 tests are untouched and pass. (proven)
AC #8: The diff adds the button attribute description to README.md (doorbell bullet, ring_on_keypress paragraph, automation example, multi-button bullet), docs/ARCHITECTURE.md and docs/API_REFERENCE.md. Each states that only button 1 has been verified on real hardware. (proven)
AC #9: The orchestrator reports the unit suite, validate.py and all PR checks incl. e2e-pi green on this head; the diff does not touch e2e/tests, test_10_entities, entity count or event types, so the existing doorbell entity E2E check is unaffected. Locally the 811 unit tests pass. (proven)
AC #10: [tester] After the merge the tester agent must check the staging HA system log for 2n_intercom errors about the log subscription or the doorbell event entity after a restart. (manual)
AC #11: [jan] Jan must press the real call button (also with ring_on_keypress on), see `button: 1` on the doorbell event twice, and confirm a call into the intercom from My2N does not ring. (manual)

AC #10: confirmed by Jan on 2026-11-21 (manual check of the whole v1.6.0 before the release). (manual, confirmed)
AC #11: confirmed by Jan on 2026-11-21 (manual check of the whole v1.6.0 before the release). (manual, confirmed)
<!-- SECTION:FINAL_SUMMARY:END -->
