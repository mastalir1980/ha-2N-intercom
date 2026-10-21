---
id: TASK-68
title: >-
  SSDP host update trusts any announcement: verify the device identity before
  switching entry.data host
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-21T09:44:00Z'
updated_date: '2026-10-21T09:47:00Z'
labels:
  - security
  - bug
  - config-flow
  - discovery
milestone: m-0
dependencies: []
references:
  - custom_components/2n_intercom/config_flow.py
  - custom_components/2n_intercom/api.py
  - tests/test_config_flow.py
  - e2e/tests/test_60_discovery.py
  - README.md
  - TASK-67
  - TASK-49
  - docs/SECURITY-REVIEW-v1.5.0.md
priority: medium
type: bug
ordinal: 73000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the security review before v1.5.0 (docs/SECURITY-REVIEW-v1.5.0.md, finding S-2).

**Current behaviour.** `async_step_ssdp` (config_flow.py:368-438) matches the announcement's `serialNumber` (= MAC) against the stored `mac_address` and, when the host differs, rewrites `entry.data[host]` and reloads the entry — without contacting the new host. The MAC is public on the LAN (ARP table, the device's unauthenticated `/ssdp_server/description.xml`), so any LAN host can send one SSDP NOTIFY / M-SEARCH reply with manufacturer "2N, part of Axis group", that MAC and its own presentation URL. TASK-49 accepted the HA core discovery-update-info pattern as "trusts the local network", but the consequences were not analysed. After the rewrite the integration talks to the attacker's host and (1) with `verify_ssl=False` sends the API password on a Basic challenge (see TASK-67), (2) performs the RTSP Digest handshake against it, (3) accepts fake log events (ring, access-control events with any user name) and relay/IO state, (4) door control and the doorbell stop working until the next genuine announcement or a manual Reconfigure. Only one INFO line records the change.

**Expected behaviour.** A host change coming from SSDP takes effect only after the integration has confirmed that the new host is the same device: connect with the stored credentials and TLS settings, read `/api/system/info`, compare the normalised `macAddr` with `entry.data[mac_address]` (and `serialNumber` with the entry unique_id when it is serial-based). Otherwise the announcement is ignored and one WARNING is logged (rate-limited, no credentials). The verification request must never fall back to HTTP Basic on an unverified connection (a client flag that disables the Basic fallback, independent of TASK-67).

**Evidence.** Unit tests `test_ssdp_updates_host_for_already_configured_device` and `test_ssdp_no_op_when_host_unchanged` (tests/test_config_flow.py:1196-1262) show the update happens without any request to the new host. Observed by code reading only; not reproduced on the LAN.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An SSDP announcement for a configured MAC with a new host whose /api/system/info reports the same MAC (and serial) updates entry.data host and reloads the entry once, as today [unit]
- [ ] #2 An announcement whose new host is unreachable, rejects the credentials, or reports a different MAC/serial leaves entry.data unchanged, does not reload and logs one WARNING without credentials [unit]
- [ ] #3 Repeated announcements for the same rogue host do not flood the log: one WARNING per host per entry lifetime [unit]
- [ ] #4 The verification request never falls back to HTTP Basic auth when the certificate is not verified, regardless of allow_insecure [unit]
- [ ] #5 README "Automatic discovery" states that the address follows the device only after the device identity has been confirmed with the stored credentials [unit]
- [ ] #6 e2e/tests/test_60_discovery.py (read-only) keeps passing [e2e]
- [ ] #7 Full unit suite, validate.py and py_compile green; PR check e2e-pi green [e2e]
- [ ] #8 Jan verifies on the real device that an IP change is still followed after the fix (manual-close) [jan]
<!-- AC:END -->
