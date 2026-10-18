---
id: TASK-51
title: >-
  Add a firmware update entity: show the available 2N firmware and install it
  from Home Assistant
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-17 09:27'
updated_date: '2026-10-18 13:30'
labels:
  - firmware
  - update-entity
  - manual-close
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
Why: roadmap D1 - users with one or more intercoms should see in HA that new 2N firmware exists and install it without opening the device web UI.

Current: the firmware version is only the device sw_version (swVersion from /api/system/info). There is no update entity and no way to install firmware from HA.

Findings (TASK-50, docs/API_REFERENCE.md section "Firmware update"): the device web UI does not ask the device to update itself. The browser queries the public 2N update server (GET https://update.2n.cz/hip/<firmwarePackage>/<newest|lts|early>/?current_ver=<swVersion>&ui_lang=en; 200 = newer version with files[].url, checksum (SHA-256), version, changelog.md, type; 204 = up to date), downloads the .bin and installs it through the public HTTP API: PUT /api/firmware (multipart blob-fw -> fileId, version, downgrade, note) and then /api/firmware/apply?fileid=<fileId> (GET or POST), after which the device reboots. Both need the System Control privilege, which the integration API account can have. The device's own branch / auto-update settings (AutoUpdate.UpdateServer.*) are readable only via the full config backup and writable only with a web session, so the integration keeps its own channel option and never reads or changes them.

Expected: an HA update entity per intercom with the installed and latest version and release notes, and an Install action that does what the web UI does (HA downloads from the 2N update server, verifies the checksum, uploads, applies, waits for the reboot). The channel (Active track / LTS / Beta) is chosen in the integration options. Install only happens on explicit user action; downgrades are never applied.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 New update platform: one entity per config entry, extends TwoNIntercomEntity, device_class firmware, entity_category config, supported features INSTALL | PROGRESS | RELEASE_NOTES; no entity when /api/system/info has no firmwarePackage (debug log); unit test
- [ ] #2 installed_version equals swVersion from /api/system/info; unit test
- [ ] #3 latest_version comes from GET https://update.2n.cz/hip/<firmwarePackage>/<track>/?current_ver=<swVersion>&ui_lang=en via the HA shared client session (never the device session, no credentials sent); 204 means latest_version = installed_version; a failed or malformed check keeps the last known value, is logged once per failure streak and never breaks the coordinator or the log subscription; unit test
- [ ] #4 release_summary (truncated to the HA limit) and async_release_notes come from changelog.md, newest version first; unit test
- [ ] #5 Install downloads files[type=firmware].url streamed to a temp file (not fully in memory), aborts before upload when the SHA-256 does not match checksum, uploads it with PUT /api/firmware (blob-fw), rejects the file (/api/firmware/reject) when the result has downgrade=true or a version different from latest_version, otherwise calls /api/firmware/apply?fileid=<fileId>; never installs automatically; unit test with a mocked API
- [ ] #6 in_progress is true during install with update_percentage for the download and upload phases (None while the device installs and reboots); after the reboot the entity waits until /api/system/info swVersion equals the target version (timeout -> translated error) and installed_version updates; unit test
- [ ] #7 Device errors (codes 7-10 missing System Control privilege, 12 invalid file, 14 file not found, 18 update already in progress, 19 version below minimum) and download/checksum failures raise a translated HomeAssistantError, reject any pending fileId and leave no partial in_progress state; unit test
- [ ] #8 New option firmware_channel (active_track -> newest, lts -> lts, beta -> early; default active_track) in entry.options with strings.json and en/de/cs translations; it only selects the update server track, the device AutoUpdate settings are not read or written; unit test
- [ ] #9 Version check runs on its own interval (not every coordinator poll), once after setup and on homeassistant.update_entity; timestamps tz-aware; unit test
- [ ] #10 PLATFORMS, strings.json, translations/*.json, icons.json, diagnostics (versions and channel only, no URLs with tokens, no secrets) updated together
- [ ] #11 E2E read-only check: HA update entity installed_version equals swVersion from the 2N API, and latest_version equals the update server answer for the same firmwarePackage/track (installed_version on 204)
- [ ] #12 E2E install test exists, is marked @pytest.mark.firmware and is excluded from default and wip runs (like relays); it runs only on Jan's explicit request
- [ ] #13 README '2N API Endpoints Used' and docs/API_REFERENCE.md updated
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files: new custom_components/2n_intercom/update.py; __init__.py (PLATFORMS); api.py: async_firmware_upload(path) -> PUT /api/firmware multipart blob-fw streamed from file, async_firmware_apply(file_id), async_firmware_reject(file_id) on the existing dual-auth request path with the usual 2N error parsing; new small module (e.g. firmware.py) for the update server client: check(package, track, current_ver, lang) -> parsed result or None on 204, download(url, dest, progress_cb) with SHA-256 verification, using homeassistant.helpers.aiohttp_client.async_get_clientsession(hass) - never the device session with the Digest middleware; coordinator.py: keep firmwarePackage from get_device_info, no other change to event handling; const.py: CONF_FIRMWARE_CHANNEL, default, track map, FIRMWARE_CHECK_INTERVAL (e.g. 6 h), FIRMWARE_UPDATE_SERVER_URL, reboot timeout; config_flow.py: options field; strings.json, translations/{en,de,cs}.json, icons.json; diagnostics.py; tests/test_update.py + test_api firmware methods + stubs for UpdateEntity/UpdateEntityFeature in tests/_stubs.py; e2e/tests/test_firmware.py (read-only check + install test marked firmware) using e2elib/twon.py and a direct update server call (stays independent of api.py).
Install flow (mirror of the device web UI, docs/API_REFERENCE.md "Firmware update"): check -> download to a temp file in a executor-safe way -> verify checksum -> PUT /api/firmware -> validate result (downgrade false, version == latest) else reject -> apply -> mark in_progress, let the coordinator/log listener reconnect through its existing backoff -> poll /api/system/info until swVersion == target or timeout.
Must not change: dual Basic/Digest auth in api.py; event-driven state and ring detection; entry.data vs entry.options split; no secrets in logs/diagnostics; broad except only for logged degradation.
If excluding the firmware marker needs changes in protected paths (e2e/scripts, e2e/ci), split that part into a separate @copilot-mac manual-path task.
<!-- SECTION:PLAN:END -->
