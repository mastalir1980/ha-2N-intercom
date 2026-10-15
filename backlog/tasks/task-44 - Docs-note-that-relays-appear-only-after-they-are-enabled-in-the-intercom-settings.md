---
id: TASK-44
title: >-
  Docs: note that relays appear only after they are enabled in the intercom
  settings
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-15 16:37'
updated_date: '2026-10-15 16:39'
labels:
  - docs
milestone: m-0
dependencies:
  - TASK-43
priority: low
type: docs
ordinal: 51000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: a user who activated the relay/switch function on the intercom did not understand that the relay entities appear only after it is enabled in the intercom settings, and that without an enabled relay nothing is shown in Home Assistant. The integration creates relay entities from /api/switch/caps, which lists only enabled relays. Expected behaviour: the user documentation says that if no relay appears, the relay must first be enabled in the intercom's own administration (web interface), and that the integration cannot enable it. The options flow stays as it is.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 README.md (section on relays / the relay control entities) states that relays appear only when enabled in the intercom settings and that the integration does not enable them
- [ ] #2 INSTALLATION.md gets the same note in its troubleshooting or relay section, if such a section exists
- [ ] #3 The wording avoids mentioning admin account names or device-specific paths; uses the neutral term 'intercom settings'
- [ ] #4 validate.py green
<!-- AC:END -->
