---
id: TASK-26
title: >-
  Expose all input ports from /api/io/caps as binary sensors (incl. extension
  modules and tamper port)
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-13 19:01'
updated_date: '2026-10-15 12:41'
labels:
  - io
  - ha-platform
  - github-issue
milestone: m-0
dependencies:
  - TASK-27
references:
  - custom_components/2n_intercom/binary_sensor.py
  - custom_components/2n_intercom/coordinator.py
  - custom_components/2n_intercom/entity.py
  - custom_components/2n_intercom/strings.json
  - custom_components/2n_intercom/icons.json
  - tests/test_binary_sensor.py
  - e2e/tests/test_10_entities.py
  - e2e/e2elib/twon.py
  - docs/API_REFERENCE.md
  - README.md
  - TASK-7
  - 'https://github.com/mastalir1980/ha-2N-intercom/issues/13'
priority: high
type: feature
ordinal: 34000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GitHub issue #13 (https://github.com/mastalir1980/ha-2N-intercom/issues/13), first half. Users with I/O extension modules see all ports in diagnostics, but only `input1` gets an HA entity. The reporter (IP Verso, HW 570v5, fw 2.50.2.76.6) has module inputs wired to the door contact ("door closed") and the lock contact ("door locked") and keeps the old helios2n integration running just to see them.

Example io_caps / io_status from the issue (inputs): `input1` = 0, `modul1.input1` = 0, `modul1.input2` = 1, `modul1.tamper` = 1. Outputs are handled by TASK-27, not here.

## Current behaviour (facts from code)
- `binary_sensor.py` `async_setup_entry` creates `TwoNIntercomInput1Sensor` only when the hard-coded port `input1` exists in io_caps (type input) and io_status; unique_id `{entry_id}_input1`, translation_key `input_1`.
- `coordinator.py` already caches `io_caps` (static, fetched once at setup) and `io_status` (polled; patched by `InputChanged` log events in `_process_input_changed_event`, which only accepts a bool `state` while `/api/io/status` reports 0/1). No new API call is needed.

## Expected behaviour
- One binary_sensor per input port reported by `/api/io/caps` (type `input`) that also exists in `/api/io/status`. State is read from the device (io_status, event-driven via InputChanged, poll as safety net).
- Ports whose name ends in `.tamper` (or is exactly `tamper`) get device_class `tamper`.
- Upgrade must not break existing installs: the `input1` entity keeps its unique_id and entity_id.

## Decision on tamper (Jan, 2026-10-13)
When the device reports a tamper input port, that port IS the tamper sensor: its state comes from the API (io_status). No separate tamper entity is created from the `TamperSwitchActivated` log event. TASK-7 is updated accordingly.

