---
id: TASK-7
title: >-
  Add security event sensors (tamper, unauthorized door open, door open too
  long, silent alarm)
status: To Do
assignee: []
created_date: '2026-08-30 09:27'
labels:
  - access-control
  - security
  - ha-platform
dependencies:
  - TASK-4
  - TASK-6
priority: high
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Subscribe to security-related log events: TamperSwitchActivated, UnauthorizedDoorOpen, DoorOpenTooLong, SilentAlarm, LoginBlocked (same graceful-degradation pattern as task-4). Expose them in HA as: binary_sensor with device_class tamper for TamperSwitchActivated; binary_sensor with device_class safety (or event entities where a momentary event fits better) for UnauthorizedDoorOpen / DoorOpenTooLong / SilentAlarm; a diagnostic entity for LoginBlocked. Also fire them via the 2n_intercom_event bus channel from task-6. Add strings/translations and icons.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Tamper binary_sensor reflects TamperSwitchActivated state
- [ ] #2 UnauthorizedDoorOpen, DoorOpenTooLong, SilentAlarm and LoginBlocked are exposed as entities and fired on the event bus
- [ ] #3 Devices lacking these events degrade gracefully (covered by test)
- [ ] #4 strings.json, translations (en/de/cs) and icons.json updated; unit tests added
<!-- AC:END -->
