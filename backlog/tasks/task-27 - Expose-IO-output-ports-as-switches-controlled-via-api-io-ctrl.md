---
id: TASK-27
title: >-
  Expose IO output ports (except led_secured) as switches controlled via
  /api/io/ctrl
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-13 19:03'
updated_date: '2026-10-15 12:12'
labels:
  - io
  - ha-platform
  - github-issue
  - relay
milestone: m-0
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
- [x] #1 `api.py` has `async_io_control(port: str, on: bool) -> bool` calling GET `/api/io/ctrl` with params `port=<port>` and `action=on|off`; returns True on `success: true`; on a device error it logs via `parse_device_error` / `log_device_error` at WARNING and returns False; timeout / transport errors handled like `async_switch_control`
- [x] #2 Unit tests in `tests/test_api.py` cover: success, device error payload (code + description logged), timeout, and correct query params for on and off
- [x] #3 One switch entity is created for each port with type output in io_caps that also exists in io_status; `led_secured` is never created; ports missing from io_status or malformed entries are skipped without error
- [x] #4 Output switch entities have `_attr_entity_registry_enabled_default = False`, unique_id `{entry_id}_io_<port>` (port name verbatim, e.g. `{entry_id}_io_modul1.relay1`), translation_key `io_output` with the port name as translation placeholder
- [x] #5 `is_on` reflects the port state in `coordinator.io_status` (accepts 1/True/"1"/"on"/"true" like `TwoNIntercomInput1Sensor._is_port_on`); there is no optimistic state and no auto-off timer
- [x] #6 turn_on / turn_off call the API, and on success request a coordinator refresh so the state is confirmed by io_status; on failure they raise a translated `HomeAssistantError` (new key in `exceptions` of strings.json + all translations) and the state stays unchanged
- [x] #7 `_process_output_changed_event` (and `_process_input_changed_event`) accept state as bool or 0/1 int, normalised to the same representation io_status uses; unit test covers both forms
- [x] #8 Existing logical switch entities (`{entry_id}_switch_<n>`), their unique_ids and behaviour are unchanged; existing tests in `tests/test_switch.py` pass unmodified
- [x] #9 Unit tests in `tests/test_switch.py`: entity set built from an io_caps fixture with the ports from issue #13 (led_secured excluded, module ports included), disabled by default, state from io_status, turn_on/off call `async_io_control` with the right port, failure raises HomeAssistantError, OutputChanged event updates state
- [x] #10 `strings.json`, `translations/en.json`, `translations/de.json`, `translations/cs.json` and `icons.json` updated together; `tests/test_translations.py` passes
- [x] #11 E2E read-only (runs in wip / e2e-pi): new test in `e2e/tests/test_10_entities.py` asserts that the set of `{entry_id}_io_<port>` switch unique_ids in the HA entity registry equals the output ports from `/api/io/caps` minus `led_secured`, that each is disabled_by integration by default, and that any enabled one has an HA state equal to `/api/io/status`
- [x] #12 E2E physical (marked `@pytest.mark.relay`, skipped by default): new test in `e2e/tests/test_30_relays.py` driven by a new env var `E2E_IO_OUTPUTS` (comma-separated port names, empty = skip, added to `e2e/.env.example` with an empty value) turns the output on via HA, waits for `/api/io/status` to report it on and HA to show on, then turns it off and checks both again
- [x] #13 README: output switches listed in the entity section with a clear warning that direct control of a relay bypasses the logical switch timing (door can stay unlocked) and that the API account needs the I/O control privilege; `/api/io/ctrl` added to "2N API Endpoints Used"; `docs/API_REFERENCE.md` table updated
- [x] #14 `python3 -m unittest discover -s tests -t tests`, `python3 validate.py` and `bash e2e/e2e.sh wip` (or PR check `e2e-pi`) are green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Branch `task-27-io-output-switches`.
2. api.py: add `IO_CTRL_PATH = "/api/io/ctrl"` next to `IO_STATUS_PATH`; add `async_io_control(self, port: str, on: bool) -> bool` modelled 1:1 on `async_switch_control` (GET, params `{"port": port, "action": "on" if on else "off"}`, `async_timeout.timeout(API_TIMEOUT)`, `response.raise_for_status()`, success check, `parse_device_error` + `log_device_error(logging.WARNING, ...)`, same except blocks). Call control is GET on 2N - do not use POST. Keep the dual Basic/Digest auth path untouched: always go through `self._async_request`.
3. coordinator.py: add `async_set_io_output(port: str, on: bool) -> bool` that calls `self.api.async_io_control` and on success calls `await self.async_request_refresh()`. Fix `_process_output_changed_event` and `_process_input_changed_event` to accept `bool` or int 0/1 (`isinstance(state, (bool, int))`), storing the value in the same form io_status uses. Do not change polling interval, ring detection or log subscription logic.
4. switch.py: add `_io_output_ports(coordinator) -> list[str]` that walks `coordinator.io_caps["ports"]`, keeps entries with `type == "output"`, a string `port`, port != `led_secured` (constant `IO_EXCLUDED_OUTPUTS = {"led_secured"}` in const.py), and present in `coordinator.io_status["ports"]`. In `async_setup_entry`, after the existing `_async_check_relays()` population, add `TwoNIntercomIoOutputSwitch` entities for those ports once (io_caps is static, no dynamic add/remove needed). Do not touch `_get_eligible_caps`, `_switch_unique_id` or `TwoNIntercomSwitch`.
5. New class `TwoNIntercomIoOutputSwitch(TwoNIntercomEntity, SwitchEntity)` in switch.py: `_attr_translation_key = "io_output"`, `_attr_translation_placeholders = {"port": port}`, `_attr_entity_registry_enabled_default = False`, unique_id `f"{entry_id}_io_{port}"`; `is_on` reads io_status (reuse the truthy set from `TwoNIntercomInput1Sensor._is_port_on`; consider moving that helper to entity.py or a small util so TASK-26 can reuse it); `async_turn_on/off` call `coordinator.async_set_io_output` and raise `HomeAssistantError(translation_domain=DOMAIN, translation_key="io_control_failed", translation_placeholders={"port": port})` on False. `PARALLEL_UPDATES = 1` already applies.
6. strings.json + translations/en,de,cs: `entity.switch.io_output.name = "Output {port}"` (de: "Ausgang {port}", cs: "Výstup {port}"); `exceptions.io_control_failed.message` ("Failed to switch output {port} on the intercom. Check that the API account has the I/O control privilege." + de/cs). icons.json: `entity.switch.io_output` with `default` mdi:electric-switch, state on mdi:electric-switch-closed.
7. Unit tests (style of tests/test_switch.py and tests/test_api.py, stubs from tests/_stubs.py, no HA and no network): see acceptance criteria; use the port list from issue #13 as fixture (io_caps with led_secured, relay1, output1, input1, modul1.relay1, modul1.relay2, modul1.input1, modul1.input2, modul1.tamper; io_status with 0/1 states).
8. e2e: add `io_caps()` to `e2e/e2elib/twon.py` (independent of api.py - do not import the integration). Read-only test in test_10_entities.py (registry vs io_caps outputs minus led_secured, disabled_by == "integration", enabled ones match io_status). Physical test in test_30_relays.py marked `@pytest.mark.relay`, parametrised from `E2E_IO_OUTPUTS` like `E2E_RELAY_NUMBERS`; the e2e harness must never enable this by default. Add `E2E_IO_OUTPUTS=` (empty) to e2e/.env.example.
9. Docs: README entity list + warning + endpoint table; docs/API_REFERENCE.md row for `/api/io/ctrl` (GET, `async_io_control`, params `port`, `action=on|off`). No version bump / CHANGELOG (release task does that).
10. Run unit tests, validate.py, py_compile, then `bash e2e/e2e.sh wip` (headless: PR check e2e-pi). Never run `--relays`.

