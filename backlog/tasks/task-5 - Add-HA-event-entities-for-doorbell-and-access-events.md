---
id: TASK-5
title: Add HA event entity for access-control events
status: To Do
assignee: []
created_date: 2026-08-30 09:27
updated_date: '2026-10-24T08:29:00Z'
labels:
  - access-control
  - ha-platform
  - needs-analysis
milestone: m-1
dependencies:
  - TASK-4
  - TASK-53
  - TASK-6
priority: high
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add an access event entity to the event platform: fired on access-control events from task-4, with event types like card, code, mobile_key, fingerprint, granted, denied and attributes (user name, credential type, direction). The doorbell event entity and the event platform itself are split out into TASK-53 (v1.5.0); build on that platform. Add strings/translations (en, de, cs) and icons. Follow the existing TwoNIntercomEntity base class conventions.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 access event entity fires on access events with correct event_type and attributes
- [ ] #2 strings.json, translations (en/de/cs) and icons.json updated
- [ ] #3 Unit tests for the new platform (mirror tests/test_binary_sensor.py style)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 (Jan): in scope of v1.6.0 (access and security events in automations are the main feature of the version). Not ready yet: needs analysis (payload schema and event types checked against log events from the E2E intercom and the 2N Logged Events manual), implementation plan and verifier tags on every criterion before it is assigned to @copilot. Order: TASK-6, then TASK-5 and TASK-7.
<!-- SECTION:NOTES:END -->
