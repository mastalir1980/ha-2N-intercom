---
id: TASK-15
title: >-
  Clarify credential fields in the options flow and point users to Reconfigure
  for API credentials
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-11 18:43'
updated_date: '2026-10-11 19:47'
labels:
  - config-flow
  - ux
  - security
dependencies: []
references:
  - custom_components/2n_intercom/strings.json
  - custom_components/2n_intercom/config_flow.py
  - README.md
  - docs/API_REFERENCE.md
priority: medium
type: enhancement
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Feedback from the owner while using the options flow (Configure) on HA staging:

1. The RTSP username help text is not understandable: "Username for the 2N RTSP streaming service (configured separately from the HTTP API in the device web UI under Services > Streaming)". It does not say the field is optional, what it is used for, what happens when it is empty, or where exactly the account is created on the intercom.
2. The user cannot find where to change the HTTP API credentials. They are intentionally NOT part of the options flow: connection identity (host, port, protocol, username, password, TLS) lives in `entry.data` and is changed through the Reconfigure flow (integration card ⋮ → Reconfigure) or reauth. This split is an architecture rule (see CLAUDE.md "Config split") and must stay. The problem is discoverability: nothing in the Configure dialog says where API credentials are, and the setup flow labels them only as "Username"/"Password", so having a second pair called "RTSP username/password" in Configure is confusing.

Also found during review: the RTSP password field in the camera options step is a plain `str` with `suggested_value`, so the saved RTSP password is shown in clear text when the dialog is opened.

Facts for the help text (from README "RTSP authentication" and docs/API_REFERENCE.md): the 2N RTSP server has its own user database (intercom web UI: Services → Streaming → RTSP Server → User Database), there is no fallback from API credentials, and without RTSP credentials the integration never tries RTSP and uses MJPEG instead. Related: TASK-14 (options flow navigation).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 RTSP username/password help text states in plain language: the fields are optional, they are only used for the RTSP (H.264) video stream, where on the intercom the RTSP account is created, that the API account does not work here, and that leaving them empty means MJPEG is used
- [x] #2 The Configure dialog (first options step description) tells the user that IP address, port and API username/password are changed via ⋮ → Reconfigure, not here
- [x] #3 API credential fields in the setup, reconfigure and reauth flows are labelled as API credentials (e.g. "API username"/"API password") with help text naming the intercom web UI section where the HTTP API account is managed, so they are clearly distinct from the RTSP pair
- [x] #4 The RTSP password field is masked (password-type text selector) and the stored value is not displayed in clear text when the options dialog is reopened; leaving it unchanged keeps the stored password, and clearing it is still possible
- [x] #5 Connection identity stays in `entry.data` and is not added to the options flow
- [x] #6 All changed texts are updated in `strings.json` and `translations/{en,de,cs}.json` (Czech and German reviewed for clarity, not machine-literal); README options table and RTSP section match the new wording
- [ ] #7 Unit tests cover RTSP password masking and keep/clear behaviour; full unit suite and `validate.py` green; E2E wip run green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Rewrite RTSP username/password help texts: fields are optional, used only for the RTSP (H.264) stream, account is created on the intercom under Services -> Streaming -> RTSP Server -> User Database, the HTTP API account does not work there, empty means MJPEG is used.
2. Options device-step description tells the user that IP address, port and API credentials are changed via the integration card menu -> Reconfigure.
3. Label credentials in the user, reconfigure and reauth_confirm steps as 'API username'/'API password' with help text naming the intercom web UI section (Services -> HTTP API -> Accounts); add the currently missing reauth_confirm step strings.
4. RTSP password field becomes a password-type TextSelector with no suggested_value, so the stored password is never shown in clear text; empty on submit keeps the stored password, and emptying the username removes the whole RTSP credential pair (clearing path, documented in help text).
5. Connection identity stays in entry.data; nothing added to the options flow (existing test guards this).
6. Update strings.json and translations/{en,de,cs}.json with reviewed Czech and German; README options table and RTSP section updated to match.
7. Unit tests for password masking and keep/clear behaviour; full unit suite, validate.py and e2e wip run green.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented on branch task-14-15-options-flow-ux (commit 6ac5ad2). RTSP password is a password-type TextSelector, never pre-filled; empty on submit keeps the stored password, clearing the username removes the credential pair. Unit evidence: OptionsFlowRtspCredentialsTests (5 tests: masking, keep, replace, clear, stays-empty) — 467 tests green, validate.py green. E2E test_40 additionally asserts the password selector type and no suggested_value on real HA (passed 21:37). AC#7 pending: a full e2e wip run is not yet green end-to-end because a parallel session (branch task-4-8-9-access-control-ring-snapshot) shares this checkout and the staging HA — it switched the checkout mid-run (wrong ref deployed) and its config-flow runs leave expected auto-detect ERROR lines (verified-HTTPS rung against a self-signed cert) that fail test_no_integration_errors_in_log in fresh-bootstrap windows. Not caused by this change; needs one clean wip run after the parallel session settles.
<!-- SECTION:NOTES:END -->
