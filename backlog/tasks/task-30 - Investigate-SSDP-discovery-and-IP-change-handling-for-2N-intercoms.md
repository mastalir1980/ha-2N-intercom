---
id: TASK-30
title: Investigate SSDP discovery and IP-change handling for 2N intercoms
status: Done
assignee: []
created_date: '2026-10-13 19:03'
updated_date: '2026-10-16 15:37'
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
- [x] #1 Notes contain the real SSDP response and UPnP device description from the ground-truth device (no secrets)
- [x] #2 Notes state whether a stable unique id is available and whether it matches the config entry unique_id
- [x] #3 Jan has decided go / no-go; on go, a ready feature task exists, on no-go quality_scale.yaml exemption text is corrected to the real reason
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Findings 2026-10-16 (Claude), checked against the E2E intercom (fw 3.x) and PR #30 (vemboy200, Control4 DS2 / DS2 Mini):
- The device serves its UPnP description at /ssdp_server/description.xml (HTTP and HTTPS, no auth). manufacturer = "2N, part of Axis group", deviceType = urn:schemas-upnp-org:device:Basic:1; friendlyName, modelName and presentationURL are present, modelNumber is absent.
- serialNumber in description.xml is the MAC (12 hex digits) and equals macAddr from /api/system/info after normalisation; UDN ends with the same MAC.
- /api/system/info serialNumber is the real 2N serial (NN-NNNN-NNNN), NOT the MAC. The config entry unique_id is that serial, so the SSDP serialNumber does not match the unique_id. A stable id exists (the MAC), but the entry has to store it separately. PR #30 does exactly that (mac_address in entry.data, backfilled for existing entries), so its design holds on a native 2N, not only on Control4 units.
- The quality_scale.yaml exemption reason ("does not broadcast a discoverable SSDP service") is wrong.
- Not captured: the raw M-SEARCH/NOTIFY response (the analysis VM is not on the multicast segment). The HA ssdp matcher works on the description fields above, so it is not needed for the decision.
Decision (Jan, 2026-10-16): go, in v1.5.0, building on PR #30. The silent host update on IP change is accepted as in HA core (discovery-update-info pattern), with a log line and a README note. Feature task: TASK-49.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Spike done against the E2E intercom (fw 3.x) and PR #30: 2N devices announce over SSDP with manufacturer "2N, part of Axis group"; description.xml serialNumber is the MAC, not the 2N serial used as unique_id, so the MAC is stored separately. Jan decided go (v1.5.0); implementation tracked in TASK-49 building on PR #30.
<!-- SECTION:FINAL_SUMMARY:END -->
