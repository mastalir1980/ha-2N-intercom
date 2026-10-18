---
id: TASK-15
title: >-
  Clarify credential fields in the options flow and point users to Reconfigure
  for API credentials
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-11 18:43'
updated_date: '2026-10-18 16:14'
labels:
  - config-flow
  - ux
  - security
milestone: m-0
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
- [x] #7 Unit tests cover RTSP password masking and keep/clear behaviour; full unit suite and `validate.py` green; E2E wip run green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Remaining work only (code is already on main; no integration code change is expected):
1. Read 'backlog instructions task-execution' and 'task-finalization'.
2. Get E2E evidence on current origin/main (c28e833 or later), read-only, NO relays:
   - First check the latest report on the Pi (the TASK-21 run on origin/main that Jan confirmed green): if its deployed_sha is c28e833+ and pytest.log shows test_40_options_flow.py (incl. the rtsp_password masking assertions) and test_00_setup.py::test_no_integration_errors_in_log passed, use it as evidence.
   - Otherwise run 'bash e2e/e2e.sh run --ref origin/main' from the main working tree.
3. If test_no_integration_errors_in_log fails because the config-flow protocol auto-detection logs ERROR lines (verified-HTTPS probe against the self-signed cert), do NOT fix it inside TASK-15: triage it as a separate bug per e2e/agent/triage.md (type bug, label e2e) and tell Jan; TASK-15 then stays In Progress.
4. If the run is green: append the report id, deployed_sha and test counts to the notes, check AC #7, write the final summary, set status Done.
5. Commit only the backlog change on branch task-15-finalize; Jan merges. Do not run relay tests, reset-entry, or touch production HA (8123).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented on branch task-14-15-options-flow-ux (commit 6ac5ad2). RTSP password is a password-type TextSelector, never pre-filled; empty on submit keeps the stored password, clearing the username removes the credential pair. Unit evidence: OptionsFlowRtspCredentialsTests (5 tests: masking, keep, replace, clear, stays-empty) — 467 tests green, validate.py green. E2E test_40 additionally asserts the password selector type and no suggested_value on real HA (passed 21:37). AC#7 pending: a full e2e wip run is not yet green end-to-end because a parallel session (branch task-4-8-9-access-control-ring-snapshot) shares this checkout and the staging HA — it switched the checkout mid-run (wrong ref deployed) and its config-flow runs leave expected auto-detect ERROR lines (verified-HTTPS rung against a self-signed cert) that fail test_no_integration_errors_in_log in fresh-bootstrap windows. Not caused by this change; needs one clean wip run after the parallel session settles.

2026-10-12 status (Claude): the implementation is merged into main (e36c496, TASK-21.4); the parallel-session problem from the note above no longer applies (single checkout, branches consolidated). Verified on main c28e833 with Python 3.12.15: full unit suite 563 OK incl. all 5 OptionsFlowRtspCredentialsTests, validate.py OK. ACs 1-6 stay checked. Only AC #7's E2E part is open: one clean E2E run on current main with evidence recorded. Side finding, not part of this task: running tests/test_config_flow.py on its own (unittest -k OptionsFlowRtspCredentialsTests) fails with ModuleNotFoundError for custom_components.2n_intercom.coordinator; it only passes inside the full discover run (import-order dependency on _stubs).

2026-10-12 finalization attempt (Copilot): current HEAD and origin/main are c28e833f733f0eef059ca6d0a7297c6f0d211097. Python 3.14.3: full unit suite passed (563 tests), validate.py passed, and py_compile passed for custom_components/2n_intercom/*.py. E2E evidence remains blocked: two read-only SSH attempts to the configured staging Pi timed out; the staging HA manifest request on port 8124 also timed out. No qualifying current-main report exists locally (the latest local directory 20261012-133233 has no summary.json or pytest.log). A new E2E pipeline run was not started while staging was unreachable. AC #7 remains unchecked and status remains In Progress. No integration code, staging deployment, relay, production HA, branch, or commit changes were made. Next prerequisite: restore staging connectivity or supply the TASK-21 current-main report with summary.json, pytest.log and test counts.

2026-10-12 report supplied by Jan: Pi report 20261012-144418 is reported passed, ref origin/main, deployed_sha c28e833, unit suite 452/452 plus validate.py green, E2E 11 passed and 2 skipped (SIP and relays). These counts are user-reported, not independently read from the report. SSH from this checkout still times out, and the report is not present locally. The remaining implementation plan explicitly requires evidence that test_40_options_flow.py (RTSP password masking assertions) and test_00_setup.py::test_no_integration_errors_in_log both passed. The supplied summary does not identify those tests; the reported 452 unit tests also differs from the verified current-main suite of 563 tests, so the Pi test checkout may be older even though deployed integration SHA is current. Need pytest.log or junit.xml from this report before checking AC #7 or setting Done. Nightly state files require no changes and were left untouched.

2026-10-12 attached JUnit evidence inspected: report 20261012-144418 contains 13 test cases, 0 failures, 0 errors, 2 skipped, hence 11 passed. tests.test_00_setup::test_no_integration_errors_in_log passed. No tests.test_40_options_flow::test_options_flow_last_step_and_back_navigation test case is present at all; RTSP password masking was not verified by this run. Skips are SIP registration disabled and manual relay test disabled. In e2e/run.sh, --ref selects the integration deployment only; unittest and pytest use the runner's working-tree test files. A passed deployment of c28e833 does not establish that the Pi ran its corresponding test suite. AC #7 remains unchecked, TASK-15 remains In Progress. Need inspect the Pi checkout status before updating it or rerun from the current main checkout on the Mac with staging connectivity; no integration changes are needed.

2026-10-12 checkout clarification: Jan reports the current Pi checkout is main at c28e833, synchronized with origin/main, with only an unrelated untracked deploy_test.sh artifact. Locally verified with git ls-tree that c28e833 tracks e2e/tests/test_40_options_flow.py, e2e/tests/test_50_access_control.py and the current tests/test_config_flow.py; there are no working-tree differences in these tests. Therefore a reset or pull to the same commit is not required. The cause of the earlier incomplete test collection remains unconfirmed; do not equate the current Pi checkout state with the test files used by report 20261012-144418. Rerun the read-only pipeline from the confirmed current Pi main checkout and inspect its new JUnit results for test_40 and the integration-log check. Leave deploy_test.sh untouched and do not run it (it is a production deployment artifact outside TASK-15).

2026-10-15 (Claude): moved to To Test under the new status scheme: AC #1-#6 verified, only AC #7's E2E part is left (one clean e2e run on current main, e.g. in the v1.5.0 release test).

AC evidence (tester review 2026-10-18): #1-#3 strings.json + en/de/cs; #4 OptionsFlowRtspCredentialsTests; #5 no API credential fields in options flow. #6 clarity = Jan. #7 E2E part missing: no E2E assertion for RTSP masking exists.

AC evidence (tester review 2026-10-18): #1-#3 strings.json + en/de/cs; #4 OptionsFlowRtspCredentialsTests; #5 no API credential fields in options flow; #6 clarity reviewed by Jan; #7 unit suite + validate green, RTSP masking verified manually by Jan (no automated E2E assertion exists).
<!-- SECTION:NOTES:END -->
