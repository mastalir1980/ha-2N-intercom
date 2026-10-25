---
id: TASK-7
title: >-
  Add security event sensors (tamper, unauthorized door open, door open too
  long, silent alarm)
status: To Do
assignee: []
created_date: 2026-08-30 09:27
updated_date: '2026-10-24T08:29:00Z'
labels:
  - access-control
  - security
  - ha-platform
  - needs-analysis
milestone: m-1
dependencies:
  - TASK-4
  - TASK-6
references:
  - TASK-26
priority: high
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Subscribe to security-related log events: TamperSwitchActivated, UnauthorizedDoorOpen, DoorOpenTooLong, SilentAlarm, LoginBlocked (same graceful-degradation pattern as task-4). Expose them in HA as: binary_sensor with device_class safety (or event entities where a momentary event fits better) for UnauthorizedDoorOpen / DoorOpenTooLong / SilentAlarm; a diagnostic entity for LoginBlocked. Also fire all of them (including TamperSwitchActivated) via the 2n_intercom_event bus channel from task-6. Add strings/translations and icons.

Tamper decision (Jan, 2026-10-13): when the device reports a tamper input port in /api/io/caps (port `tamper` or `*.tamper`), the tamper state comes from that port via the API (TASK-26) and NO tamper entity is created from the TamperSwitchActivated log event. The event is still fired on the event bus. Only for devices without a tamper input port may a tamper binary_sensor (device_class tamper) be driven by the event.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 When io_caps has a tamper input port, no event-based tamper entity is created (unit test); without such a port, a tamper binary_sensor reflects TamperSwitchActivated
- [ ] #2 UnauthorizedDoorOpen, DoorOpenTooLong, SilentAlarm and LoginBlocked are exposed as entities, and all five events (incl. TamperSwitchActivated) are fired on the event bus
- [ ] #3 Devices lacking these events degrade gracefully (covered by test)
- [ ] #4 strings.json, translations (en/de/cs) and icons.json updated; unit tests added
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 (Jan): in scope of v1.6.0 (access and security events in automations are the main feature of the version). Not ready yet: needs analysis (payload schema and event types checked against log events from the E2E intercom and the 2N Logged Events manual), implementation plan and verifier tags on every criterion before it is assigned to @copilot. Order: TASK-6, then TASK-5 and TASK-7.
<!-- SECTION:NOTES:END -->
