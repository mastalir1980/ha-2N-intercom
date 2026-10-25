---
id: TASK-12
title: >-
  Device rejects API calls (codes 7, 10, 12) but the integration reports success
  with empty entities
status: To Do
assignee: []
created_date: 2026-10-11 16:04
updated_date: '2026-10-24T08:28:00Z'
labels:
  - e2e
  - api
  - repairs
  - needs-analysis
milestone: m-1
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
- [ ] #1 When every essential call is refused with a 2N error body, the coordinator refresh fails (entities unavailable) instead of reporting success with empty data [unit]
- [ ] #2 A refused optional feature call (switch, io, camera, directory) with a privilege error (codes 8-10) creates one translated Repair issue naming the missing privilege group; the issue clears when the call succeeds [unit]
- [ ] #3 Code 1 (not supported) on an optional feature disables only that feature, with no Repair issue and no repeated WARNING [unit]
- [ ] #4 strings.json and en/de/cs translations for the new Repair issues; validate.py green [unit]
- [ ] #5 E2E: with the read-only E2E account no Repair issue is open and all entities are available (HA says X <-> 2N API says X) [e2e]
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Recurred 2026-10-11 (report 20261011-180751), sha ade47bc, HA 2026.9.0, device E2E intercom fw 3.x. Failed: test_device_accepts_integration_requests (code=7 'invalid connection type' on phone/switch/io/call status, log/subscribe, system/switch/io caps) and test_camera_snapshot_is_jpeg (camera_proxy -> 500; container log: camera/snapshot rejected code=7). ha_system_log count=36 WARNING at api.py:144. system/info still succeeds (device_registry test passed). Unchanged from first occurrence (20261011-175902).

2026-10-11 (Jan): the intercom's HTTP API is configured HTTPS-only — plain HTTP is disabled on the device. This explains code 7 'invalid connection type': the config entry created by ade47bc settled on plaintext HTTP. The secure-by-default work (TASK-1: verified HTTPS -> unverified HTTPS -> HTTP last) is the expected fix for the code-7 part; verify with 'bash e2e/e2e.sh reset-entry' + 'bash e2e/e2e.sh wip'. The silent-failure part (coordinator success with 100% rejected calls) remains a separate bug either way. Also consider: when the device rejects HTTP with code 7, the config flow should fall through to HTTPS instead of accepting the entry.

Recurred 2026-10-11 (report 20261011-201113), sha ade47bc-dirty, HA 2026.9.0, device E2E intercom fw 3.x. NEW DATA POINT: this run deployed the WORKTREE (ref=worktree, ade47bc-dirty) so the security/secure-by-default-connection changes WERE live (previous two occurrences deployed committed ade47bc without them) — code 7 still occurs on every request, so the secure-by-default branch does not resolve this. Failed: test_device_accepts_integration_requests (code=7 'invalid connection type' on phone/switch/io/call status, log/subscribe, system/switch/io caps) and test_camera_snapshot_is_jpeg (camera_proxy -> 500; container log camera/snapshot rejected code=7). ha_system_log count=36 WARNING at api.py:145. system/info still succeeds (device_registry test passed).

2026-10-11 verification: with the working-tree secure-by-default changes (TASK-1, not yet committed) + reset-entry + new API account, report e2e/reports/20261011-201937 is green: test_device_accepts_integration_requests and test_camera_snapshot_is_jpeg pass, zero 'rejected by device' warnings. => code-7 part is fixed by TASK-1 once merged. Still open here: the silent-failure part (AC #2) — coordinator reports success while the device rejects every call.
<!-- SECTION:NOTES:END -->