Ground-truth E2E device is IP Force 2.0 fw 3.3.x without an extension module - E2E covers only its built-in inputs; do not hard-code the port list in tests.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 One binary_sensor is created for every port with type input in io_caps that also exists in io_status; malformed entries and ports missing from io_status are skipped without error
- [x] #2 The `input1` entity keeps class behaviour, unique_id `{entry_id}_input1` and translation_key `input_1` (no entity registry change on upgrade); a unit test asserts the unique_id is unchanged
- [x] #3 All other input ports use unique_id `{entry_id}_io_<port>` (port name verbatim, e.g. `{entry_id}_io_modul1.input1`) and translation_key `io_input` with the port name as translation placeholder
- [x] #4 Ports named `tamper` or ending in `.tamper` get `BinarySensorDeviceClass.TAMPER` and translation_key `io_tamper` (name "Tamper {port}"); other inputs have no device class
- [x] #5 Input entities are enabled by default (same as today for input1) and have no entity_category
- [x] #6 `_process_input_changed_event` (and `_process_output_changed_event`) accept state as bool or int 0/1; an InputChanged event for any port (not only input1) updates the matching entity on the next coordinator update; unit tests cover both state forms
- [x] #7 Unit tests in `tests/test_binary_sensor.py` use the port list from issue #13 as fixture: entity set (input1 + modul1.input1 + modul1.input2 + modul1.tamper, no outputs), unique_ids, tamper device class, state from io_status with 0/1 values; existing tests pass unmodified
- [x] #8 `strings.json`, `translations/en.json`, `translations/de.json`, `translations/cs.json` and `icons.json` updated together; `tests/test_translations.py` passes
- [x] #9 E2E read-only in `e2e/tests/test_10_entities.py`: for every input port in `/api/io/caps` (via new `twon.io_caps()`), an HA binary_sensor exists (input1 by `_input1` suffix, others by `_io_<port>`) and its state equals `/api/io/status`; replaces or extends `test_input1_matches_device`
- [x] #10 README entity list and `docs/API_REFERENCE.md` updated (inputs per port, tamper port is the tamper sensor)
- [x] #11 `python3 -m unittest discover -s tests -t tests`, `python3 validate.py` and `bash e2e/e2e.sh wip` (or PR check `e2e-pi`) are green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Work on the already checked-out task-26-expose-all-input-ports-from-api-io-caps branch; TASK-27 is Done. Reuse its is_io_port_on helper and bool/0/1 event handling without changing coordinator behavior.
2. Discover valid input ports present in both cached io_caps and io_status; preserve TwoNIntercomInput1Sensor and its identity, and add generic per-port input sensors with tamper classification and translated port names. Reuse or extract existing output-port discovery logic if applicable.
3. Update strings, all three translations, and icons together. Add issue #13 fixtures and unit coverage for discovery, identities, defaults, states, tamper ports, and InputChanged updates; retain existing tests.
4. Reuse the independent E2E io_caps client added by TASK-27 and generalize input-state comparison to all discovered input ports, read-only. Update README and API reference; no version or changelog changes.
5. Run targeted unit coverage, then the requested full unit suite, validate.py, and py_compile locally. Do not contact HA or the intercom; leave e2e-pi to the orchestrator. Record results and implementation notes, leave criteria unchecked and status In Progress, and commit locally with a TASK-26 message.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-15 (Claude): added to v1.5.0 together with TASK-27 (both halves of issue #13).

Implemented per-port input discovery using io_ports_of_type, extracted from TASK-27 output discovery so both platforms share the same validation and de-duplication. Reused is_io_port_on and the bool/0/1 InputChanged/OutputChanged normalization already delivered by TASK-27; no coordinator or API changes were needed. input1 retains its original class, unique_id, and input_1 translation key. Other inputs use verbatim port unique IDs and placeholders; exact tamper and .tamper suffix ports get the tamper device class. Inputs retain the normal enabled-by-default, uncategorized HA defaults.
Updated strings, EN/DE/CS translations, icons, README and API reference. Added issue #13 discovery/state/identity/default/tamper/malformed-data coverage and InputChanged coverage for every fixture input with bool and integer states; existing test methods remain unchanged. Generalized the read-only E2E input assertion and reused twon.io_caps() already supplied by TASK-27. Restricted the output E2E registry helper to switch entities because new input IDs share the _io_ prefix.
Local validation on Python 3.12.15: targeted binary_sensor/coordinator/switch/translations suite passed (215 tests); full python3 -m unittest discover -s tests -t tests passed (587 tests); python3 validate.py passed; python3 -m py_compile custom_components/2n_intercom/*.py and the changed E2E test passed; final binary sensor rerun passed (39 tests). The full suite emitted RuntimeWarnings from existing untouched API test stubs; no failures. Offline E2E assertions passed with the mixed issue #13 input/output fixture and correctly rejected missing, wrong-domain, and wrong-state inputs, without loading E2E configuration or contacting devices.
No real E2E commands, Home Assistant access, intercom access, hardware switching, protected-path edits, version bump, or CHANGELOG changes. e2e-pi remains pending for the orchestrator after push. Task stays In Progress with all acceptance criteria unchecked as required in headless mode.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented by the headless coder. Checks green on 39cf735ce after 0 fix round(s): e2e-pi=pass, validate=pass, validate=pass, validate=pass, validate=pass. PR: https://github.com/mastalir1980/ha-2N-intercom/pull/37. Done takes effect when the PR is merged.
<!-- SECTION:FINAL_SUMMARY:END -->
