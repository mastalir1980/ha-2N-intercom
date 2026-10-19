---
id: TASK-51
title: >-
  Add a firmware update entity that shows when new 2N firmware is available and
  links to the device web UI
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-17 09:27'
updated_date: '2026-10-19 18:41'
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
- [x] #1 New update platform: one entity per config entry, extends TwoNIntercomEntity, device_class firmware, entity_category config, supported features RELEASE_NOTES only (no INSTALL, no PROGRESS); no entity when /api/system/info has no firmwarePackage (debug log) [unit]
- [x] #2 installed_version equals swVersion from /api/system/info and follows it after a coordinator refresh [unit]
- [x] #3 latest_version comes from GET https://update.2n.cz/hip/<firmwarePackage>/<track>/?current_ver=<swVersion>&ui_lang=en via the HA shared client session (never the device session, no credentials sent); 204 means latest_version = installed_version; a failed or malformed check keeps the last known value, is logged once per failure streak and never breaks the coordinator or the log subscription [unit]
- [x] #4 A 200 answer whose type does not match the selected track (newest needs stable=true, lts needs lts=true, early needs stable=false) is treated as up to date, like the device web UI [unit]
- [x] #5 release_summary (truncated to the HA limit) and async_release_notes come from changelog.md, newest version first [unit]
- [x] #6 release_url is the device web UI <protocol>://<host>[:<port> only when not the protocol default]/ built from entry.data, never with credentials; the same URL is set as configuration_url in the device info, so the HA device page links to the intercom [unit]
- [x] #7 New option firmware_channel (active_track -> newest, lts -> lts, beta -> early; default active_track) in entry.options with strings.json and en/de/cs translations; the device AutoUpdate settings are not read or written [unit]
- [x] #8 The version check runs on its own interval (not every coordinator poll), once after setup and on homeassistant.update_entity; timestamps tz-aware [unit]
- [x] #9 PLATFORMS, strings.json, translations/*.json, icons.json and diagnostics (versions and channel only, no URLs with tokens, no secrets) updated together [unit]
- [x] #10 The integration calls no firmware endpoint of the device (/api/firmware, /api/firmware/apply, /api/firmware/reject, /api/autoupdate/*); a unit test guards it [unit]
- [x] #11 E2E read-only check: HA update entity installed_version equals swVersion from the 2N API, latest_version equals the update server answer for the same firmwarePackage/track (installed_version on 204), and the host in release_url equals the configured intercom host [e2e]
- [x] #12 README documents the update entity, the channel option and that updating happens in the device web UI; README '2N API Endpoints Used' and docs/API_REFERENCE.md updated [unit]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add the read-only firmware response parser and shared credential-free device web UI URL helper; retain firmwarePackage and expose safe firmware diagnostics.
2. Add the update platform with RELEASE_NOTES only, installed version from the device coordinator, independent six-hour checks via the HA shared session, forced refresh, track filtering, cached results and failure-streak logging.
3. Wire firmware_channel options, platform registration, strings, all translations and icons without changing device authentication or event handling.
4. Add unit coverage for every unit criterion and an independent read-only E2E comparison; update README and API reference.
5. Run the required local Python gates, record implementation evidence without checking criteria or finalizing status, and commit locally on the current task branch.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-19: rescoped by Jan - v1.5.0 only informs (versions, release notes, link to the device web UI). Install moved to the v1.6.0 task that uses the device's built-in updater (GET /api/autoupdate/updatefw, 2N OS >= 3.3).

