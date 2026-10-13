---
id: TASK-27
title: >-
  Expose IO output ports (except led_secured) as switches controlled via
  /api/io/ctrl
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-13 19:03'
updated_date: '2026-10-13 19:54'
labels:
  - io
  - ha-platform
  - github-issue
  - relay
dependencies: []
references:
  - custom_components/2n_intercom/switch.py
  - custom_components/2n_intercom/api.py
  - custom_components/2n_intercom/coordinator.py
  - custom_components/2n_intercom/binary_sensor.py
  - custom_components/2n_intercom/strings.json
  - custom_components/2n_intercom/icons.json
  - tests/test_switch.py
  - tests/test_api.py
  - e2e/tests/test_10_entities.py
  - e2e/tests/test_30_relays.py
  - e2e/e2elib/twon.py
  - docs/API_REFERENCE.md
  - README.md
  - 'https://github.com/mastalir1980/ha-2N-intercom/issues/13'
priority: medium
type: feature
ordinal: 35000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GitHub issue #13 (https://github.com/mastalir1980/ha-2N-intercom/issues/13), second half. Users cannot control the physical output ports of the intercom from HA. The reporter (IP Verso, HW 570v5, fw 2.50.2.76.6, with an I/O extension module) uses `output1` to enable an RFID reader and keeps the old helios2n integration running just for that.

## Background: two layers in 2N
- **Physical ports** (`/api/io/caps`, `/api/io/status`, `/api/io/ctrl`): real terminals. Example from the issue, outputs: `led_secured`, `relay1`, `output1`, `modul1.relay1`, `modul1.relay2`; inputs: `input1`, `modul1.input1`, `modul1.input2`, `modul1.tamper`.
- **Logical switches** (`/api/switch/caps|status|ctrl`): a door-opener function that the installer maps to a physical port and gives timing (e.g. close relay1 for 5 s). Today `switch.py` / `cover.py` expose only these.

## Current behaviour (facts from code)
- `switch.py` creates entities only from `coordinator.switch_caps` (logical switches), unique_id `{entry_id}_switch_<n>`.
- `api.py` reads `/api/io/caps` and `/api/io/status` (`async_get_io_caps`, `async_get_io_status`) but has no wrapper for `/api/io/ctrl`.
- `coordinator.py` already caches `io_caps` (fetched once at setup, static) and `io_status` (polled), and patches `io_status` from `OutputChanged` log events in `_process_output_changed_event`. Note that handler only accepts a bool `state`, while `/api/io/status` reports `state` as 0/1.

## Expected behaviour
- One HA switch per output port reported by `/api/io/caps` (type `output`) that is also present in `/api/io/status`, **except `led_secured`** (status LED driven by the intercom itself; decided by Jan 2026-10-13).
- All output ports are exposed, including `relay1` and module relays, even when a logical switch drives the same relay (decision by Jan 2026-10-13, option A). Because of that the entities are **disabled by default** and the docs carry a warning.
- These are **latching** outputs, not pulses: turn_on sets the port on and it stays on until turn_off. State is read from `io_status` (event-driven via OutputChanged, poll as safety net). No optimistic state, no auto-off timer.

## Why the warning matters
Switching `relay1` directly via `/api/io/ctrl` bypasses the timing of the logical switch. If a user enables the direct `relay1` entity and turns it on, the door stays unlocked until someone turns it off. README must say so clearly.

