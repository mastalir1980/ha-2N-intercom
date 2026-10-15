---
id: TASK-13
title: >-
  E2E ground-truth 2N account lacks Switch API privilege — 401 on
  /api/switch/{caps,status}
status: Done
assignee: []
created_date: '2026-10-11 16:04'
updated_date: '2026-10-15 12:47'
labels:
  - e2e
  - env
dependencies: []
priority: low
type: bug
ordinal: 43000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The E2E ground-truth client (e2elib/twon.py) gets HTTP 401 Unauthorized when reading /api/switch/caps and /api/switch/status from the staging intercom, which makes two entity-mirror tests error out before they ever compare HA state. The SAME helper, SAME HTTPS Digest credentials, reads /api/system/info successfully in the same run (test_00 test_device_registry_matches_device passed). A 401 on some services but not others is the classic 2N per-service account privilege: the API account the E2E harness uses has System access but not the Switch service enabled/granted on this device.

This is independent of the integration (it is the test's own direct device call, on purpose kept separate from api.py) and independent of the code-7 issue affecting the integration (that is an HTTP-200 app error, this is a transport-level 401). Classify as environment: the device's HTTP API account used by the E2E tests needs the Switch service enabled/privileged (or the E2E credentials must point at an account that has it).

Evidence (report e2e/reports/20261011-175902):
- test_switch_entities_match_device_caps FAILED: HTTPError 401 for https://<device>/api/switch/caps (tests/test_10_entities.py:47 -> e2elib/twon.py:30)
- test_switch_state_matches_device FAILED: HTTPError 401 for https://<device>/api/switch/status (tests/test_10_entities.py:53 -> e2elib/twon.py:30)
- test_00 device_registry (uses twon.system_info over HTTPS Digest) PASSED — proves transport/auth are fine for System service.

Suspected location: not code — device-side 2N HTTP API account config for the E2E credentials (Services -> HTTP API -> account privileges, Switch service). twon.py _get (e2elib/twon.py:25) already does Digest->Basic fallback; the 401 survives it.

Versions: integration sha ade47bc, HA 2026.9.0, device E2E intercom, firmware 3.x.

Reproduce: e2e/run.sh --ref ade47bc (no --relays needed).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 test_switch_entities_match_device_caps and test_switch_state_matches_device pass (the E2E ground-truth account can read /api/switch/caps and /api/switch/status)
- [x] #2 The E2E setup docs (e2e/README.md) state which 2N HTTP API services/privileges the test account must have, so this misconfiguration is caught at setup rather than as a test failure
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Recurred 2026-10-11 (report 20261011-180751), sha ade47bc, HA 2026.9.0, device E2E intercom fw 3.x. Failed: test_switch_entities_match_device_caps and test_switch_state_matches_device — twon.py _get raises 401 on /api/switch/caps and /api/switch/status (challenge: Basic realm="HTTP API (2/00000100)", Digest). Same account reads /api/system/info fine (device_registry test passed). Digest->Basic fallback in twon.py:25 does not clear it. Unchanged from first occurrence (20261011-175902).

2026-10-11 (Jan): confirmed — the API account used by the E2E tests lacks the needed privileges. Fix is on the device: use an HTTP API account with read + control rights for the required services, then update INTERCOM_USER/INTERCOM_PASSWORD in e2e/.env and run 'bash e2e/e2e.sh reset-entry'.

Recurred 2026-10-11 (report 20261011-201113), sha ade47bc-dirty (worktree deploy, secure-by-default changes live), HA 2026.9.0, device E2E intercom fw 3.x. Failed: test_switch_entities_match_device_caps and test_switch_state_matches_device — twon.py _get raises 401 on /api/switch/caps and /api/switch/status (challenge: Basic realm="HTTP API (2/00000100)", Dig). Same account reads /api/system/info fine (device_registry passed). Digest->Basic fallback in twon.py:30 does not clear it. Unchanged from prior occurrences; independent of the secure-by-default branch (test-side HTTPS 401, not the integration's code-7).

Validation: report e2e/reports/20261011-201937 (worktree, 11 passed / 2 skipped) — test_switch_entities_match_device_caps and test_switch_state_matches_device pass after Jan switched the E2E credentials to an API account with Switch/I-O/Phone privileges.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Environment fix: the E2E tests now use a dedicated 2N HTTP API account with read + control rights for System, Switch, I/O, Phone/Call, Camera and Logging. e2e/README.md documents the required privileges and the reset-entry step. Verified by E2E run e2e/reports/20261011-201937 (all non-relay tests green on E2E intercom fw 3.x).
<!-- SECTION:FINAL_SUMMARY:END -->
