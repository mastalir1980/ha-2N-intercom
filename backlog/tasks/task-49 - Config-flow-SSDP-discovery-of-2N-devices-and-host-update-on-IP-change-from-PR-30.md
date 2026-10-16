---
id: TASK-49
title: >-
  Config flow: SSDP discovery of 2N devices and host update on IP change (from
  PR #30)
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-16 15:37'
updated_date: '2026-10-16 15:37'
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
1. Start from PR #30: in the task worktree run `git fetch origin pull/30/head:pr30` and `git cherry-pick` its single commit (keeps vemboy200 as author). Resolve conflicts against main (TASK-41 and TASK-48 change config_flow.py first; this task depends on them). Keep the PR design: CONF_MAC = "mac_address" in const.py, _normalize_mac, async_step_ssdp, MAC backfill in __init__.py async_setup_entry, ssdp matcher in manifest.json.
2. config_flow.py async_step_ssdp: rename abort reason cannot_connect -> no_host for "no host in the announcement"; keep no_mac. Update strings.json + translations/{en,de,cs}.json (abort.no_host, abort.no_mac, flow_title) and drop the ssdp-specific cannot_connect text.
3. config_flow.py host update branch: before async_update_entry log `_LOGGER.info("2N intercom %s moved from %s to %s (SSDP); updating the entry", entry.title, old_host, host)`. Never log credentials or the MAC. Keep reload as an async task, once per change.
4. diagnostics.py: add CONF_MAC to TO_REDACT_ENTRY.
5. Check reauth/reconfigure keep mac_address in entry.data (they merge into existing data; add a unit test each, fix only if it is dropped).
6. tests/test_config_flow.py: keep the PR tests, adjust to no_host, add tests for the INFO log line, same-host discovery (no reload), and reconfigure keeping mac_address. tests/test_diagnostics*.py (or the existing diagnostics test file): mac_address redacted.
7. e2e/e2elib/twon.py: add `ssdp_description() -> dict[str, str]` that GETs /ssdp_server/description.xml (same session/verify settings, no auth needed) and returns manufacturer, serialNumber, UDN parsed with xml.etree (namespace-aware). Do not import the integration. New e2e test in e2e/tests/test_10_entities.py or a new test_60_discovery.py: (a) manufacturer equals the string in manifest.json ssdp matcher (read the manifest file); (b) normalised serialNumber == normalised system_info()["macAddr"]; (c) `/api/diagnostics/config_entry/<id>` data.entry.data has key mac_address (value redacted). Read-only, no relay marker. Never print the MAC or serial in assertions/messages.
8. README.md: in Installation/Configuration add "Automatic discovery" (2N and Control4 DS2 units show up under Settings > Devices & services > Discovered; the entry follows the device when its IP changes; this trusts the local network - a device announcing the same MAC would receive the connection, use HTTPS). quality_scale.yaml: keep the PR texts for discovery / discovery-update-info, fix wording if needed.
9. Must not change: unique_id stays the 2N serial (existing entries must not be re-created); dual Basic/Digest auth in api.py; entry.data vs entry.options split (mac_address and host are data). No CHANGELOG/version bump (release task TASK-37).
10. PR body: "Closes #30, fixes #11", credit vemboy200. Validation: unit suite + validate.py + py_compile on Python 3.12+, PR check e2e-pi green. AC #9 manual part is Jan's (manual-close).
<!-- SECTION:PLAN:END -->
