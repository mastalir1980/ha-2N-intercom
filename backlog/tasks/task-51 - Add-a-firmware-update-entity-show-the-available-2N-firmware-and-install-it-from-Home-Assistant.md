---
id: TASK-51
title: >-
  Add a firmware update entity: show the available 2N firmware and install it
  from Home Assistant
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-17 09:27'
labels:
  - firmware
  - update-entity
  - manual-close
  - on-hold
milestone: m-0
dependencies:
  - TASK-50
references:
  - docs/ROADMAP-NAVRH.md
  - docs/API_REFERENCE.md
  - custom_components/2n_intercom/coordinator.py
  - custom_components/2n_intercom/api.py
  - custom_components/2n_intercom/__init__.py
  - custom_components/2n_intercom/config_flow.py
priority: medium
type: feature
ordinal: 58000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: roadmap D1 - users with one or more intercoms should see in HA that new 2N firmware exists and install it without opening the device web UI.

Current: the firmware version is only the device sw_version (swVersion from /api/system/info). There is no update entity and no way to trigger the update.

Expected: an HA update entity per intercom with the installed and latest version, release notes when available, and an Install action that triggers the device's own update from the 2N update server. The firmware branch (Active Track / LTS / Beta) is chosen in the integration options. Install only happens on explicit user action. The mechanism comes from the investigation task (dependency); this task stays on-hold until that task fills in the API details.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 New update platform: one entity per config entry, extends TwoNIntercomEntity, device_class firmware, entity_category config; unit test
- [ ] #2 installed_version equals swVersion from /api/system/info; unit test
- [ ] #3 latest_version comes from the 2N update server via the mechanism from the investigation task; a failed check keeps the last known value, is logged and never breaks the coordinator or the log subscription; unit test
- [ ] #4 Release notes / release_summary are shown when the device provides them; unit test
- [ ] #5 Install triggers the device update and shows in_progress (with progress if the device reports it); after the reboot the entity reconnects and installed_version updates; never installs automatically; unit test with a mocked API
- [ ] #6 Without the System Control privilege the install fails with a translated HomeAssistantError and no partial state; unit test
- [ ] #7 New option firmware_channel (active_track / lts / beta) in entry.options with strings.json and en/de/cs translations; it is applied as the investigation defines; unit test
- [ ] #8 Version check runs on its own interval (not every coordinator poll) and once after setup; timestamps tz-aware; unit test
- [ ] #9 PLATFORMS, strings.json, translations/*.json, icons.json, diagnostics (versions only, no secrets) updated together
- [ ] #10 E2E read-only check: HA update entity installed_version and latest_version equal what the 2N API reports
- [ ] #11 E2E install test exists, is marked @pytest.mark.firmware and is excluded from default and wip runs (like relays); it runs only on Jan's explicit request
- [ ] #12 README '2N API Endpoints Used' and docs/API_REFERENCE.md updated
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files: new custom_components/2n_intercom/update.py; __init__.py (PLATFORMS); api.py (check / trigger / branch methods per the investigation, using the existing dual-auth request path); coordinator.py (separate firmware check timer, cached result, degradation on errors in the MotionDetected style); const.py (CONF_FIRMWARE_CHANNEL + default); config_flow.py (options field); strings.json, translations/{en,de,cs}.json, icons.json; diagnostics.py; tests/test_update.py + stubs for UpdateEntity in tests/_stubs.py; e2e/tests/test_firmware.py using e2elib/twon.py (stays independent of api.py).
Must not change: dual Basic/Digest auth in api.py; event-driven state and ring detection; entry.data vs entry.options split; no secrets in logs/diagnostics; broad except only for logged degradation.
If excluding the firmware marker needs changes in protected paths (e2e/scripts, e2e/ci), split that part into a separate @copilot-mac manual-path task.
<!-- SECTION:PLAN:END -->
