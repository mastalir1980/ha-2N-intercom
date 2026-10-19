---
id: TASK-51
title: >-
  Add a firmware update entity that shows when new 2N firmware is available and
  links to the device web UI
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-17 09:27'
updated_date: '2026-10-19 14:56'
labels:
  - firmware
  - update-entity
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
  - docs/API_REFERENCE.md#firmware-update
priority: medium
type: feature
ordinal: 58000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: roadmap D1 - users should see in HA that their intercom needs a firmware update. Installing from HA is moved to v1.6.0 (decision by Jan, 2026-10-19): this task only informs and links to the device web UI, where the user updates.

Current: the firmware version is only the device sw_version (swVersion from /api/system/info). Nothing tells the user that a newer firmware exists.

Facts (TASK-50, docs/API_REFERENCE.md section "Firmware update"): the public 2N update server answers GET https://update.2n.cz/hip/<firmwarePackage>/<newest|lts|early>/?current_ver=<swVersion>&ui_lang=en without authentication; 200 = newer version (version, changelog.md array, type {stable, lts, ...}), 204 = up to date. firmwarePackage is in /api/system/info on fw 3.x. The device web UI shows a new version only when the type matches the chosen track (Active track <-> stable, LTS <-> lts, Beta <-> stable=false). The device's own AutoUpdate settings are not readable with the API account, so the track is an integration option.

Expected: one HA update entity per intercom with installed and latest version and release notes, no Install button; its release_url and the device page (configuration_url) open the intercom web UI. The integration never uploads, applies or triggers firmware in this task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 New update platform: one entity per config entry, extends TwoNIntercomEntity, device_class firmware, entity_category config, supported features RELEASE_NOTES only (no INSTALL, no PROGRESS); no entity when /api/system/info has no firmwarePackage (debug log) [unit]
- [ ] #2 installed_version equals swVersion from /api/system/info and follows it after a coordinator refresh [unit]
- [ ] #3 latest_version comes from GET https://update.2n.cz/hip/<firmwarePackage>/<track>/?current_ver=<swVersion>&ui_lang=en via the HA shared client session (never the device session, no credentials sent); 204 means latest_version = installed_version; a failed or malformed check keeps the last known value, is logged once per failure streak and never breaks the coordinator or the log subscription [unit]
- [ ] #4 A 200 answer whose type does not match the selected track (newest needs stable=true, lts needs lts=true, early needs stable=false) is treated as up to date, like the device web UI [unit]
- [ ] #5 release_summary (truncated to the HA limit) and async_release_notes come from changelog.md, newest version first [unit]
- [ ] #6 release_url is the device web UI <protocol>://<host>[:<port> only when not the protocol default]/ built from entry.data, never with credentials; the same URL is set as configuration_url in the device info, so the HA device page links to the intercom [unit]
- [ ] #7 New option firmware_channel (active_track -> newest, lts -> lts, beta -> early; default active_track) in entry.options with strings.json and en/de/cs translations; the device AutoUpdate settings are not read or written [unit]
- [ ] #8 The version check runs on its own interval (not every coordinator poll), once after setup and on homeassistant.update_entity; timestamps tz-aware [unit]
- [ ] #9 PLATFORMS, strings.json, translations/*.json, icons.json and diagnostics (versions and channel only, no URLs with tokens, no secrets) updated together [unit]
- [ ] #10 The integration calls no firmware endpoint of the device (/api/firmware, /api/firmware/apply, /api/firmware/reject, /api/autoupdate/*); a unit test guards it [unit]
- [ ] #11 E2E read-only check: HA update entity installed_version equals swVersion from the 2N API, latest_version equals the update server answer for the same firmwarePackage/track (installed_version on 204), and the host in release_url equals the configured intercom host [e2e]
- [ ] #12 README documents the update entity, the channel option and that updating happens in the device web UI; README '2N API Endpoints Used' and docs/API_REFERENCE.md updated [unit]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files: new custom_components/2n_intercom/update.py (UpdateEntity, features RELEASE_NOTES only); new small module firmware.py with the update server check only: check(session, package, track, current_ver, lang) -> parsed result or None on 204, using homeassistant.helpers.aiohttp_client.async_get_clientsession(hass), never the device session with the Digest middleware; coordinator.py get_device_info(): add configuration_url (shared helper that builds the web UI URL from entry.data, also used by update.py); keep firmwarePackage from /api/system/info; const.py: CONF_FIRMWARE_CHANNEL, default, track map, FIRMWARE_CHECK_INTERVAL (6 h), FIRMWARE_UPDATE_SERVER_URL; config_flow.py options field; strings.json, translations/{en,de,cs}.json, icons.json; diagnostics.py; __init__.py PLATFORMS; tests/test_update.py, stubs for UpdateEntity/UpdateEntityFeature in tests/_stubs.py; e2e/tests/test_firmware.py read-only using e2elib/twon.py and a direct update server call (independent of api.py). No upload, apply, reject or autoupdate calls anywhere (that is the v1.6.0 task). Must not change: dual Basic/Digest auth in api.py; event-driven state and ring detection; entry.data vs entry.options split; no secrets in logs/diagnostics; broad except only for logged degradation.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-19: rescoped by Jan - v1.5.0 only informs (versions, release notes, link to the device web UI). Install moved to the v1.6.0 task that uses the device's built-in updater (GET /api/autoupdate/updatefw, 2N OS >= 3.3).
<!-- SECTION:NOTES:END -->
