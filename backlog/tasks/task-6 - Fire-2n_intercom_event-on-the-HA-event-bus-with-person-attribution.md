---
id: TASK-6
title: Fire 2n_intercom_event on the HA event bus with person attribution
status: Done
assignee:
  - '@copilot'
created_date: '2026-08-30 09:27'
updated_date: '2026-11-21 12:37'
labels:
  - access-control
  - automation
  - coordinator
milestone: m-1
dependencies:
  - TASK-4
references:
  - custom_components/2n_intercom/coordinator.py
  - custom_components/2n_intercom/const.py
  - custom_components/2n_intercom/event.py
  - custom_components/2n_intercom/diagnostics.py
  - custom_components/2n_intercom/__init__.py
  - tests/_stubs.py
  - tests/test_coordinator_access.py
  - tests/test_coordinator.py
  - tests/test_coordinator_keypress.py
  - tests/test_event.py
  - tests/test_diagnostics.py
  - e2e/tests/test_50_access_control.py
  - README.md
  - docs/ARCHITECTURE.md
  - docs/API_REFERENCE.md
  - >-
    https://wiki.2n.com/hip/hapi/latest/en/5-prehled-funkci-http-api/5-10-api-log/5-10-1-api-log-caps
priority: high
type: feature
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: automations cannot react to who came to the door. TASK-4 parses the access-control log events, but only the latest one is kept in coordinator data and diagnostics; nothing reaches automations. The HA event bus (`<domain>_event`, the pattern of `deconz_event` / `hue_event`) is the standard channel for this, and later device triggers (`device_id`), the access event entity (TASK-5) and the security events (TASK-7) build on it.

**Current behaviour (facts from code, main fbbcd0b).**
- `coordinator.py` `_process_access_event` parses the 10 access events into a frozen `AccessEvent` and stores only `_last_access_event`. `_async_run_log_subscription` processes a whole pull batch and calls `_publish_event_state()` once, so anything that reads "the latest event" sees only the last event of a batch (one card swipe = `CardEntered` + `UserAuthenticated` + `AccessTaken`).
- There is no `hass.bus.async_fire` in `custom_components/` (the only bus use is `async_listen_once` for HA stop in `__init__.py`).
- A ring is counted in two places: the call-event branch of `_process_log_event` (`if not self._ring_detected: self._ring_count += 1`) and `_process_key_pressed_event`. `event.py` `_handle_coordinator_update` builds the `ring` attributes (`called_peer`, `button` from TASK-77, `caller_name`, `caller_number`) inline.
- `__init__.py` `async_setup_entry` starts the log listener before `async_forward_entry_setups`, so the device can be missing from the device registry for the very first events.

