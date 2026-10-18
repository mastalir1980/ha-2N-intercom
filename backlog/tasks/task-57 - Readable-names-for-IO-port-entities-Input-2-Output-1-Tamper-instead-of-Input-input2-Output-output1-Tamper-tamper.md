---
id: TASK-57
title: >-
  Readable names for IO port entities (Input 2, Output 1, Tamper instead of
  Input input2, Output output1, Tamper tamper)
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-18 10:30'
labels:
  - io
  - ux
  - translations
milestone: m-0
dependencies:
  - TASK-56
references:
  - custom_components/2n_intercom/binary_sensor.py
  - custom_components/2n_intercom/switch.py
  - custom_components/2n_intercom/strings.json
  - tests/test_binary_sensor.py
  - tests/test_switch.py
  - tests/test_translations.py
priority: low
type: bug
ordinal: 64000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: IO entities from TASK-26/TASK-27 put the raw 2N port id into the translated name, so a real install shows "Input input2", "Output output1" and "Tamper tamper" next to the older "Input 1". It reads like a duplicate and looks broken.

Current behaviour: translation names `Input {port}`, `Output {port}`, `Tamper {port}` (binary_sensor `io_input`, `io_tamper`; switch `io_output`) with `port` = raw id from `/api/io/caps` (`input2`, `output1`, `tamper`, `modul1.input1`). `input1` uses the separate legacy class `TwoNIntercomInput1Sensor` named "Input 1".

Expected behaviour: built-in ports read `Input 2`, `Output 1`, `Tamper`; extension module ports read e.g. `Module 1 input 1`, `Module 1 tamper`; the names are consistent with `Input 1` in en/de/cs. Unique_ids do not change (existing entity_ids stay).

Pointers: `binary_sensor.py` `TwoNIntercomIoInputSensor`, `switch.py` `TwoNIntercomIoOutputSwitch`, `strings.json` + `translations/{en,de,cs}.json` placeholders (pass a parsed number/module instead of the raw port id; unknown port ids fall back to the raw id). Must not change: unique_ids, which ports are exposed (TASK-56 decides that), entity behaviour.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Names: `input2` -> Input 2, `output1` -> Output 1, `tamper` -> Tamper, `modul1.input1` -> Module 1 input 1, `modul1.tamper` -> Module 1 tamper (en; de/cs equivalent); unit test over the name/placeholder mapping
- [ ] #2 A port id that does not match the known patterns keeps a name containing the raw id; unit test
- [ ] #3 Unique_ids of IO input/tamper/output entities are unchanged; existing tests green
- [ ] #4 test_translations and validate.py green; `bash e2e/e2e.sh wip` or PR check e2e-pi green
<!-- AC:END -->
