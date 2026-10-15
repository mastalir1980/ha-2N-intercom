---
id: TASK-26
title: >-
  Expose all input ports from /api/io/caps as binary sensors (incl. extension
  modules and tamper port)
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-13 19:01'
updated_date: '2026-10-15 12:23'
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
priority: medium
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
- [ ] #1 One binary_sensor is created for every port with type input in io_caps that also exists in io_status; malformed entries and ports missing from io_status are skipped without error
- [ ] #2 The `input1` entity keeps class behaviour, unique_id `{entry_id}_input1` and translation_key `input_1` (no entity registry change on upgrade); a unit test asserts the unique_id is unchanged
- [ ] #3 All other input ports use unique_id `{entry_id}_io_<port>` (port name verbatim, e.g. `{entry_id}_io_modul1.input1`) and translation_key `io_input` with the port name as translation placeholder
- [ ] #4 Ports named `tamper` or ending in `.tamper` get `BinarySensorDeviceClass.TAMPER` and translation_key `io_tamper` (name "Tamper {port}"); other inputs have no device class
- [ ] #5 Input entities are enabled by default (same as today for input1) and have no entity_category
- [ ] #6 `_process_input_changed_event` (and `_process_output_changed_event`) accept state as bool or int 0/1; an InputChanged event for any port (not only input1) updates the matching entity on the next coordinator update; unit tests cover both state forms
- [ ] #7 Unit tests in `tests/test_binary_sensor.py` use the port list from issue #13 as fixture: entity set (input1 + modul1.input1 + modul1.input2 + modul1.tamper, no outputs), unique_ids, tamper device class, state from io_status with 0/1 values; existing tests pass unmodified
- [ ] #8 `strings.json`, `translations/en.json`, `translations/de.json`, `translations/cs.json` and `icons.json` updated together; `tests/test_translations.py` passes
- [ ] #9 E2E read-only in `e2e/tests/test_10_entities.py`: for every input port in `/api/io/caps` (via new `twon.io_caps()`), an HA binary_sensor exists (input1 by `_input1` suffix, others by `_io_<port>`) and its state equals `/api/io/status`; replaces or extends `test_input1_matches_device`
- [ ] #10 README entity list and `docs/API_REFERENCE.md` updated (inputs per port, tamper port is the tamper sensor)
- [ ] #11 `python3 -m unittest discover -s tests -t tests`, `python3 validate.py` and `bash e2e/e2e.sh wip` (or PR check `e2e-pi`) are green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Branch `task-26-io-input-sensors`.
2. Shared helper: add a small function (e.g. `io_port_is_on(io_status, port) -> bool` and `io_ports_of_type(io_caps, io_status, port_type) -> list[str]`) in `entity.py` or a new `io.py`, with the truthy set `(1, True, "1", "on", "true")` taken from `TwoNIntercomInput1Sensor._is_port_on`. If TASK-27 already landed a helper, reuse it instead of adding a second one.
3. coordinator.py: in `_process_input_changed_event` and `_process_output_changed_event` accept `isinstance(state, (bool, int))`. Nothing else in the coordinator changes (no new polling, no new events, no change to ring detection or log subscription).
4. binary_sensor.py `async_setup_entry`: keep the doorbell, relay-1-active and motion logic as is. Replace the hard-coded input1 block: for each input port from the helper, create `TwoNIntercomInput1Sensor` when port == "input1", otherwise new `TwoNIntercomIoInputSensor(coordinator, entry, port)`.
5. New class `TwoNIntercomIoInputSensor(TwoNIntercomEntity, BinarySensorEntity)`: unique_id `f"{entry_id}_io_{port}"`; if `port == "tamper" or port.endswith(".tamper")` -> `_attr_device_class = BinarySensorDeviceClass.TAMPER`, `_attr_translation_key = "io_tamper"`, else `_attr_translation_key = "io_input"`; `_attr_translation_placeholders = {"port": port}`; `is_on` via the helper.
6. strings.json + translations: `entity.binary_sensor.io_input.name` = "Input {port}" (de "Eingang {port}", cs "Vstup {port}"); `io_tamper.name` = "Tamper {port}" (de "Sabotage {port}", cs "Sabotáž {port}"). icons.json: `io_input` mdi:import / state on mdi:electric-switch-closed; `io_tamper` default mdi:shield-check, on mdi:shield-alert.
7. Unit tests per acceptance criteria (style of tests/test_binary_sensor.py with FakeCoordinator; no HA, no network).
8. e2e: add `io_caps()` to `e2e/e2elib/twon.py` (returns `ports` from `/api/io/caps`; keep the client independent of api.py). Generalise `test_input1_matches_device` to all input ports. Read-only only - nothing here switches hardware.
9. Docs: README entity list, docs/API_REFERENCE.md note. No version bump / CHANGELOG.
10. Run unit tests, validate.py, py_compile, `bash e2e/e2e.sh wip` (headless: PR check e2e-pi).

Must not change: input1 unique_id/translation_key, doorbell/relay/motion sensors, dual auth in api.py, entry.data/options split, E2E client independence. Do not add any tamper entity based on log events (see decision in description).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-15 (Claude): added to v1.5.0 together with TASK-27 (both halves of issue #13).
<!-- SECTION:NOTES:END -->
