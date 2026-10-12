---
id: TASK-6
title: Fire 2n_intercom_event on the HA event bus with person attribution
status: To Do
assignee: []
created_date: '2026-08-30 09:27'
labels:
  - access-control
  - automation
dependencies:
  - TASK-4
priority: high
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
For every doorbell and access-control event, fire a 2n_intercom_event on the Home Assistant event bus (hass.bus.async_fire) with a structured payload: device_id, config_entry_id, event type, user uuid + resolved name (from task-4), credential type, direction, result, session/call info where relevant. This enables automations like 'when a specific person arrives'. Document the event schema in README.md with an automation example. Do not fire events for internal state-sync log entries (SwitchStateChanged etc.) — only user-facing events (ring, access, security).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 2n_intercom_event fired on ring and access events with documented payload schema
- [ ] #2 Payload includes device_id so device triggers can later attach to it
- [ ] #3 README.md documents the event schema with a YAML automation example
- [ ] #4 Unit tests assert bus events are fired with expected payloads
<!-- AC:END -->
