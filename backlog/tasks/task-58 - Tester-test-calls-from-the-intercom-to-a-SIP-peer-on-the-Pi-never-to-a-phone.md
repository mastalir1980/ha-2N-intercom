---
id: TASK-58
title: 'Tester: test calls from the intercom to a SIP peer on the Pi, never to a phone'
status: To Do
assignee: []
created_date: '2026-10-18 15:48'
updated_date: '2026-10-18 15:50'
labels:
  - infra
  - agent
  - manual-path
  - on-hold
dependencies:
  - TASK-59
priority: low
ordinal: 65000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Lets the tester verify outgoing-call ring detection without anyone at the door. Calls are made only from the intercom to one allowlisted SIP peer (baresip on the Pi). Note: an API dial is probably originator=api, not button, so this does not replace the physical button check (hypothesis, verify on the device).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Jan creates a dedicated 2N account with call control only (no switch control) and stores it outside the repo
- [ ] #2 The wrapper dials only the single SIP URI from a root-owned config file on the Pi; any other number, My2N or phone number is refused - unit tests
- [ ] #3 Every test call is hung up by the wrapper, with a hard timeout
- [ ] #4 Check: dial -> HA doorbell on, call_state sensor follows; result in the tester report
<!-- AC:END -->