Must not change: dual auth in api.py, entry.data/options split, logical switch entities and their unique_ids, cover.py, ring detection, the E2E client independence.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented GET /api/io/ctrl through _async_request with the existing switch-control error-handling pattern, plus coordinator refresh only after successful writes. Physical output switches are discovered once from caps/status, exclude led_secured, retain verbatim port unique IDs, are disabled by default, and expose only device-confirmed latching state. Logical switch entity code and unique IDs are unchanged.
InputChanged and OutputChanged now accept bool or integer 0/1, reject other values, and store integer 0/1 like io/status. Extracted is_io_port_on into entity.py and reused it from the existing input1 sensor and new output switches. Added translated IO privilege guidance and icons in all three languages, plus the README timing-bypass/door-unlocked warning and API endpoint reference.
Local Python 3.12 gates passed: 580 full-suite unit tests; python3 validate.py; python3 -m py_compile custom_components/2n_intercom/*.py. Existing API test coroutine warnings remain outside this task scope. No E2E or hardware access was attempted; acceptance criteria remain unchecked and status remains In Progress pending the orchestrator e2e-pi gate.

E2E coverage is now added without running it: the independent TwoN client reads /api/io/caps; the read-only test compares the exact registry unique-ID set against output capabilities minus led_secured, checks integration-disabled defaults and enabled output state, and explicitly reports missing status ports. The physical roundtrip is relay-marked and additionally gated by empty-default E2E_IO_OUTPUTS; it validates each allowlisted port, requires the output switch to be manually enabled and initially off, and always attempts turn_off with HA/device confirmation in finally. Existing logical relay test bodies and all protected harness files are unchanged. The three edited E2E Python files compile successfully.
Implementation is ready for the orchestrator to push and run e2e-pi. No push, E2E execution, relay actuation, version bump, or CHANGELOG change was performed. Task status and unchecked acceptance criteria are intentionally retained until that gate is green.

Recovery: the headless coder run 20261013-214615-TASK-27 stopped before push because the patch touched the protected path e2e/.env.example (the task itself asked for that line). Jan applied the unchanged patch by hand in PR #29: code in one commit, the empty E2E_IO_OUTPUTS line plus comments in e2e/.env.example in a separate commit. The coder had replaced the original implementation plan with a shortened one; the original plan is restored here. Review by Claude against all 14 acceptance criteria: no findings. Verification: PR #29 checks validate and e2e-pi green on 9c298a7 (15 passed, 0 failed, 1 skipped; relay-marked tests not run, including the new physical test_io_output_roundtrip); unit suite 580 tests OK, validate.py OK, py_compile OK.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Physical IO output ports from /api/io/caps (except led_secured) are now exposed as disabled-by-default, latching HA switches controlled via GET /api/io/ctrl (new api.async_io_control, coordinator.async_set_io_output), with state from io_status/OutputChanged and a translated error when the device rejects control. InputChanged/OutputChanged accept bool or 0/1. Logical switches unchanged. README warns that direct relay control bypasses logical switch timing and needs the I/O control privilege. Verified by unit tests (580 OK), validate.py, and the e2e-pi PR check (read-only registry vs /api/io/caps test green). The physical roundtrip test (relay-marked, gated by empty E2E_IO_OUTPUTS) was not executed.
<!-- SECTION:FINAL_SUMMARY:END -->
