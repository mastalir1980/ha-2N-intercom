---
id: TASK-50
title: >-
  Investigate how to trigger the intercom's built-in firmware update from the 2N
  update server over the API
status: Done
assignee:
  - '@claude'
created_date: '2026-10-17 09:27'
updated_date: '2026-10-18 13:31'
labels:
  - firmware
  - investigation
milestone: m-0
dependencies: []
references:
  - docs/ROADMAP-NAVRH.md
  - docs/API_REFERENCE.md
  - custom_components/2n_intercom/coordinator.py
  - >-
    https://wiki.2n.com/hip/hapi/latest/en/5-prehled-funkci-http-api/5-2-api-firmware
priority: medium
type: spike
ordinal: 57000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: roadmap item D1 (docs/ROADMAP-NAVRH.md) - an HA update entity for the intercom firmware. The feature task depends on knowing how the device's own online update is triggered.

Facts: the integration reads only swVersion from /api/system/info (coordinator.py get_device_info -> device sw_version). The public HTTP API firmware group only has PUT /api/firmware (multipart blob-fw upload, privilege System Control), /api/firmware/apply and /api/firmware/reject; no documented endpoint checks the 2N update server or starts an online update. Fw 3.x web UI (System > Firmware) has 'Server update' against the official 2N update server with a branch (Active Track / LTS / Beta) and a check interval, a 'Check for Updates' button and a Firmware Update Log.

Hypothesis (Jan): the device downloads and installs firmware by itself; the integration only needs to trigger it through an API call, probably the one the web UI uses.

Questions to answer: (1) which requests the web UI sends for 'Check for Updates' and for starting the update - method, path, params, auth scheme, required privilege, response incl. available version and release notes; (2) whether they work with the HTTP API account (Digest/Basic) or only with a web UI session; (3) where the branch and check interval are stored and whether they can be read and written over the API; (4) the states during download/install/reboot and how to tell success or failure; (5) the minimum firmware and differences between fw 2.50 and fw 3.x.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Requests for check, available version and update start are documented in docs/API_REFERENCE.md (new section 'Firmware update') with request/response examples, without secrets, host names or the exact device model/build
- [x] #2 Documented whether the branch (Active Track / LTS / Beta) can be read and set over the API
- [x] #3 Documented update states, reboot behaviour and how success/failure is detected
- [x] #4 Go/no-go decision recorded; the feature task has a concrete implementation plan and its on-hold label removed (or it is closed with the reason)
- [x] #5 No firmware is installed on the E2E intercom during the investigation without Jan's explicit approval in the conversation
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Read the firmware/auto-update code in both device web UIs (new React UI /new/ and legacy UI /) instead of recording clicks - same answer, no risk of starting an update.
2. Try the internal read paths (POST /api/system/db/values, /ajax) and GET /api/config with the integration API account (Digest/Basic), read-only.
3. Call the public 2N update server directly for all three tracks.
4. Read the 2N HTTP API docs for /api/firmware, apply, reject.
5. Write docs/API_REFERENCE.md "Firmware update", decide go/no-go, update TASK-51.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Findings (details in docs/API_REFERENCE.md "Firmware update"):
- Hypothesis "the device downloads and installs by itself, the UI only triggers it" is not true for the UI button: the browser checks https://update.2n.cz/hip/<firmwarePackage>/<newest|lts|early>/?current_ver=<swVersion>&ui_lang=<lang>, downloads files[].url and installs via the public PUT /api/firmware + /api/firmware/apply. Same in the new and legacy UI.
- Update server verified from the Mac: 204 for an up-to-date version on all tracks, 200 with files/checksum/version/changelog.md/type for an older current_ver. firmwarePackage is in /api/system/info (fw 3.x).
- Branch/interval live in AutoUpdate.UpdateServer.* (UpgradeMode 1/2/3 = newest/lts/early) and AutoUpdate.UpdateSource. With the API account they are readable only in the full GET /api/config backup; POST /api/system/db/values returns code 9 "authorization required" with Digest and Basic, /ajax returns 400 - both need a web session. Writing needs a web session too. autoupdate.updatefirmware (/ajax) is the auto-provisioning source, not the 2N update server.
- API account has System Control (GET /api/config 200), which PUT /api/firmware and apply need.
- No firmware was uploaded or applied on the E2E intercom (AC #5). Upload/apply response and reboot behaviour are taken from the UI code and 2N docs; TASK-51 E2E install test verifies them on the device on Jan's request.
- fw 2.50: legacy UI module uses the same server and endpoints; not verified on a 2.50 device (hypothesis).
Decision: GO - TASK-51 mirrors the web UI flow (HA checks the update server, downloads, verifies SHA-256, uploads, applies); channel is an integration option, device AutoUpdate settings untouched. TASK-51 rewritten with plan and criteria, on-hold removed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Spike done without touching the device firmware: the web UI checks the public 2N update server from the browser and installs through the documented PUT /api/firmware + /api/firmware/apply, so the integration can do the same with its API account (System Control). Branch/auto-update settings are web-session only, so the channel becomes an integration option. Verified by reading both web UI bundles, read-only calls with the API account (system/info, config, db/values -> code 9, ajax -> 400) and direct update server calls (200/204). Documented in docs/API_REFERENCE.md "Firmware update"; TASK-51 has the concrete plan and is no longer on hold.
<!-- SECTION:FINAL_SUMMARY:END -->
