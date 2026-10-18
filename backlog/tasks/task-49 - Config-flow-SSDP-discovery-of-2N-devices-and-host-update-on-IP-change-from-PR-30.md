---
id: TASK-49
title: >-
  Config flow: SSDP discovery of 2N devices and host update on IP change (from
  PR #30)
status: To Test
assignee:
  - '@copilot'
created_date: '2026-10-16 15:37'
updated_date: '2026-10-18 08:15'
labels:
  - discovery
  - config-flow
  - github-pr
  - github-issue
  - manual-close
milestone: m-0
dependencies:
  - TASK-41
  - TASK-48
references:
  - 'https://github.com/mastalir1980/ha-2N-intercom/pull/30'
  - 'https://github.com/mastalir1980/ha-2N-intercom/issues/11'
  - custom_components/2n_intercom/config_flow.py
  - custom_components/2n_intercom/__init__.py
  - custom_components/2n_intercom/manifest.json
  - custom_components/2n_intercom/diagnostics.py
  - custom_components/2n_intercom/quality_scale.yaml
  - e2e/e2elib/twon.py
  - README.md
  - TASK-30
priority: medium
type: feature
ordinal: 56000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: users have to type the intercom IP by hand, and when the device gets a new address from DHCP the integration silently stops working until the user runs Reconfigure. GitHub issue #11 shows that 2N devices announce themselves over SSDP. External PR #30 (vemboy200, tested on Control4 DS2 / DS2 Mini) adds an ssdp matcher, async_step_ssdp, a separate mac_address in entry.data (backfilled for existing entries) and a silent host update + reload when a configured device shows up on a new address.

Evidence (TASK-30, E2E intercom fw 3.x): /ssdp_server/description.xml (no auth) has manufacturer "2N, part of Axis group"; its serialNumber is the MAC and equals macAddr from /api/system/info; UDN ends with the MAC; /api/system/info serialNumber is the real 2N serial (the config entry unique_id), not the MAC. So the PR design (match on a separately stored MAC, not on unique_id) is right for native 2N devices too. PR #30 merges cleanly into main as of 2026-10-16 and its unit tests pass (617 tests, Python 3.12).

Decided with Jan 2026-10-16: ship in v1.5.0, building on PR #30 (keep vemboy200 as the commit author, credit in the PR body, "Closes #30, fixes #11"). The silent host update is accepted as in HA core (discovery-update-info pattern), but it must be visible: an info log line and a README note. Review fixes on top of the PR are listed in the acceptance criteria. The headless coder carries the PR because e2e-pi does not run on fork PRs.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 manifest.json has an ssdp matcher on manufacturer "2N, part of Axis group"; a discovered device that is not configured yet opens a setup flow with the host prefilled and the discovered friendlyName as the default name - unit test
- [ ] #2 A discovery for an already-configured device (same MAC, normalised) on a new host updates entry.data host, reloads the entry once and aborts with already_configured; same host aborts without reload - unit tests
- [ ] #3 The host update logs one INFO line with the entry title, old host and new host (no credentials, no MAC) - unit test
- [ ] #4 Announcement without a usable MAC aborts with no_mac; without a usable host it aborts with a new reason no_host (not cannot_connect); strings.json and en/de/cs translations have both reasons and flow_title - unit tests
- [ ] #5 mac_address is stored in entry.data by the user step and backfilled from /api/system/info macAddr for existing entries on setup; reauth and reconfigure keep it - unit tests
- [ ] #6 diagnostics redacts mac_address (privacy: users post diagnostics in public issues) - unit test
- [ ] #7 E2E (read-only): description.xml on the E2E intercom has the manufacturer string used by the manifest matcher and its serialNumber equals /api/system/info macAddr after normalisation ("HA expects X <-> 2N says X"); the deployed entry diagnostics contain mac_address (redacted), proving the backfill ran
- [ ] #8 README documents automatic discovery, that the host follows the device on an IP change, and that this trusts devices on the local network; quality_scale.yaml discovery and discovery-update-info are done with a correct comment
- [ ] #9 Full unit suite, validate.py and py_compile green on Python 3.12+; PR check e2e-pi green; Jan verifies on a real device that an unconfigured 2N shows up under Discovered and that an entry follows an IP change (manual-close)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Cherry-pick the single commit from PR #30, preserving vemboy200 as author and the existing serial-based unique_id, dual authentication, and data/options separation.
2. Complete SSDP abort reasons, safe INFO host-change logging, MAC redaction, and regression coverage for discovery, backfill, reauth, and reconfigure.
3. Add an independent namespace-aware SSDP XML reader and read-only E2E coverage comparing the manifest matcher, device identity, and redacted entry diagnostics.
4. Document automatic discovery, DHCP address following, and local-network trust; update quality-scale comments without a version or changelog change.
5. Run the required Python 3.12+ local gates, record implementation notes and PR attribution/closing text, and commit locally. Leave acceptance criteria unchecked and status In Progress; e2e-pi and manual device verification remain external gates.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Carried PR #30 as commit f7de124, preserving the original contributor as author; resolved additive conflicts with TASK-41/TASK-48 without removing their behavior. PR attribution: based on @vemboy200 contribution. Required PR body text: Closes #30, fixes #11.

Completed no_mac/no_host handling and all translations, a single INFO host-change message, entry MAC redaction, and regression tests for normalized identity, exactly one scheduled reload per host change, unchanged-host/repeated-announcement no-ops, user-step MAC storage, setup backfill, and reauth/reconfigure preservation. Kept the serial-based unique_id, connection/options split, authentication code, manifest version, and CHANGELOG unchanged. Fixed the inherited discovery-name issue: friendlyName now remains the default after the user submits credentials. Invalid/blank MACs and malformed or missing announcement URLs abort with the appropriate reason; a usable location URL remains a fallback.

Added TwoN.ssdp_description() using unauthenticated GET, existing client TLS/timeout settings, namespace-aware ElementTree parsing, and explicit HTTP/XML/missing-field errors. Added offline XML-client regressions and read-only e2e/tests/test_60_discovery.py comparing the local manifest matcher with the device manufacturer, normalized SSDP/API MAC identities, and redacted mac_address in deployed entry diagnostics. Assertions compare private identities via booleans to avoid printing them. README and architecture/quality-scale docs explain discovery, address following, backfill, and local-network trust with HTTPS guidance.

Local gates passed on Python 3.12.15: python3 -m unittest discover -s tests -t tests (655 tests), python3 validate.py, and python3 -m py_compile custom_components/2n_intercom/*.py. The new E2E files also compile. Independent read-only diff review reported no significant issues. No E2E or device/HA requests were run on the VM; e2e-pi and the manual Discovered/IP-change checks remain pending. Kept status In Progress and all acceptance criteria unchecked because this is manual-close.

Existing harness follow-up, outside this task: selecting test_config_flow as the first isolated unittest module fails because its loader depends on coordinator stubs initialized by other modules. The required full discovery-based suite is green; no unrelated test infrastructure changes were made.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented SSDP discovery and MAC-based host following from PR #30, preserving contributor authorship and serial-based config-entry identity. Added abort/logging/privacy fixes, setup backfill and flow regressions, read-only discovery E2E coverage, and trust documentation. All 655 unit tests, validate.py, and py_compile pass on Python 3.12.15. Awaiting e2e-pi and manual device verification; acceptance criteria remain unchecked and status remains In Progress.
<!-- SECTION:FINAL_SUMMARY:END -->
