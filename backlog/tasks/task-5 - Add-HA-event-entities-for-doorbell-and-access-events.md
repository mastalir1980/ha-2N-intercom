---
id: TASK-5
title: Add HA event entities for doorbell and access events
status: To Do
assignee: []
created_date: '2026-08-30 09:27'
labels:
  - access-control
  - ha-platform
dependencies:
  - TASK-4
priority: high
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add an event platform (event.py) to the integration. Create: (1) a doorbell event entity with device_class doorbell fired on the existing ring detection path — keep the existing binary_sensor for backwards compatibility; (2) an access event entity fired on access-control events from task-4, with event types like card, code, mobile_key, fingerprint, granted, denied and attributes (user name, credential type, direction). Register the platform in __init__.py PLATFORMS, add strings/translations (en, de, cs) and icons. Follow the existing TwoNIntercomEntity base class conventions.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 event entity with device_class doorbell fires on ring; existing doorbell binary_sensor unchanged
- [ ] #2 access event entity fires on access events with correct event_type and attributes
- [ ] #3 strings.json, translations (en/de/cs) and icons.json updated
- [ ] #4 Unit tests for the new platform (mirror tests/test_binary_sensor.py style)
<!-- AC:END -->
