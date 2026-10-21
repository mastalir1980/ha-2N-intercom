---
id: TASK-68
title: >-
  SSDP host update trusts any announcement: verify the device identity before
  switching entry.data host
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-21T09:44:00Z'
updated_date: '2026-10-21 14:44'
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add an API-client switch that disables Basic fallback independently of allow_insecure, retaining the normal dual-auth defaults. Allow system-info verification failures to be logged only by the discovery caller.
2. Before updating a configured SSDP host, query system/info using saved connection settings and credentials. Require a normalized MAC match and a serial match for serial-based unique IDs; preserve legacy host/MAC-based entries, close the temporary client, and leave the entry untouched on failure. Deduplicate warnings per entry and candidate host across discovery flows/reloads.
3. Extend config-flow and request-path unit coverage for identity matches/mismatches, failed requests, warning deduplication, saved TLS/auth options, and unchanged hosts. Update Automatic discovery and the architecture documentation; keep existing read-only discovery E2E checks unchanged.
4. Run the targeted unit tests and all required local gates. Record implementation notes and commit TASK-68 locally without pushing, checking criteria, finalizing the task, or contacting HA/the intercom.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented SSDP host verification with a temporary API client using the saved credentials, protocol, port, TLS settings and allow_insecure option precedence. The normalized API MAC must match; serial-based unique IDs additionally require the API serial to match. Verification clients are always closed. Unchanged hosts make no request, and concurrent successful announcements schedule only one update/reload.
Added allow_basic_fallback to the API client, defaulting to the existing normal dual-auth behavior. SSDP enables it only for verified HTTPS, so allow_insecure cannot override the discovery safety policy. System-info probes delegate error logging to the discovery flow, avoiding duplicate warnings and untrusted error/credential text. Warning memory is shared in hass.data per entry ID and candidate host, independent of flow instances and reloadable runtime_data; rejected hosts remain eligible for later successful verification.
Updated README Automatic discovery and the architecture documentation. Existing read-only e2e/tests/test_60_discovery.py is unchanged.
Local evidence (Python 3.12.15): full unittest discovery passed 713 tests; python3 validate.py passed; python3 -m py_compile custom_components/2n_intercom/*.py passed; git diff --check passed.
AC #1 evidence: test_ssdp_updates_host_for_already_configured_device verifies normalized MAC/serial matching, preservation of identity/settings, and one update/reload; test_ssdp_concurrent_matching_announcements_reload_once covers concurrent discovery.
AC #2 evidence: test_ssdp_rejects_unverifiable_hosts_without_changing_entry covers unreachable/auth/API failures, different or missing identities, malformed results, unchanged entry data, no reload, cleanup and one credential-free WARNING.
AC #3 evidence: test_ssdp_warning_is_once_per_host_per_entry_across_flows covers repeated failures across new flows and runtime replacement, distinct hosts and distinct entries. The real-client Basic-challenge flow test also verifies warning deduplication without API log duplication.
AC #4 evidence: test_ssdp_unverified_basic_challenge_never_receives_credentials exercises the real API request path from SSDP over HTTP and unverified HTTPS with both insecure-option values; test_basic_fallback_can_be_disabled_independently_of_transport_opt_in covers all transport/TLS/opt-in combinations. Saved verified-HTTPS behavior is covered by test_ssdp_verification_preserves_saved_transport_and_auth_settings.
AC #5 evidence: README Automatic discovery now explicitly states identity confirmation at the new address with stored API credentials and TLS settings before the host changes.
AC #6: pending the orchestrator-run e2e-pi check; discovery E2E file retained unchanged.
AC #7: all three required local gates passed; e2e-pi is pending. No HA/intercom or E2E commands were run on this VM.
AC #8: manual verification by Jan remains outstanding. Task intentionally remains In Progress with all acceptance criteria unchecked for orchestrator review/finalization.
<!-- SECTION:NOTES:END -->
