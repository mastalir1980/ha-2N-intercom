---
id: TASK-53
title: >-
  Doorbell event entity (EventDeviceClass.DOORBELL) so HomeKit links the
  doorbell to the camera without YAML
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-18 08:41'
updated_date: '2026-10-18 08:45'
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
1. coordinator.py: add a monotonically increasing `ring_count` (int, starts 0) exposed as a property. Increment it ONLY where a new ring starts, i.e. inside the `if is_ringing and ring_allowed:` branch when `not self._ring_detected` (the same guard that already captures the ring snapshot once for the CallStateChanged + CallSessionStateChanged pair). Do not change any other ring logic, the pulse, `ring_active` or the peer filter.
2. New `event.py`: `TwoNIntercomDoorbellEvent(TwoNIntercomEntity, EventEntity)` with `_attr_device_class = EventDeviceClass.DOORBELL`, `_attr_event_types = ["ring"]`, `_attr_translation_key = "doorbell"`, unique_id `f"{entry_id}_doorbell_event"`. Remember the last seen `ring_count` at add time (no event on startup/restore); in `_handle_coordinator_update` when `coordinator.ring_count` grew, call `self._trigger_event("ring", {...})` with called_peer / caller_name / caller_number (same source as TwoNIntercomDoorbell.extra_state_attributes) and then `async_write_ha_state()`. Event entities are stateless otherwise; do not poll.
3. __init__.py `_get_platforms()`: append "event" in the `CONF_ENABLE_DOORBELL` branch next to "binary_sensor" (unload uses `loaded_platforms`, nothing else to change).
4. strings.json `entity.event.doorbell` (name "Doorbell"; state_attributes event_type ring), translations en/de/cs, icons.json `event.doorbell` mdi:doorbell. Keep test_translations green.
5. tests: extend tests/_stubs.py with minimal `homeassistant.components.event` stubs (EventEntity with `_trigger_event`, EventDeviceClass); new tests/test_event.py in the style of tests/test_binary_sensor.py; coordinator tests for `ring_count` (one per ring for the event pair, unchanged for incoming calls and filtered peers) in tests/test_coordinator.py.
6. e2e/tests: read-only test that finds the event entity of the config entry via the HA client and checks device_class, event_types and that its device_id equals the camera entity device_id. No relay marker.
7. Docs: HOMEKIT_INTEGRATION.md + README.md per the AC; TwoNIntercomDoorbell docstring.
Must not change: binary_sensor entity (backwards compatibility, Control4/automations rely on it), event-driven ring detection (architecture rule: ring detection is exclusively event-driven), entry.data/options split, no new options. No version bump / CHANGELOG (release task TASK-37).
<!-- SECTION:PLAN:END -->
