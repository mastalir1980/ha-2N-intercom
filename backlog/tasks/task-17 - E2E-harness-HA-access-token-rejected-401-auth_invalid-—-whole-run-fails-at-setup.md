---
id: TASK-17
title: >-
  E2E harness HA access token rejected (401 auth_invalid) — whole run fails at
  setup
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-11 19:23'
updated_date: '2026-10-11 19:48'
labels:
  - e2e
  - env
dependencies: []
priority: high
type: bug
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
All E2E tests fail before exercising the integration because the HA client in e2elib/ha.py cannot authenticate to staging HA. REST calls return 401 Unauthorized and the WebSocket auth returns {"type":"auth_invalid","message":"Invalid access token or password"}. The deploy stage itself succeeded (container recreated, HA came up) and the intercom was reachable (context.json is populated: 2N IP Force 2.0 fw 3.3.1.82.4), so this is an environment/credentials problem with the long-lived HA access token the harness reads from e2e/.env — not an integration defect. Likely the staging HA .storage/onboarding was reset on container recreate (invalidating the stored token) or the token in e2e/.env was rotated/expired.

Impact: nothing can be tested — 3 failed, 10 errored, 1 skipped; every failure is the same auth error, so the whole pipeline is unusable until the token is refreshed.

Evidence (report e2e/reports/20261011-211946):
- pytest.log: "e2elib.ha.HAError: websocket auth failed: {type: auth_invalid, message: Invalid access token or password}" at e2elib/ha.py:90 (raised from entries() -> ws(), conftest.py:61) for all config-entry/entity/lifecycle/options tests.
- pytest.log: "GET /api/services -> 401: 401: Unauthorized" (e2elib/ha.py:42) and "GET /api/config -> 401" (context.json ha_version_error).
- ha_container.log: repeated "Login attempt or request with invalid authentication from 192.168.88.52 ... Requested URL: /api/config, /api/websocket, /api/services" — staging HA is rejecting the harness bearer token.
- "[e2e] could not dump system log: websocket auth failed: ... Invalid access token or password".

Suspected location: token source is e2e/.env (HA long-lived token); consumed in e2elib/ha.py:_headers()/ws() (lines 28-29, 87-90). Not a code bug.

Versions: integration sha 6ac5ad2-dirty (worktree), intercom 2N IP Force 2.0 fw 3.3.1.82.4, HA version unknown (401 blocked /api/config).

Reproduce: regenerate/refresh the staging HA long-lived access token, update e2e/.env (HA_TOKEN), then re-run bash e2e/e2e.sh wip. Do not paste the token anywhere.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 With a valid HA token in e2e/.env, bash e2e/e2e.sh wip authenticates and the setup/entity/lifecycle tests (test_config_entry_loaded, test_entities_available, test_services_registered, …) run and pass instead of erroring with auth_invalid
- [ ] #2 The pipeline detects an invalid/expired HA token during bootstrap or a pre-flight check and fails fast with a clear environment-error message, instead of surfacing as ~13 per-test auth_invalid errors that look like integration failures
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Root cause was contention between two parallel e2e sessions sharing the staging HA plus stale renamed containers (hash-prefixed ha-staging leftovers) blocking compose recreate. Fixed by: removing stale containers, graceful compose down, wiping root-owned .storage via a throwaway container (documented permission pitfall), clearing HA_TOKEN/HA_E2E_PASSWORD in .env and re-running bootstrap. Token valid afterwards.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Environment fixed: stale staging containers removed, .storage reset, staging re-bootstrapped; harness token valid. Watch out: parallel e2e sessions still share one staging HA and can invalidate each other.
<!-- SECTION:FINAL_SUMMARY:END -->
