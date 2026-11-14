---
id: TASK-12
title: >-
  Device rejects API calls (codes 7, 10, 12) but the integration reports success
  with empty entities
status: Done
assignee:
  - '@claude'
created_date: '2026-10-11 16:04'
updated_date: '2026-11-14 00:28'
labels:
  - e2e
  - api
  - repairs
milestone: m-3
dependencies: []
priority: high
type: bug
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: when the device refuses requests, the integration looks healthy while entities stay empty or dead. Two reports:
- 2026-10-11, E2E intercom fw 3.x: every call answered code 7 "invalid connection type" (HTTP was disabled on the device). The connection part is fixed since 1.4.0 (verified HTTPS first); see implementation notes for the history.
- 2026-10-23, issue #105 (2N IP Uni, fw 2.50): /api/switch/* and /api/system/caps answer code 10 (insufficient privileges); the Uni account offers only Phone/Calls and Keypad privileges. Only WARNING lines in the log.

Current behaviour (fact): _async_get_result_dict() (api.py) returns {} on a 2N error body (success=false) and callers log a WARNING; the coordinator refresh counts this as success, so entities show default/empty state and the user gets no hint what to change on the device.

Expected behaviour: the user sees what is wrong and how to fix it in Home Assistant: entities that depend on a refused call are unavailable (not empty), and a Repair issue names the missing privilege group or the refused connection type with the fix on the device. Expected device limits (feature not present on this model, e.g. io/* code 1 on a device without inputs) are not errors.

Open before ready (analysis): mapping of 2N codes to user messages (7, 8-10 privileges, 12, 1 not supported), which calls are essential (system/info, call/status, log/subscribe) vs optional (switch, io, camera, directory), and how this fits the existing reauth path (three failed polls trigger reauth, 1.5.0).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 When every essential call is refused with a 2N error body, the coordinator refresh fails (entities unavailable) instead of reporting success with empty data [unit]
- [x] #2 A refused optional feature call (switch, io, camera, directory) with a privilege error (codes 8-10) creates one translated Repair issue naming the missing privilege group; the issue clears when the call succeeds [unit]
- [x] #3 Code 1 (not supported) on an optional feature disables only that feature, with no Repair issue and no repeated WARNING [unit]
- [x] #4 strings.json and en/de/cs translations for the new Repair issues; validate.py green [unit]
- [x] #5 E2E: with the read-only E2E account no Repair issue is open and all entities are available (HA says X <-> 2N API says X) [e2e]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Decisions (analysis 2026-11-13):
- Essential calls: /api/system/info, /api/phone/status, /api/call/status. Optional features by path prefix: switch (/api/switch/), io (/api/io/), camera (/api/camera/), directory (/api/dir/). /api/system/caps and /api/log/* are neither (they degrade as today).
- Code mapping: 8, 9, 10 on an optional feature = missing privilege -> Repair issue. Code 1 on an optional feature = not on this model -> feature switched off quietly. Code 7 and everything else only matter through the essential rule (refresh fails with the device error in the message).
- Reauth path is unchanged: only HTTP 401 counts as an auth failure. A 2N error body never triggers reauth.

Steps:
1. api.py: the client remembers the last 2N refusal per path (device_errors); a success on the path clears it. A repeated identical refusal is logged at DEBUG, the first at WARNING (code 1 on an optional feature at INFO).
2. coordinator.py: after a poll, raise UpdateFailed when all three essential paths are refused; create/delete one Repair issue per feature (api_privilege_missing_<entry_id>_<feature>, privilege group as placeholder); skip switch and io polling when the feature answered code 1.
3. __init__.py: delete the issues on unload.
4. strings.json + en/de/cs: issues.api_privilege_missing.
5. Unit tests in tests/test_api.py, test_coordinator.py, test_init.py. E2E: no open Repair issue of the integration, all entities available.
Must not change: dual auth, event-driven ring detection, the basic_auth_refused issue, behaviour of fake/legacy API objects without device_errors.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Recurred 2026-10-11 (report 20261011-180751), sha ade47bc, HA 2026.9.0, device E2E intercom fw 3.x. Failed: test_device_accepts_integration_requests (code=7 'invalid connection type' on phone/switch/io/call status, log/subscribe, system/switch/io caps) and test_camera_snapshot_is_jpeg (camera_proxy -> 500; container log: camera/snapshot rejected code=7). ha_system_log count=36 WARNING at api.py:144. system/info still succeeds (device_registry test passed). Unchanged from first occurrence (20261011-175902).

2026-10-11 (Jan): the intercom's HTTP API is configured HTTPS-only — plain HTTP is disabled on the device. This explains code 7 'invalid connection type': the config entry created by ade47bc settled on plaintext HTTP. The secure-by-default work (TASK-1: verified HTTPS -> unverified HTTPS -> HTTP last) is the expected fix for the code-7 part; verify with 'bash e2e/e2e.sh reset-entry' + 'bash e2e/e2e.sh wip'. The silent-failure part (coordinator success with 100% rejected calls) remains a separate bug either way. Also consider: when the device rejects HTTP with code 7, the config flow should fall through to HTTPS instead of accepting the entry.

Recurred 2026-10-11 (report 20261011-201113), sha ade47bc-dirty, HA 2026.9.0, device E2E intercom fw 3.x. NEW DATA POINT: this run deployed the WORKTREE (ref=worktree, ade47bc-dirty) so the security/secure-by-default-connection changes WERE live (previous two occurrences deployed committed ade47bc without them) — code 7 still occurs on every request, so the secure-by-default branch does not resolve this. Failed: test_device_accepts_integration_requests (code=7 'invalid connection type' on phone/switch/io/call status, log/subscribe, system/switch/io caps) and test_camera_snapshot_is_jpeg (camera_proxy -> 500; container log camera/snapshot rejected code=7). ha_system_log count=36 WARNING at api.py:145. system/info still succeeds (device_registry test passed).

2026-10-11 verification: with the working-tree secure-by-default changes (TASK-1, not yet committed) + reset-entry + new API account, report e2e/reports/20261011-201937 is green: test_device_accepts_integration_requests and test_camera_snapshot_is_jpeg pass, zero 'rejected by device' warnings. => code-7 part is fixed by TASK-1 once merged. Still open here: the silent-failure part (AC #2) — coordinator reports success while the device rejects every call.

2026-11-13 (Claude): implemented in worktree branch task-12-visible-device-rejections, stacked on the TASK-73 branch (local commit, not pushed). Change against the plan: the essential calls are /api/phone/status and /api/call/status only. /api/system/info is left out because in the original report (2026-10-11, code 7) it kept answering while everything else was refused, so 'all three refused' would not have caught that case. api.py: device_errors, _record_device_result, feature_for_path, ESSENTIAL_API_PATHS, TWON_ERROR_CODES_PRIVILEGE. coordinator.py: _essential_refusals, _feature_not_supported, _async_sync_privilege_issues, async_delete_api_privilege_issues. Translations: issues.api_privilege_missing in strings.json + en/de/cs. Unit tests: test_coordinator.DeviceRefusalTests (6 tests), test_api (test_refusals_are_remembered_per_path_and_cleared_on_success, test_repeated_refusal_is_logged_as_warning_only_once, test_not_supported_optional_feature_never_logs_a_warning, test_feature_for_path_groups_optional_endpoints), test_init.test_unload_removes_this_entrys_privilege_repairs, test_translations.test_missing_privilege_repair_is_translated. E2E: test_no_repair_issue_when_device_accepts_all_calls in e2e/tests/test_10_entities.py (+ HA.repair_issues). Local run: 845 unit tests green except test_blueprint (jinja2 missing in the local Python, unrelated), validate.py green, mypy not run (not installed locally). Not covered: code 7 gets no Repair issue of its own (it surfaces through the failed refresh and its message); a Repair issue for a privilege the model cannot grant (e.g. Switches on the device from issue #105) stays open until the user ignores it.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
A device that answers 2N error bodies no longer looks healthy. The API client remembers the last refusal per path; the coordinator fails the refresh when /api/phone/status and /api/call/status are both refused, opens one translated Repair issue per optional feature refused for privileges (codes 8-10) and quietly stops polling a feature the model lacks (code 1). Repeated refusals are logged at DEBUG. PR: https://github.com/mastalir1980/ha-2N-intercom/pull/124 (stacked on the TASK-73 PR). Checks green on 1914bd1: e2e-pi=pass (25 passed, 0 failed, 1 skipped; the skip is the same as on main), validate=pass. Jan ran this branch on his production intercom on 2026-11-14 with no regression.
AC #1: proven. test_coordinator.DeviceRefusalTests.test_refresh_fails_when_every_essential_call_is_refused raises UpdateFailed with the 2N error in the message and reports data again once one essential call answers; test_refused_optional_calls_alone_do_not_fail_the_refresh. Essential calls are phone/status and call/status (system/info is excluded, see the implementation notes).
AC #2: proven. test_privilege_refusal_opens_one_repair_issue_and_clears_it covers codes 8, 9, 10 for switch, io, camera and directory: one create call over three polls, the privilege group in the placeholders, issue gone after the call succeeds; test_two_refused_paths_of_one_feature_share_one_issue; test_init.test_unload_removes_this_entrys_privilege_repairs.
AC #3: proven. test_not_supported_feature_is_switched_off_without_issue (io caps/status not polled, switch and phone still polled, no issue, no WARNING); test_api.test_not_supported_optional_feature_never_logs_a_warning (INFO once, then DEBUG); test_repeated_refusal_is_logged_as_warning_only_once.
AC #4: proven. test_translations.test_missing_privilege_repair_is_translated plus the existing key and placeholder consistency tests for strings.json and en/de/cs; validate.py green (PR check validate).
AC #5: proven. e2e-pi on the PR: test_no_repair_issue_when_device_accepts_all_calls (new) and test_entities_available passed on the E2E intercom.
<!-- SECTION:FINAL_SUMMARY:END -->
