---
id: TASK-12
title: >-
  Integration rejected with code 7 'invalid connection type' on every request
  (E2E intercom fw 3.x)
status: To Do
assignee: []
created_date: '2026-10-11 16:04'
updated_date: '2026-10-15 12:47'
labels:
  - e2e
  - api
dependencies: []
priority: high
type: bug
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Against the E2E staging intercom (E2E intercom, firmware 3.x) EVERY integration HTTP API call is rejected by the device with `code=7 description='invalid connection type'`. The config entry still loads and the coordinator reports success=True, but all entities carry empty/default state and the camera is dead — HA camera_proxy returns 500. So the integration looks 'up' while being completely non-functional on this device/firmware, and the HA log fills with a WARNING storm on every poll (~1/s for log/subscribe + every coordinator refresh).

Key point narrowing the cause: the integration AUTHENTICATES fine (no 401 in its log — every rejection is an HTTP-200 body with success=false, code 7), so TLS/transport and credentials are OK; the device accepts the request then refuses the connection type for that account. An INDEPENDENT Digest-over-HTTPS client — the E2E ground-truth helper e2elib/twon.py — reads /api/system/info from the SAME device over HTTPS in the same run (test_00 test_device_registry_matches_device passed). So plain HTTPS Digest works against this device; only the integration's path gets code 7. Suspects: the integration's device API account has a 'Connection type' setting incompatible with the HTTPS request it makes, and/or something in the aiohttp DigestAuthMiddleware(preemptive=False)+Basic-fallback request shape that fw 3.x labels 'invalid connection type'. Needs investigation of what differs between the integration request and a bare Digest/HTTPS GET.

Separate but related integration defect in the same failure: a device that refuses 100% of calls with code 7 is swallowed as empty results and reported as coordinator success (see _async_get_result_dict returning {} and callers logging WARNING only) — the integration should surface an actionable error instead of presenting dead entities as 'working'.

Evidence (report e2e/reports/20261011-175902):
- pytest: test_camera_snapshot_is_jpeg FAILED — camera_proxy -> 500 (tests/test_10_entities.py:31)
- ha_container.log: repeated 'rejected by device ... code=7 description="invalid connection type"' for system/caps, switch/caps, switch/status, io/caps, io/status, phone/status, call/status, camera/snapshot, log/subscribe
- ha_system_log.json: same, count=36, level WARNING, source api.py:144

Suspected location: custom_components/2n_intercom/api.py _async_request (~555) / async_get_session DigestAuthMiddleware (~408); error surfacing in _async_get_result_dict (~800) and coordinator treating empty data as success.

Versions: integration sha ade47bc (deployed = committed HEAD; note the secure-by-default working-tree changes were NOT in this deploy), HA 2026.9.0, device E2E intercom, firmware 3.x. Docs/code are validated against firmware 2.50 (IP Verso), so this is the first run against a 3.x E2E intercom.

Reproduce: e2e/run.sh --ref ade47bc (no --relays needed).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 test_camera_snapshot_is_jpeg passes against E2E intercom fw 3.x (camera_proxy returns a JPEG) and the integration's API calls are no longer rejected with code 7 'invalid connection type'
- [ ] #2 A regression unit test asserts the integration surfaces/handles a device 'code 7 invalid connection type' response (clear error / entities unavailable) instead of silently reporting coordinator success with empty data
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Recurred 2026-10-11 (report 20261011-180751), sha ade47bc, HA 2026.9.0, device E2E intercom fw 3.x. Failed: test_device_accepts_integration_requests (code=7 'invalid connection type' on phone/switch/io/call status, log/subscribe, system/switch/io caps) and test_camera_snapshot_is_jpeg (camera_proxy -> 500; container log: camera/snapshot rejected code=7). ha_system_log count=36 WARNING at api.py:144. system/info still succeeds (device_registry test passed). Unchanged from first occurrence (20261011-175902).

2026-10-11 (Jan): the intercom's HTTP API is configured HTTPS-only — plain HTTP is disabled on the device. This explains code 7 'invalid connection type': the config entry created by ade47bc settled on plaintext HTTP. The secure-by-default work (TASK-1: verified HTTPS -> unverified HTTPS -> HTTP last) is the expected fix for the code-7 part; verify with 'bash e2e/e2e.sh reset-entry' + 'bash e2e/e2e.sh wip'. The silent-failure part (coordinator success with 100% rejected calls) remains a separate bug either way. Also consider: when the device rejects HTTP with code 7, the config flow should fall through to HTTPS instead of accepting the entry.

Recurred 2026-10-11 (report 20261011-201113), sha ade47bc-dirty, HA 2026.9.0, device E2E intercom fw 3.x. NEW DATA POINT: this run deployed the WORKTREE (ref=worktree, ade47bc-dirty) so the security/secure-by-default-connection changes WERE live (previous two occurrences deployed committed ade47bc without them) — code 7 still occurs on every request, so the secure-by-default branch does not resolve this. Failed: test_device_accepts_integration_requests (code=7 'invalid connection type' on phone/switch/io/call status, log/subscribe, system/switch/io caps) and test_camera_snapshot_is_jpeg (camera_proxy -> 500; container log camera/snapshot rejected code=7). ha_system_log count=36 WARNING at api.py:145. system/info still succeeds (device_registry test passed).

2026-10-11 verification: with the working-tree secure-by-default changes (TASK-1, not yet committed) + reset-entry + new API account, report e2e/reports/20261011-201937 is green: test_device_accepts_integration_requests and test_camera_snapshot_is_jpeg pass, zero 'rejected by device' warnings. => code-7 part is fixed by TASK-1 once merged. Still open here: the silent-failure part (AC #2) — coordinator reports success while the device rejects every call.
<!-- SECTION:NOTES:END -->
