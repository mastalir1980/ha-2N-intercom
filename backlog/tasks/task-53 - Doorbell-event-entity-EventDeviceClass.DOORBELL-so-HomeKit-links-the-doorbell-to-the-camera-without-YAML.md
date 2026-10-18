---
id: TASK-53
title: >-
  Doorbell event entity (EventDeviceClass.DOORBELL) so HomeKit links the
  doorbell to the camera without YAML
status: To Test
assignee:
  - '@copilot'
created_date: '2026-10-18 08:41'
updated_date: '2026-10-18 09:54'
labels:
  - doorbell
  - homekit
  - ha-platform
  - manual-close
milestone: m-0
dependencies: []
references:
  - custom_components/2n_intercom/binary_sensor.py
  - custom_components/2n_intercom/coordinator.py
  - custom_components/2n_intercom/__init__.py
  - custom_components/2n_intercom/image.py
  - tests/test_binary_sensor.py
  - tests/_stubs.py
  - HOMEKIT_INTEGRATION.md
  - 'https://www.home-assistant.io/integrations/event/'
  - 'https://www.home-assistant.io/integrations/homekit/'
  - >-
    https://github.com/home-assistant/core/blob/dev/homeassistant/components/homekit/__init__.py
priority: high
type: feature
ordinal: 60000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: users want the 2N doorbell to ring their HomePods / show as a video doorbell in Apple Home. Today the only doorbell entity is `binary_sensor.<intercom>_doorbell` (device_class OCCUPANCY, `binary_sensor.py` TwoNIntercomDoorbell). A HomeKit Bridge set up from the HA UI then shows the doorbell as a separate occupancy accessory, not as the doorbell of the camera, because HA HomeKit auto-links a doorbell to a camera on the same device ONLY for an `event` entity with device class `doorbell` (homeassistant/components/homekit/__init__.py, linked-sensor lookup `DOORBELL_EVENT_SENSOR`; there is no binary_sensor doorbell case). The UI options flow cannot set `linked_doorbell_sensor`, so today users must write HomeKit YAML (HOMEKIT_INTEGRATION.md). Reproduced on a real setup on 2026-10-18.

Current behaviour: no `event` platform; HomeKit via UI = camera + separate occupancy sensor, no doorbell chime.
Expected behaviour: an `event.<intercom>_doorbell` entity with device_class doorbell on the same device as the camera fires `ring` once per real ring; a HomeKit Bridge created only from the UI (accessory mode, camera entity) shows a video doorbell and HomePods chime.

Splits the doorbell half out of TASK-5 (TASK-5 keeps the access event entity). Required for v1.5.0 (Jan, 2026-10-18).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 New `event` platform (`event.py`) creates one doorbell event entity per config entry when `enable_doorbell` is on (same condition as the doorbell binary_sensor); not created when it is off
- [ ] #2 The entity extends TwoNIntercomEntity (same device as the camera), has device_class `EventDeviceClass.DOORBELL`, `event_types == ["ring"]`, translation key `doorbell`, unique_id `<entry_id>_doorbell_event`
- [ ] #3 Exactly one `ring` event is fired per ring, although CallStateChanged and CallSessionStateChanged both report it (unit test feeds both events and asserts one trigger)
- [ ] #4 No event for calls into the intercom (TASK-31 rules) and none for peers filtered out by the Called ID filter (TASK-45/47 rules); unit tests for both
- [ ] #5 Event attributes carry `called_peer` (and caller name/number when known), same values as the binary_sensor attributes; no secrets
- [ ] #6 Existing `binary_sensor.<intercom>_doorbell` is unchanged (state, device class, unique_id, attributes); existing tests stay green
- [ ] #7 strings.json, translations en/de/cs and icons.json have the new entity (mdi:doorbell); test_translations green
- [ ] #8 HOMEKIT_INTEGRATION.md and README.md: UI-only HomeKit setup (accessory mode, include just the camera) is the primary path and auto-links `event.<intercom>_doorbell`; YAML `linked_doorbell_sensor` kept as fallback; the "YAML required / cannot be set from the UI" statements are gone; the misleading OCCUPANCY rationale is fixed (TwoNIntercomDoorbell docstring + HOMEKIT_INTEGRATION.md "Doorbell device class")
- [ ] #9 E2E (read-only, no relays): the doorbell event entity exists in staging HA with device_class doorbell, event_types [ring], the same device_id as the camera entity, and is available while the intercom is reachable
- [ ] #10 Manual (manual-close, Jan): a button press on the real intercom fires exactly one `ring` in HA; a UI-only HomeKit Bridge shows a video doorbell in Apple Home and the HomePod chimes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add a monotonic coordinator ring_count only in the existing new-ring guard, preserving ring direction, peer filtering, pulse and binary sensor behavior.
2. Add the coordinator-backed doorbell EventEntity and enable its platform alongside the doorbell binary sensor; baseline the counter when added and emit ring with the existing caller metadata only on new rings.
3. Add event translations/icons and focused unit coverage for setup, lifecycle, deduplication, incoming calls, peer filtering and metadata.
4. Add a read-only staging E2E assertion for event class/types, availability and camera device association.
5. Update HomeKit and README guidance to prefer UI-only camera accessory auto-linking and retain YAML as fallback; correct the binary sensor docstring.
6. Run the required Python local gates, record results and remaining Pi/manual checks, and commit locally without marking criteria or task Done.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented the doorbell event platform with EventDeviceClass.DOORBELL, event_types [ring], the shared device identity and unique ID <entry_id>_doorbell_event. It is forwarded only with enable_doorbell. The coordinator counter increments only at the existing new-ring guard, independently of snapshot enablement; the entity baselines at add time and allowlists called_peer/caller_name/caller_number from the same sources as the binary sensor.
Added unit coverage for paired and batched call events, subsequent rings, pulse independence, incoming calls, Called ID filtering, safe caller metadata, startup/re-add behavior, availability, platform toggles and translations. Existing binary-sensor runtime behavior is unchanged. The current binary-sensor code does not explicitly declare OCCUPANCY; its inherited device class is preserved, and the misleading docstring/rationale was removed rather than changing the entity.
Added a read-only staging E2E check for event presence, doorbell class, ring type, availability while the independent 2N client can reach the device, and the camera device_id link. Updated HOMEKIT_INTEGRATION.md, README.md and architecture documentation to describe UI-only camera accessory setup, automatic event linking and the explicit YAML fallback.
Local validation on Python 3.12: all 670 unit tests passed; python3 validate.py passed; integration py_compile passed. The new E2E test file also compiles without importing or running E2E fixtures. No Home Assistant/intercom calls or E2E runner were executed on the VM.
Pending: the orchestrator must run e2e-pi, and Jan must perform AC #10 (one physical press -> one HA ring, UI-only HomeKit video doorbell and HomePod chime). Task remains In Progress with all acceptance criteria unchecked under manual-close. No version bump, CHANGELOG change, protected-path edit or push.
<!-- SECTION:NOTES:END -->
