---
id: TASK-55
title: >-
  Remove the doorbell binary_sensor; the doorbell event entity is the only
  doorbell entity
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-18 10:29'
labels:
  - doorbell
  - breaking-change
  - ha-platform
milestone: m-0
dependencies:
  - TASK-53
references:
  - custom_components/2n_intercom/binary_sensor.py
  - custom_components/2n_intercom/event.py
  - blueprints/doorbell_notification_answer_hangup.yaml
  - HOMEKIT_INTEGRATION.md
  - tests/test_binary_sensor.py
  - tests/test_event.py
priority: high
type: enhancement
ordinal: 62000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: since TASK-53 every intercom gets two entities named "Doorbell" (`binary_sensor.<intercom>_doorbell` and `event.<intercom>_doorbell`), which looks like a duplicate in the entity list. The event entity is the one HomeKit auto-links to the camera. Decision by Jan (2026-10-18): keep only the event entity and remove the binary_sensor in v1.5.0 as a breaking change (no deprecation period).

Current behaviour: `binary_sensor.py` creates `TwoNIntercomDoorbell` (unique_id `<entry_id>_doorbell`) when `enable_doorbell` is on; `event.py` creates the doorbell event (unique_id `<entry_id>_doorbell_event`). The blueprint `blueprints/doorbell_notification_answer_hangup.yaml` triggers on the binary_sensor and derives the call_state sensor and camera entity ids by string replacement of `binary_sensor`/`doorbell`. HOMEKIT_INTEGRATION.md, README.md, INSTALLATION.md, docs/ARCHITECTURE.md (+ `_gen_excalidraw.py`) mention the binary_sensor.

Expected behaviour: no doorbell binary_sensor is created; an existing registry entry with unique_id `<entry_id>_doorbell` in the binary_sensor domain is removed on setup so users do not keep an orphan "unavailable" entity; ring detection, the ring snapshot image, the event entity, `last_ring` and Called ID filtering work unchanged.

Approach / pointers: drop the class and its setup branch in `binary_sensor.py`, remove its translation/icon keys, registry cleanup in `async_setup_entry` (pattern: `switch.py` `_remove_stale_entities`), rewrite the blueprint to trigger on the event entity (selector domain `event`, integration `2n_intercom`, device_class doorbell) and resolve call_state/camera via the device of the trigger entity instead of string replacement. Must not change: coordinator ring logic, event entity unique_id and attributes. Depends on TASK-53 being verified on the device first.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 With `enable_doorbell` on, setup creates no binary_sensor with unique_id `<entry_id>_doorbell`; the doorbell event entity is still created; unit test
- [ ] #2 An existing registry entry `binary_sensor` / `<entry_id>_doorbell` is removed on setup; unit test
- [ ] #3 The blueprint triggers on the doorbell event entity and finds the call_state sensor and camera of the same device without string replacement of entity ids; blueprint YAML is valid
- [ ] #4 strings.json, translations en/de/cs and icons.json no longer contain the binary_sensor doorbell keys; test_translations and validate.py green
- [ ] #5 README.md, INSTALLATION.md, HOMEKIT_INTEGRATION.md and docs/ARCHITECTURE.md (+ regenerated diagrams) describe only the event entity; the release task can list this as a breaking change (note in the task final summary)
- [ ] #6 E2E (read-only): staging HA has `event.<intercom>_doorbell` and no doorbell binary_sensor for the entry ("HA says one doorbell entity"); `bash e2e/e2e.sh wip` or PR check e2e-pi green
<!-- AC:END -->
