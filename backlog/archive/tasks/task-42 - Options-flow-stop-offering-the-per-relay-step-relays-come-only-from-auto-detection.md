---
id: TASK-42
title: >-
  Options flow: stop offering the per-relay step; relays come only from
  auto-detection
status: To Do
assignee: []
created_date: '2026-10-15 16:28'
updated_date: '2026-10-16 15:06'
labels:
  - config-flow
  - ux
dependencies:
  - TASK-41
references:
  - custom_components/2n_intercom/config_flow.py
  - custom_components/2n_intercom/switch.py
  - custom_components/2n_intercom/cover.py
  - custom_components/2n_intercom/strings.json
  - tests/test_config_flow.py
  - e2e/tests/test_40_options_flow.py
priority: low
type: enhancement
ordinal: 49000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: Jan activated the relay/switch function on the intercom and the relays appeared automatically under the device in HA (entities created from /api/switch/caps). He does not want them in the integration configuration. The per-relay options step (async_step_relay) also shows a 'Relay Number' field with a single choice, which is redundant. Current behaviour: the options flow shows one relay step per detected relay with Relay Number (fixed choice), Relay Name, Device Type door/gate and Pulse Duration; values are saved in entry.options under relays. Expected behaviour: the options flow shows no relay step and no Relay Number field; relays are created automatically from /api/switch/caps with default name 'Relay N', door type and pulse from the device switchOnDuration. Existing installs keep their already-saved relay overrides in entry.options (name, door/gate type, pulse) and they stay applied, so nothing is lost on upgrade. Trade-off to record: a new install can no longer choose gate (cover) for a relay in the options flow; a gate relay then stays a switch with the default pulse until the user changes it in HA.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The options flow shows no relay step and no Relay Number field for any number of detected relays
- [ ] #2 A new install creates one entity per detected relay with name 'Relay N', door type and pulse from switchOnDuration, without any options step
- [ ] #3 Relay overrides already saved in entry.options (name, door/gate type, pulse) are still applied on upgrade and after restart; a unit test covers this
- [ ] #4 Relay-related strings (relay step title, description, relay_number, relay fields) are removed from strings.json and translations en/de/cs; validate.py green
- [ ] #5 The last_step logic in async_step_device no longer depends on detected relays for a relay step; the device step is last when the camera step is not shown
- [ ] #6 Unit suite green on Python 3.12+; e2e/tests/test_40_options_flow.py updated to the new step list and bash e2e/e2e.sh wip green
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Not planned (Jan, 2026-10-16): the current relay handling in the options flow stays as it is. Removed from v1.5.0 and from the dependencies of TASK-37 and TASK-43 (TASK-43 now depends on TASK-41 to keep the order).
<!-- SECTION:NOTES:END -->
