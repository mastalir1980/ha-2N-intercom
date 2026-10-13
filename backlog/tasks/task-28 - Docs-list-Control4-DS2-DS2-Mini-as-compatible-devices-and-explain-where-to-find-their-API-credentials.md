---
id: TASK-28
title: >-
  Docs: list Control4 DS2 / DS2 Mini as compatible devices and explain where to
  find their API credentials
status: To Do
assignee: []
created_date: '2026-10-13 19:03'
labels:
  - docs
  - github-issue
dependencies: []
references:
  - README.md
  - INSTALLATION.md
  - 'https://github.com/mastalir1980/ha-2N-intercom/issues/10'
priority: low
type: docs
ordinal: 36000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GitHub issue #10 (https://github.com/mastalir1980/ha-2N-intercom/issues/10). A user reports the integration works with the Control4 DS2 door station (a Control4-branded 2N IP Verso) and the DS2 Mini (a branded IP Solo). Credentials are not set up in the 2N web UI as usual: they are shown in Control4 Composer Pro -> doorbell driver -> Properties -> Advanced. Nothing in the docs says these devices work, so Control4 owners do not try the integration.

The same user also reports two open problems on Control4 units (relay does not switch although the station shows the door-open icon; an intercom call started from Control4 turns the doorbell sensor on). These are tracked separately and must be mentioned as known limitations, not as working features.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 README supported devices section lists Control4 DS2 and DS2 Mini as community-reported compatible (rebranded 2N IP Verso / IP Solo), with the firmware the reporter used if known
- [ ] #2 INSTALLATION.md explains where Control4 users find the API credentials (Composer Pro, doorbell driver, Properties, Advanced)
- [ ] #3 Known limitations mention the open Control4 relay and false-doorbell reports with a link to issue #10
- [ ] #4 quality_scale.yaml docs-supported-devices comment still accurate
<!-- AC:END -->
