---
id: TASK-30
title: Investigate SSDP discovery and IP-change handling for 2N intercoms
status: To Do
assignee: []
created_date: '2026-10-13 19:03'
updated_date: '2026-10-15 12:47'
labels:
  - discovery
  - config-flow
  - github-issue
dependencies: []
references:
  - custom_components/2n_intercom/quality_scale.yaml
  - custom_components/2n_intercom/config_flow.py
  - docs/ROADMAP-NAVRH.md
  - 'https://github.com/mastalir1980/ha-2N-intercom/issues/11'
priority: low
type: spike
ordinal: 38000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GitHub issue #11 (https://github.com/mastalir1980/ha-2N-intercom/issues/11): a user shows 2N devices answering in an SSDP browser and asks for auto discovery and automatic IP update when the address changes.

This conflicts with what the repo says today: `quality_scale.yaml` marks discovery and discovery-update-info as exempt ("does not broadcast a discoverable mDNS/SSDP service that maps to a unique device id"), and docs/ROADMAP-NAVRH.md E1 (DHCP discovery) was dropped on 2026-08-30, with E2 (mDNS/ONVIF) at P3. The issue suggests the exemption reason may be wrong.

Spike: check what the ground-truth E2E intercom fw 3.x (and, if available, an IP Verso 2.50 report) advertises over SSDP/UPnP - ST/NT, USN, LOCATION, SERVER, and whether the device description contains a stable id (serial number or MAC) that matches what the integration uses as unique_id. Then propose whether to add an `ssdp` matcher, `async_step_ssdp`, and host update on IP change (discovery-update-info).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Notes contain the real SSDP response and UPnP device description from the ground-truth device (no secrets)
- [ ] #2 Notes state whether a stable unique id is available and whether it matches the config entry unique_id
- [ ] #3 Jan has decided go / no-go; on go, a ready feature task exists, on no-go quality_scale.yaml exemption text is corrected to the real reason
<!-- AC:END -->
