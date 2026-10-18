---
id: TASK-56
title: >-
  Relays only from enabled logical switches: hide relay IO outputs and remove
  the Relay 1 active sensor
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-18 10:29'
labels:
  - relay
  - io
  - ha-platform
milestone: m-0
dependencies:
  - TASK-55
references:
  - custom_components/2n_intercom/switch.py
  - custom_components/2n_intercom/binary_sensor.py
  - custom_components/2n_intercom/const.py
  - tests/test_switch.py
  - tests/test_binary_sensor.py
  - e2e/tests/test_10_entities.py
  - e2e/tests/test_30_relays.py
  - 'https://github.com/mastalir1980/ha-2N-intercom/issues/13'
priority: medium
type: enhancement
ordinal: 63000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: on a real install the entity list shows the same relay three times: the logical switch `Relay 1` (from `/api/switch/caps`), the physical IO output switch `Output relay1` (from `/api/io/caps`, TASK-27) and the binary_sensor `Relay 1 active`. Decision by Jan (2026-10-18): relays in HA are only the logical switches that are enabled on the intercom. Physical IO outputs that are relays (`relay1`, `relay2`, module relays such as `modul1.relay1`) are not exposed any more. Plain outputs (`output1`, `output2`, module outputs that are not relays) stay as they are (disabled by default), because GitHub issue #13 uses `output1` to power an RFID reader without any logical switch on it. This revises the TASK-27 decision "expose relay1 too (option A)".

Current behaviour: `switch.py` `_io_output_ports` exposes every IO output except `led_secured` (`IO_EXCLUDED_OUTPUTS` in `const.py`); `binary_sensor.py` creates `TwoNIntercomRelay1ActiveSensor` (unique_id `<entry_id>_relay1_active`, disabled by default) when logical switch 1 exists.

Expected behaviour: no IO output switch for ports whose name is `relayN` or `<module>.relayN`; no `Relay 1 active` binary_sensor; existing registry entries for both are removed on setup (no orphan "unavailable" entities); the logical relay switches/covers and plain output switches are unchanged.

Pointers: `switch.py` `_io_output_ports`, `const.py` `IO_EXCLUDED_OUTPUTS`, `binary_sensor.py` `_switch_exists` and `TwoNIntercomRelay1ActiveSensor`, strings/translations/icons keys `relay_1_active`, `e2e/tests/test_10_entities.py` and `e2e/tests/test_30_relays.py` (IO output relay tests), README/docs relay sections. Must not change: logical switch/cover entities and their unique_ids, `/api/io/ctrl` handling for plain outputs, IO input sensors.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 IO caps with outputs `led_secured`, `relay1`, `relay2`, `output1`, `modul1.relay1`, `modul1.output1` produce output switches only for `output1` and `modul1.output1`; unit test
- [ ] #2 No `Relay 1 active` binary_sensor is created when logical switch 1 exists; unit test
- [ ] #3 Existing registry entries `switch` / `<entry_id>_io_relayN` (incl. module relays) and `binary_sensor` / `<entry_id>_relay1_active` are removed on setup; unit test
- [ ] #4 Logical relay switches and gate covers from `/api/switch/caps` + options are unchanged (existing tests green)
- [ ] #5 strings.json, translations en/de/cs and icons.json drop `relay_1_active`; test_translations and validate.py green; README.md/docs describe relays as the logical switches enabled on the intercom and plain outputs as disabled-by-default switches
- [ ] #6 E2E (read-only, no relay switching): staging HA has a switch per enabled logical relay and no IO output switch for relay ports ("HA relays == enabled /api/switch/caps entries"); relay-switching tests in test_30_relays.py that target IO relay outputs are removed or retargeted and stay marked `relay`; `bash e2e/e2e.sh wip` or PR check e2e-pi green
<!-- AC:END -->