Implemented the informational firmware update platform and public catalog parser. The entity supports RELEASE_NOTES only, uses the HA shared client session, checks before initial add and on its independent six-hour timer/manual refresh, and cancels its timer on removal. Failed checks retain the previous version and notes and log once per failure streak. No device firmware endpoints or downloads were added; device authentication and log-event handling are unchanged.
System info is retained from initial setup without a duplicate startup request and refreshed on subsequent coordinator polls so installed firmware changes are visible without reloading. The shared web UI helper supplies credential-free release_url and configuration_url with protocol-default ports omitted. Firmware channel is an options-only preference; device AutoUpdate settings remain untouched.
Evidence for review (criteria intentionally left unchecked):
AC #1: tests/test_update.py setup/metadata and missing-package debug-log cases.
AC #2: test_installed_version_follows_real_coordinator_refresh and test_device_info_failure_preserves_installed_version.
AC #3: public GET parameter/session assertions, 204 handling, malformed/network failures, cached-result recovery and failure-streak logging tests; ring events and device refresh continue after a catalog failure.
AC #4: exact-boolean track matching and mismatch-as-current tests for newest/lts/early.
AC #5: newest-first full markdown and 255-character summary tests.
AC #6: shared device/release URL assertions for HTTP/HTTPS defaults, nondefault ports and IPv6, independent of options and without credentials.
AC #7: options flow tests cover active_track default and saving all three channels; all translated selectors are checked.
AC #8: lifecycle test covers initial update-before-add, independent six-hour registration, no checks during coordinator polls, scheduled/manual checks, timezone-aware timestamps and timer removal; concurrent checks are serialized.
AC #9: setup includes update once; translation/icon wiring and firmware diagnostics tests cover versions/channel only.
AC #10: AST regression guard checks all integration Python string literals for prohibited device firmware/autoupdate endpoints.
AC #11: added e2e/tests/test_firmware.py comparing HA installed/latest versions with the independent device client/public catalog, forced update_entity, release host and device configuration link. Execution is pending the orchestrated e2e-pi check; no E2E commands or device/HA connections were run on this VM.
AC #12: README, API reference and architecture docs updated; documentation contract test covers the read-only update behavior and catalog endpoint.
Local gates on Python 3.12: all 704 unit tests passed; validate.py passed; integration modules and the new E2E module compile; git diff --check passed. Existing unrelated API-test coroutine warnings were not modified. Task remains In Progress for the independent review and Pi E2E gate.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented by the headless coder. Checks green on f77a39c84 after 0 fix round(s): validate=pass, validate=pass, e2e-pi=pass. PR: https://github.com/mastalir1980/ha-2N-intercom/pull/93. Done takes effect when the PR is merged.
AC #1: tests/test_update.py FirmwareEntityTests.test_setup_one_informational_entity_using_shared_session asserts a single entity, device class firmware, entity category config and features == RELEASE_NOTES only; test_missing_package_skips_entity_with_debug_log covers no entity plus debug log. update.py extends TwoNIntercomEntity. Full suite (704 tests) passes. (proven)
AC #2: test_installed_version_follows_real_coordinator_refresh drives a real coordinator refresh and checks installed_version follows swVersion; test_device_info_failure_preserves_installed_version covers refresh failure. coordinator._async_update_data now refreshes system_info after the first poll. (proven)
AC #3: FirmwareCatalogTests.test_public_get_has_only_catalog_parameters_and_no_credentials checks URL, current_ver/ui_lang params and no auth; the entity setup test checks the shared HA session is used. Tests cover 204 -&gt; installed_version, malformed/network/HTTP errors, test_failure_streak_logs_once_keeps_cache_and_recovers, test_malformed_failed_check_preserves_last_successful_result and test_failure_does_not_stop_device_refresh_or_ring_events. (proven)
AC #4: FirmwareCatalogTests.test_track_matching_requires_exact_boolean_flags and FirmwareEntityTests.test_204_and_mismatched_tracks_clear_obsolete_release_notes cover newest/lts/early mismatches as up to date. firmware.py uses release_type[flag] is (track != 'early'). (proven)
AC #5: test_notes_are_newest_first_and_not_limited and test_200_versions_notes_and_summary_limit verify the reversed (newest-first) changelog, async_release_notes and release_summary truncated to 255 characters. docs/API_REFERENCE.md confirms the server array is ascending. (proven)
AC #6: test_shared_web_ui_url_handles_defaults_nondefault_ports_and_ipv6 asserts release_url equals configuration_url in device info, default port omitted, non-default port included, no credentials. web.py builds the URL from entry.data only. (proven)
AC #7: const.py defines CONF_FIRMWARE_CHANNEL, default active_track and the track map; tests/test_config_flow.py covers the options field default and saving all three channels; test_selected_option_maps_all_channels_not_entry_data covers the map from entry.options; test_firmware_platform_translations_and_icons_are_wired checks strings.json and en/de/cs. No device AutoUpdate endpoint is called. (proven)
AC #8: test_separate_interval_initial_check_manual_refresh_and_cleanup checks update_before_add, the FIRMWARE_CHECK_INTERVAL timer, no checks on coordinator polls, manual refresh, tz-aware timestamp (dt_util.utcnow) and timer removal; test_concurrent_checks_are_serialized. (proven)
AC #9: __init__._get_platforms appends update (tests/test_init.py updated by adding update to the expected platforms, not weakened); translation/icon wiring test; tests/test_diagnostics.py covers the firmware section, which holds only installed/latest version and channel. (proven)
AC #10: FirmwareReadOnlyContractTests.test_integration_has_no_device_firmware_endpoint_literals scans every integration .py string constant (AST) for /api/firmware and /api/autoupdate. Manual diff review also finds no such calls. (proven)
AC #11: e2e/tests/test_firmware.py compares HA installed_version with twon.system_info swVersion, latest_version with an independent direct catalog call (installed on 204 or track mismatch), release_url host with the configured host and the device configuration_url. It does not touch relays or device firmware endpoints. The orchestrator reports the e2e-pi check green on this head. (proven)
AC #12: README.md, docs/API_REFERENCE.md and docs/ARCHITECTURE.md are updated; FirmwareReadOnlyContractTests.test_firmware_user_documentation_covers_read_only_behavior asserts the README Firmware updates section (firmware_channel, device web UI, six hours), update.2n.cz in the endpoints section, and firmware_channel/RELEASE_NOTES in the API reference. (proven)
<!-- SECTION:FINAL_SUMMARY:END -->
