---
id: TASK-50
title: >-
  Investigate how to trigger the intercom's built-in firmware update from the 2N
  update server over the API
status: To Do
assignee: []
created_date: '2026-10-17 09:27'
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
- [ ] #1 Requests for check, available version and update start are documented in docs/API_REFERENCE.md (new section 'Firmware update') with request/response examples, without secrets, host names or the exact device model/build
- [ ] #2 Documented whether the branch (Active Track / LTS / Beta) can be read and set over the API
- [ ] #3 Documented update states, reboot behaviour and how success/failure is detected
- [ ] #4 Go/no-go decision recorded; the feature task has a concrete implementation plan and its on-hold label removed (or it is closed with the reason)
- [ ] #5 No firmware is installed on the E2E intercom during the investigation without Jan's explicit approval in the conversation
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Jan opens the E2E intercom web UI in Chrome; Claude records the network requests (DevTools) while clicking 'Check for Updates' only - not the update itself.
2. Replay the recorded check request with curl from the Mac using the API account from e2e/.env (never print the values) to see if the API account is enough.
3. Look for the branch/interval settings in the requests and in GET /api/config.
4. Write the findings into docs/API_REFERENCE.md and finalize the plan of the feature task.
<!-- SECTION:PLAN:END -->