**Evidence (2N HTTP API manual, 5.10.1 api log caps, https://wiki.2n.com/hip/hapi/latest/en/5-prehled-funkci-http-api/5-10-api-log/5-10-1-api-log-caps, checked 2026-11-01).** Permanent / conditioned parameters: `CardEntered` "reader, uid, valid" / "ap, session, direction, uuid"; `CodeEntered` "code, valid" / "ap, session, direction, input, type, uuid, reason"; `MobKeyEntered` "action, authid, valid" / "ap, session, direction, uuid"; `FingerEntered` "valid" / "ap, session, direction, uuid"; `UserAuthenticated` "ap, session, name" / "uuid, apbBroken"; `UserRejected` "ap, session, name" / "uuid, reason"; `AccessTaken` "ap, session"; `AccessBlocked` "ap, state"; `AccessLimited` "ap, type, state"; `ApiAccessRequested` "ap, valid" / "session, uuid". So only `UserAuthenticated` and `UserRejected` always carry the user name from the device; for the other events the name comes from the TASK-4 dir/query cache and can be unknown. Not verified: no access event has been captured on the E2E intercom yet; the parameter names come from the manual and the TASK-4 parser.

**Expected behaviour (design decisions, Claude 2026-11-01).**
- D1. Event name `2n_intercom_event` (`DOMAIN + "_event"`).
- D2. One bus event per accepted log event, fired when the event is parsed, in device order. An event the parser rejects fires nothing.
- D3. `type` values: `ring`; `card_entered` (CardEntered), `code_entered` (CodeEntered), `mobile_key_entered` (MobKeyEntered), `fingerprint_entered` (FingerEntered), `user_authenticated` (UserAuthenticated), `user_rejected` (UserRejected), `access_taken` (AccessTaken), `access_blocked` (AccessBlocked), `access_limited` (AccessLimited), `api_access_requested` (ApiAccessRequested).
- D4. Every payload: `device_id`, `config_entry_id`, `type`, `timestamp` (ISO 8601, UTC). Access payload: always all fields of `AccessEvent.as_dict()` except `event_type` (`credential_type`, `access_point`, `direction`, `granted`, `reason`, `state`, `user_uuid`, `user_name`, `session`), `null` when unknown, so `event_data` triggers and templates see a fixed schema. Ring payload: the same attributes the doorbell event entity puts on its `ring` event (one shared helper), absent when unknown, exactly like the entity.
- D5. Never in a payload or a log line: `code`, `uid`, `authid`, `reader` or any raw param. No user name or uuid in log lines.
- D6. A bus `ring` is fired for every counted ring, with the same rules as the doorbell entity (TASK-31: calls into the intercom never ring; `called_id` filter; one ring per press; `ring_on_keypress`), also when the doorbell entity is disabled.
- D7. Not fired: MotionDetected, SwitchStateChanged, InputChanged, OutputChanged, RegistrationStateChanged, ConfigurationChanged, CapabilitiesChanged, DeviceState, DirectoryChanged, KeyPressed that does not ring. Security events are TASK-7.
- D8. `user_name` is best effort: the event is fired at once and never delayed or fired again when a later directory refresh back-fills the name. The README tells users to match on `user_uuid`, or on `user_authenticated`, which always has the name.
- D9. Diagnostics get an `event_bus` section (event name, the types this entry can fire, a count per fired type) so E2E and the tester can see the channel without a physical press.

Out of scope: device triggers, the access event entity (TASK-5), security events (TASK-7), `apbBroken`, user attribution for `AccessTaken`, logbook descriptions, CHANGELOG/version (release task).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every access event that `_process_access_event` accepts fires exactly one `2n_intercom_event` with the D3 `type` (all 10 types tested); replaying `CardEntered`, `UserAuthenticated` and `AccessTaken` in one pull batch fires three bus events in that order [unit]
- [x] #2 The access payload has exactly the keys `device_id`, `config_entry_id`, `type`, `timestamp`, `credential_type`, `access_point`, `direction`, `granted`, `reason`, `state`, `user_uuid`, `user_name`, `session`; unknown values are `null`, values equal the parsed `AccessEvent`, and `timestamp` is a tz-aware ISO 8601 string from `utcTime` [unit]
- [x] #3 `user_name` comes from the event `name` for `user_authenticated` / `user_rejected` and from the dir/query cache for the other types; it is `null` when unknown, and a later directory back-fill does not fire the event again [unit]
- [x] #4 No payload contains `code`, `uid`, `authid` or `reader`, nor their values: `CodeEntered` with a code, `CardEntered` with a uid and `MobKeyEntered` with an authid are tested; no new log line contains a user name or uuid [unit]
- [x] #5 Rejected access events (params not a dict, no `valid`, unknown `state`) fire no bus event and the next event is still processed; `MotionDetected`, `SwitchStateChanged`, `InputChanged`, `OutputChanged`, `RegistrationStateChanged`, `ConfigurationChanged`, `CapabilitiesChanged`, `DeviceState`, `DirectoryChanged` and a `KeyPressed` that does not ring fire none [unit]
- [x] #6 Each counted ring fires one `type: ring` event whose extra keys equal the doorbell entity ring attributes for the same ring (shared helper, compared in a test); `CallStateChanged` + `CallSessionStateChanged` of one press fire one; a call into the intercom and a `called_id`-filtered ring fire none; `ring_on_keypress` with `%1` fires one; the bus ring fires also when the doorbell entity is disabled [unit]
- [x] #7 `device_id` is the id of the device registry entry with identifier `(2n_intercom, entry_id)`, `null` while that device is not registered yet and resolved on a later event; `config_entry_id` is the entry id [unit]
- [x] #8 Diagnostics have an `event_bus` section: `event` = `2n_intercom_event`, `types` = the types this entry can fire, derived from the subscribed log events, and `fired` = a count per type since setup; it contains no user name, uuid or other user data [unit]
- [x] #9 A new E2E test in `e2e/tests/test_50_access_control.py` checks HA diagnostics `event_bus.types` ⇄ device `/api/log/caps` (`ring` when `CallStateChanged` or `CallSessionStateChanged` is in caps, plus the mapped access types in caps), with its own copy of the mapping; it is read-only and the rest of the E2E suite stays green [e2e]
- [x] #10 `README.md` has the subsection "Event bus: `2n_intercom_event`" under Automation Examples with the type table, the payload table, name sources, what is never included, the recorder note and two YAML examples (person arrives via `user_authenticated`; wrong PIN via `code_entered` with `granted: false`); `docs/ARCHITECTURE.md` and `docs/API_REFERENCE.md` mention the bus event; no CHANGELOG or version change (checked in the PR diff) [unit]
- [x] #11 Unit suite, `validate.py` and `py_compile` pass; existing ring, keypress, access-parsing, doorbell entity and subscription tests pass unchanged [unit]
- [x] #12 After the merge, the staging HA system log shows no error from `2n_intercom` after a restart, and diagnostics show `event_bus` with types that match the device and integer counts [tester]
- [x] #13 Jan listens to `2n_intercom_event` in Developer tools → Events: one call-button press gives one `ring` event with the device_id of the intercom device, a call from My2N into the intercom gives none, a valid credential the intercom supports gives `granted: true` and the user name on `user_authenticated`, and a wrong PIN gives `code_entered` with `granted: false` and no code (the valid credential opens the door: relay) [jan]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. `const.py`: `EVENT_2N_INTERCOM = f"{DOMAIN}_event"`, `BUS_EVENT_RING = "ring"`, `ACCESS_BUS_EVENT_TYPES: dict[str, str]` mapping each name in `ACCESS_LOG_EVENTS` to its D3 type (keep `ACCESS_LOG_EVENTS` unchanged; a unit test asserts both have the same keys).
2. `coordinator.py`, device id: `self._device_id: str | None = None`. Method `_resolve_device_id()`: return the cached id; else, with `self.config_entry`, import `homeassistant.helpers.device_registry` locally (same pattern as `get_device_info`) and use `async_get(self.hass).async_get_device(identifiers={(DOMAIN, entry_id)})`; cache only a found id; return `None` otherwise. Do not wrap it in a broad `except`; add a small `device_registry` stub to `tests/_stubs.py` instead.
3. `coordinator.py`, firing: `self._bus_events_fired: dict[str, int] = {}`. Method `_fire_bus_event(event_type: str, timestamp: datetime, data: dict[str, Any])` builds `{"device_id": ..., "config_entry_id": entry_id or None, "type": event_type, "timestamp": timestamp.isoformat(), **data}`, calls `self.hass.bus.async_fire(EVENT_2N_INTERCOM, payload)` and increments the counter. At most one debug line with the type only (no user data).
4. `coordinator.py`, access: at the end of `_process_access_event`, after `self._last_access_event = AccessEvent(...)`, fire `ACCESS_BUS_EVENT_TYPES[event_name]` with `as_dict()` minus `event_type` and `timestamp` (the timestamp goes in as the argument). Return values and `_last_access_event` stay as they are. `_async_refresh_directory_names` back-fill must not fire anything.
5. `coordinator.py`, ring: new public method `ring_event_attributes() -> dict[str, Any]` that returns what `event.py` builds today (`called_peer`, `button` (TASK-77, from `last_ring_button`), `caller_name`, `caller_number`, each only when known). Call branch of `_process_log_event`: remember `new_ring = not self._ring_detected` before the count, and fire `BUS_EVENT_RING` with `self._last_ring_time` and `ring_event_attributes()` after `self._last_ring_time` is set, only when `new_ring`. `_process_key_pressed_event`: fire after `self._last_ring_time` is set. No other change to ring detection.
6. `coordinator.py`, properties: `bus_event_types` (sorted list: `ring` when `CallStateChanged`, `CallSessionStateChanged` or `KeyPressed` is in `_subscribed_log_events`, plus the mapped types of the subscribed access events) and `bus_events_fired` (copy of the counter).
7. `event.py`: `_handle_coordinator_update` uses `coordinator.ring_event_attributes()`; behaviour unchanged.
8. `diagnostics.py`: section `event_bus` = `{"event": EVENT_2N_INTERCOM, "types": coordinator.bus_event_types, "fired": coordinator.bus_events_fired}`.
9. Unit tests: `tests/test_coordinator_access.py` (one bus event per accepted access event and type, batch order, fixed key set, `null`s, timestamp from `utcTime`, name sources incl. no re-fire on back-fill, secrets absent, rejected/non-user-facing events fire nothing, device_id cached / `None` before registration); `tests/test_coordinator.py` and `tests/test_coordinator_keypress.py` (one bus ring per press, none for incoming calls or `called_id`-filtered rings, keypress ring, ring payload == entity ring attributes for the same ring, using a press with `info="2"` so `button` is compared too); `tests/test_event.py` (entity attributes unchanged via the helper); `tests/test_diagnostics.py` (`event_bus` section, no user data). Add `bus.async_fire` recording to the `_Hass` test helpers.
10. E2E: new test in `e2e/tests/test_50_access_control.py`: skip when diagnostics have no `event_bus`; expected types from `twon.log_caps()` with a local copy of the mapping (`ring` when `CallStateChanged` or `CallSessionStateChanged` is in caps; `KeyPressed` is off by default) == diagnostics `event_bus.types`; `fired` values are ints. Read-only, no relay, no call.
11. Docs: `README.md` new subsection under "Automation Examples": "Event bus: `2n_intercom_event`" with the D3 type table, the D4 payload table, name sources (D8), what is never included (D5), that HA's recorder stores the events incl. user names, and two YAML examples (`platform: event`, `event_type: 2n_intercom_event`, `event_data: {type: user_authenticated, user_name: ...}`; `event_data: {type: code_entered, granted: false}`); one line in the "Access control" feature bullet. `docs/ARCHITECTURE.md` section "2. Události": the bus event step. `docs/API_REFERENCE.md` event -> action table: the bus type per access event and for the ring.

Must not change: ring detection rules and counting (TASK-31, the TASK-77 button logic, `called_id`, one ring per press, `KEYPRESS_RING_HOLD`), the snapshot, the TASK-4 parsing and `AccessEvent`, the subscribed event list, the doorbell entity behaviour, `entry.data`/`entry.options`, translations (no new strings needed). One bad event must never break the subscription.

Headless execution: implement the approved steps above on the current task branch, run the Python 3.12 unit/validate/compile gates, record evidence in implementation notes, and commit locally without pushing. Leave criteria unchecked and status In Progress; E2E, independent review and manual criteria belong to the orchestrator/tester/Jan.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 (Jan): in scope of v1.6.0 (access and security events in automations are the main feature of the version). Not ready yet: needs analysis (payload schema and event types checked against log events from the E2E intercom and the 2N Logged Events manual), implementation plan and verifier tags on every criterion before it is assigned to @copilot. Order: TASK-6, then TASK-5 and TASK-7.

2026-11-01 (Claude): analysis done (code on main fbbcd0b, 2N manual 5.10.1 api log caps). Payload schema and type names are decisions D1-D9 in the description; verifier tags on every criterion. Ready for @copilot. TASK-77 is on main: the ring attributes incl. `button` move into the coordinator helper `ring_event_attributes()`, used by both the doorbell entity and the bus ring event (AC #6).

Implemented TASK-6 D1-D9: constants for all ten access types plus ring; immediate per-parsed-access firing in pull order; lazy device_id resolution with only successful lookup cached; fixed access schema from AccessEvent; shared ring_event_attributes() for bus/entity; subscription-derived event_bus types and per-fired-type counts. Ring rules, snapshots, access parsing, directory back-fill behaviour and subscription selection remain unchanged. No new event payload logging was added.

Added 14 unit tests across the existing access, coordinator, keypress, event and diagnostics modules, plus recording bus and per-Hass device registry stubs. Existing test assertions were not weakened or removed. Added independent read-only E2E test_event_bus_types_match_device_log_caps in e2e/tests/test_50_access_control.py; it checks the local mapping against device log/caps and integer counts after subscription, with KeyPressed default-off. No E2E/network/physical action was run on the VM.

Updated README Event bus automation subsection (type/payload tables, name sources, credential exclusion, recorder privacy and two YAML examples), architecture event flow and API event/action mapping. No manifest, CHANGELOG, translations or protected paths changed.

Local evidence: Python 3.12.15; python3 -m unittest discover -s tests -t tests passed all 825 tests; python3 validate.py passed; python3 -m py_compile custom_components/2n_intercom/*.py passed; the new E2E test file also compiles; git diff --check passed.

Evidence map for the independent reviewer (criteria remain unchecked):
AC #1: AccessBusEventTests.test_all_access_types_fire_once_with_exact_parsed_payload and test_one_pull_batch_fires_every_event_in_device_order.
AC #2: AccessBusEventTests.test_all_access_types_fire_once_with_exact_parsed_payload and test_unknown_access_fields_are_present_as_null.
AC #3: AccessBusEventTests.test_names_use_event_then_directory_without_backfill_refiring, with existing DirectoryNameResolutionTests unchanged.
AC #4: AccessBusEventTests.test_credentials_and_raw_parameters_never_reach_bus_or_logs; no new payload/user logging in the production diff.
AC #5: AccessBusEventTests.test_rejected_events_do_not_fire_or_break_next_event_in_batch and test_non_user_facing_events_never_fire.
AC #6: RingBusEventTests (two presses with doorbell disabled, incoming/filter exclusion), KeyPressedRingTests.test_bus_keypress_ring_once_in_either_order_with_call_events, DoorbellEventTests.test_bus_and_entity_share_ring_attributes_including_button (info=2, caller metadata, shared helper), plus unchanged ring/keypad tests.
AC #7: AccessBusEventTests.test_device_id_retried_until_found_then_cached (correct identifier pair, another-entry exclusion, early null and later cache).
AC #8: AccessBusEventTests.test_bus_types_follow_subscription_and_counts_are_defensive_copies and DiagnosticsTests.test_event_bus_diagnostics_use_subscription_and_integer_counts_only.
AC #9: New read-only E2E test added; execution and whole E2E result pending e2e-pi.
AC #10: README, docs/ARCHITECTURE.md and docs/API_REFERENCE.md diff; no CHANGELOG/manifest change.
AC #11: Full 825-test suite and all required local gates passed as above.
AC #12: Pending tester after merge; not attempted on the VM.
AC #13: Pending Jan physical/call/credential/relay verification; not attempted on the VM.

Task intentionally remains In Progress with all acceptance criteria unchecked for orchestrator review/finalization.

2026-11-21: Jan confirmed in the conversation that he checked the whole v1.6.0 on staging and the real intercom; the outstanding manual criteria are closed on that statement.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented by the headless coder. Checks green on 317fc5337 after 0 fix round(s): e2e-pi=pass, validate=pass, validate=pass. PR: https://github.com/mastalir1980/ha-2N-intercom/pull/121. To Test takes effect when the PR is merged.
AC #1: AccessBusEventTests.test_all_access_types_fire_once_with_exact_parsed_payload loops over all 10 events (asserts ACCESS_BUS_EVENT_TYPES keys == ACCESS_LOG_EVENTS, exactly one bus event with the D3 type each); test_one_pull_batch_fires_every_event_in_device_order runs CardEntered/UserAuthenticated/AccessTaken through _async_run_log_subscription and asserts order card_entered, user_authenticated, access_taken. Full suite (825 tests) passes locally. (proven)
AC #2: test_all_access_types_fire_once_with_exact_parsed_payload asserts set(payload) == the 13 required keys, payload equals AccessEvent.as_dict() minus event_type plus device_id/config_entry_id/type, and timestamp is tz-aware UTC parsed from utcTime 1548078453; test_unknown_access_fields_are_present_as_null asserts all other keys are None for a bare AccessTaken. (proven)
AC #3: test_names_use_event_then_directory_without_backfill_refiring: CardEntered with directory not yet loaded gives user_name None, after the directory drain the stored event name is back-filled but len(bus.events) stays 1 and the fired payload is unchanged; the other seven types take the cache name, UserAuthenticated/UserRejected take the event name, unknown uuid gives None. (proven)
AC #4: test_credentials_and_raw_parameters_never_reach_bus_or_logs sends CodeEntered, CardEntered and MobKeyEntered with code/uid/authid/reader/extra params and asserts neither keys nor values appear in any payload, and that no DEBUG log line contains the secrets, the uuid or the cached user name. _fire_bus_event adds only a payload built from AccessEvent, and the diff adds no log lines. (proven)
AC #5: test_rejected_events_do_not_fire_or_break_next_event_in_batch (non-dict params, missing valid, unknown state for AccessBlocked/AccessLimited) fires nothing and the following FingerEntered still fires in the same pull batch; test_non_user_facing_events_never_fire covers MotionDetected, SwitchStateChanged, InputChanged, OutputChanged, RegistrationStateChanged, ConfigurationChanged, CapabilitiesChanged, DeviceState, DirectoryChanged and a non-ringing KeyPressed '#', asserting no bus events. (proven)
AC #6: RingBusEventTests: two presses with enable_doorbell False each fire exactly one type=ring event (CallSessionStateChanged + CallStateChanged of one press give one) with button/called_peer; incoming-direction and called_id-filtered rings fire none. KeyPressedRingTests.test_bus_keypress_ring_once_in_either_order_with_call_events covers %1 with call events in both orders (one ring). DoorbellEventTests.test_bus_and_entity_share_ring_attributes_including_button uses info='2' and asserts the entity trigger args equal the bus extras and that the shared helper is called. Code: new_ring guard in the call branch, fire after _last_ring_time in both paths. (proven)
AC #7: test_device_id_retried_until_found_then_cached: device_id None while unregistered (another entry's device present), resolves to 'device-1' on the next event via async_get_device(identifiers={('2n_intercom','entry-1')}), stays cached after the registry is cleared (lookup called twice); config_entry_id equals the entry id in all payloads. (proven)
AC #8: DiagnosticsTests.test_event_bus_diagnostics_use_subscription_and_integer_counts_only uses a real coordinator: event=2n_intercom_event, types derived from _subscribed_log_events (empty before subscription, ['card_entered','ring'] after), fired={'card_entered':2,'ring':1} with int values, and no uuid, user name, card uid or user_* keys in the section; test_bus_types_follow_subscription_and_counts_are_defensive_copies covers ring from each of the three sources and copies. (proven)
AC #9: e2e/tests/test_50_access_control.py::test_event_bus_types_match_device_log_caps adds a local ACCESS_BUS_TYPES copy, derives expected from twon.log_caps() (ring when CallStateChanged or CallSessionStateChanged in caps), compares with diagnostics event_bus.types, checks fired values are ints, skips when event_bus is absent, and is read-only (no relay/call). Orchestrator reports e2e-pi green on this head. (proven)
AC #10: Diff: README.md has the 'Event bus: `2n_intercom_event`' subsection under Automation Examples with the type table, payload table, name sources, never-included list, recorder note and two YAML examples (user_authenticated with user_name; code_entered with granted: false) plus the feature bullet; docs/ARCHITECTURE.md and docs/API_REFERENCE.md are updated; no CHANGELOG.md or manifest.json change in the diff stat. (proven)
AC #11: Ran python3 -m unittest discover -s tests -t tests on Python 3.12.15: 825 tests OK; validate.py runs clean; orchestrator confirmed py_compile. Removed test lines are only the inline device_registry stub (replaced by install_device_registry_stub with the same attributes) and import/helper-argument changes; no assertions were removed or loosened. (proven)
AC #12: [tester] After merge, check the staging HA system log for 2n_intercom errors after a restart and that diagnostics event_bus.types match the device with integer counts. (manual)
AC #13: [jan] Physical verification in Developer tools -&gt; Events: one call-button press gives one ring with the intercom device_id, a My2N call into the intercom gives none, a valid credential gives granted true and the user name on user_authenticated, a wrong PIN gives code_entered with granted false and no code. (manual)

AC #12: confirmed by Jan on 2026-11-21 (manual check of the whole v1.6.0 before the release). (manual, confirmed)
AC #13: confirmed by Jan on 2026-11-21 (manual check of the whole v1.6.0 before the release). (manual, confirmed)
<!-- SECTION:FINAL_SUMMARY:END -->