## Known risks for the implementer
- The 2N API account needs the I/O control privilege; without it the device answers 401 / an error (see TASK-13 for the same problem with the Switch API). This must surface as a clear error, not a silent failure.
- Ground-truth E2E device is IP Force 2.0 fw 3.3.x without an extension module; it has fewer outputs than the reporter. Exact output list is unknown until the E2E run - read it from `/api/io/caps`, do not hard-code it in tests.
- Any E2E that actually switches an output changes hardware and must be marked `@pytest.mark.relay` (never runs in `e2e.sh wip` / `e2e-pi`).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `api.py` has `async_io_control(port: str, on: bool) -> bool` calling GET `/api/io/ctrl` with params `port=<port>` and `action=on|off`; returns True on `success: true`; on a device error it logs via `parse_device_error` / `log_device_error` at WARNING and returns False; timeout / transport errors handled like `async_switch_control`
- [ ] #2 Unit tests in `tests/test_api.py` cover: success, device error payload (code + description logged), timeout, and correct query params for on and off
- [ ] #3 One switch entity is created for each port with type output in io_caps that also exists in io_status; `led_secured` is never created; ports missing from io_status or malformed entries are skipped without error
- [ ] #4 Output switch entities have `_attr_entity_registry_enabled_default = False`, unique_id `{entry_id}_io_<port>` (port name verbatim, e.g. `{entry_id}_io_modul1.relay1`), translation_key `io_output` with the port name as translation placeholder
- [ ] #5 `is_on` reflects the port state in `coordinator.io_status` (accepts 1/True/"1"/"on"/"true" like `TwoNIntercomInput1Sensor._is_port_on`); there is no optimistic state and no auto-off timer
- [ ] #6 turn_on / turn_off call the API, and on success request a coordinator refresh so the state is confirmed by io_status; on failure they raise a translated `HomeAssistantError` (new key in `exceptions` of strings.json + all translations) and the state stays unchanged
- [ ] #7 `_process_output_changed_event` (and `_process_input_changed_event`) accept state as bool or 0/1 int, normalised to the same representation io_status uses; unit test covers both forms
- [ ] #8 Existing logical switch entities (`{entry_id}_switch_<n>`), their unique_ids and behaviour are unchanged; existing tests in `tests/test_switch.py` pass unmodified
- [ ] #9 Unit tests in `tests/test_switch.py`: entity set built from an io_caps fixture with the ports from issue #13 (led_secured excluded, module ports included), disabled by default, state from io_status, turn_on/off call `async_io_control` with the right port, failure raises HomeAssistantError, OutputChanged event updates state
- [ ] #10 `strings.json`, `translations/en.json`, `translations/de.json`, `translations/cs.json` and `icons.json` updated together; `tests/test_translations.py` passes
- [ ] #11 E2E read-only (runs in wip / e2e-pi): new test in `e2e/tests/test_10_entities.py` asserts that the set of `{entry_id}_io_<port>` switch unique_ids in the HA entity registry equals the output ports from `/api/io/caps` minus `led_secured`, that each is disabled_by integration by default, and that any enabled one has an HA state equal to `/api/io/status`
- [ ] #12 E2E physical (marked `@pytest.mark.relay`, skipped by default): new test in `e2e/tests/test_30_relays.py` driven by a new env var `E2E_IO_OUTPUTS` (comma-separated port names, empty = skip, added to `e2e/.env.example` with an empty value) turns the output on via HA, waits for `/api/io/status` to report it on and HA to show on, then turns it off and checks both again
- [ ] #13 README: output switches listed in the entity section with a clear warning that direct control of a relay bypasses the logical switch timing (door can stay unlocked) and that the API account needs the I/O control privilege; `/api/io/ctrl` added to "2N API Endpoints Used"; `docs/API_REFERENCE.md` table updated
- [ ] #14 `python3 -m unittest discover -s tests -t tests`, `python3 validate.py` and `bash e2e/e2e.sh wip` (or PR check `e2e-pi`) are green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Keep the checked-out task-27-expose-io-output-ports-except-led-secure branch. Add GET /api/io/ctrl through the existing authenticated request path and a coordinator control method with confirmed refresh.
2. Normalize bool and integer 0/1 input/output log events; reuse the input-state helper for disabled-by-default physical output switches, excluding led_secured and malformed or absent ports. Preserve logical switches and covers.
3. Update entity names, translated control errors, and icons together. Extend isolated API, coordinator, switch, and translation tests without altering existing logical-switch test cases.
4. Add independent io_caps E2E client support, read-only registry/state coverage, and explicitly opted-in relay-marked physical output coverage via empty-default E2E_IO_OUTPUTS. Do not contact HA or the intercom from this VM.
5. Document latching behavior, timing bypass hazards, I/O control privileges, and /api/io/ctrl. Run the full Python 3.12 unit suite, validate.py, and py_compile; leave acceptance criteria unchecked and task In Progress pending e2e-pi. Record implementation notes and commit locally with TASK-27 prefix; do not push.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented GET /api/io/ctrl through _async_request with the existing switch-control error-handling pattern, plus coordinator refresh only after successful writes. Physical output switches are discovered once from caps/status, exclude led_secured, retain verbatim port unique IDs, are disabled by default, and expose only device-confirmed latching state. Logical switch entity code and unique IDs are unchanged.
InputChanged and OutputChanged now accept bool or integer 0/1, reject other values, and store integer 0/1 like io/status. Extracted is_io_port_on into entity.py and reused it from the existing input1 sensor and new output switches. Added translated IO privilege guidance and icons in all three languages, plus the README timing-bypass/door-unlocked warning and API endpoint reference.
Local Python 3.12 gates passed: 580 full-suite unit tests; python3 validate.py; python3 -m py_compile custom_components/2n_intercom/*.py. Existing API test coroutine warnings remain outside this task scope. No E2E or hardware access was attempted; acceptance criteria remain unchecked and status remains In Progress pending the orchestrator e2e-pi gate.

E2E coverage is now added without running it: the independent TwoN client reads /api/io/caps; the read-only test compares the exact registry unique-ID set against output capabilities minus led_secured, checks integration-disabled defaults and enabled output state, and explicitly reports missing status ports. The physical roundtrip is relay-marked and additionally gated by empty-default E2E_IO_OUTPUTS; it validates each allowlisted port, requires the output switch to be manually enabled and initially off, and always attempts turn_off with HA/device confirmation in finally. Existing logical relay test bodies and all protected harness files are unchanged. The three edited E2E Python files compile successfully.
Implementation is ready for the orchestrator to push and run e2e-pi. No push, E2E execution, relay actuation, version bump, or CHANGELOG change was performed. Task status and unchecked acceptance criteria are intentionally retained until that gate is green.
<!-- SECTION:NOTES:END -->
