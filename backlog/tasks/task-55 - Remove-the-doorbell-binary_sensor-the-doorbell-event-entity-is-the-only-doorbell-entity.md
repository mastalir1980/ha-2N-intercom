---
id: TASK-55
title: >-
  Remove the doorbell binary_sensor; the doorbell event entity is the only
  doorbell entity
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-18 10:29'
updated_date: '2026-10-18 12:17'
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Remove TwoNIntercomDoorbell from the binary_sensor platform and migrate the exact legacy domain/platform/unique-ID registry entry in integration async_setup_entry before platform forwarding, including enable_doorbell=false. Preserve other entities and coordinator/event behavior.
2. Update the notification blueprint to select doorbell events, ignore startup/restore/unavailable and attribute-only transitions, and discover the active call-state sensor and camera on the triggering device without entity-name replacement. Pin answer/hangup to its config entry and session.
3. Remove binary-sensor doorbell translation/icon keys; add migration/setup, offline blueprint YAML/Jinja and translation regression coverage plus a read-only E2E single-doorbell assertion. Declare blueprint parsing dependencies as test-only.
4. Update README, installation, HomeKit and architecture guidance, regenerate diagrams, and document the breaking migration for release notes.
5. Run required Python 3.12 local gates, record results with Pi E2E pending, and commit on the current branch without checking criteria, closing the task or pushing.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Removed the doorbell binary-sensor implementation and its translation/icon keys. The integration setup now removes only binary_sensor / 2n_intercom / <entry_id>_doorbell, including renamed or disabled registry entries and entries with enable_doorbell off. Migration is idempotent and leaves the event, other platforms, physical inputs and other intercom entries untouched. Cleanup is intentionally in __init__.async_setup_entry because the binary_sensor platform is not forwarded when the option is off.
The blueprint selects event + integration 2n_intercom + device_class doorbell, reacts only to new ring timestamps (including the first ring from unknown), and suppresses startup/restore/unavailable and attribute-only updates. It discovers the active call-state sensor and camera from the triggering device and integration, independent of localized/renamed IDs, and pins call services to that config entry/session. Missing enabled camera or active session produces an explicit automation error. Removed the old unused camera/call-state inputs.
Added exact migration/non-removal/idempotence coverage, no-binary-sensor setup assertions, retained event metadata/ring/filter regression coverage, translation-key removal assertions, and offline blueprint YAML/template tests. Jinja2/PyYAML are declared only in tests/requirements.txt and documented in README; runtime requirements remain empty. Updated the read-only E2E entity check to require exactly one doorbell event and no legacy binary-sensor registry entry.
Updated README, INSTALLATION, HOMEKIT_INTEGRATION, ARCHITECTURE and the diagram generator; regenerated both Excalidraw diagrams. No coordinator/event implementation change, version bump, CHANGELOG edit or protected-path edit.

Local gates on Python 3.12.15: all 675 unit tests passed; python3 validate.py passed; integration py_compile passed; changed E2E test compiles; git diff --check passed. Full-suite execution exposed a test-stub package-attribute leak introduced by the new registry stub; corrected its isolation and reran the whole suite successfully. Existing unrelated API fake-coroutine RuntimeWarnings remain outside this task.
No Home Assistant/intercom connection or E2E runner was invoked on the VM. AC #6 still requires the orchestrator PR check e2e-pi. Task remains In Progress and every acceptance criterion is unchecked, as required for headless execution. Work is committed locally only; no push.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Breaking change for v1.5.0 / TASK-37 release notes: the doorbell binary sensor is removed without a deprecation period and its legacy registry entry is deleted automatically on setup, even when doorbell is disabled. Migrate automation/blueprint inputs and explicit HomeKit links to the unchanged doorbell event entity. The blueprint now resolves the camera and active call sensor by device rather than entity-name replacement; translations, user/developer docs and diagrams are updated. Local evidence: 675 unit tests, validate.py and py_compile passed on Python 3.12. The read-only E2E assertion for one event doorbell and no legacy binary sensor is added; e2e-pi remains pending before task closure.
<!-- SECTION:FINAL_SUMMARY:END -->
