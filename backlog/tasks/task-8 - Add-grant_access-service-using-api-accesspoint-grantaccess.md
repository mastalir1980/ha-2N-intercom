---
id: TASK-8
title: Add grant_access service using /api/accesspoint/grantaccess
status: Done
assignee:
  - '@copilot'
created_date: '2026-08-30 09:27'
updated_date: '2026-10-15 12:47'
labels:
  - access-control
  - services
milestone: m-0
dependencies:
  - TASK-1
priority: high
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Opening the door from HA today pulses the relay directly via /api/switch/ctrl, which leaves no access record on the device. /api/accesspoint/grantaccess (2N HTTP API 5.17.3, available since fw 2.37; verified against the docs 2026-10-11) instead asks the device to grant access on behalf of a directory user, so the device applies that user's access rights and logs the access (it also emits the ApiAccessRequested log event, see TASK-4). Important facts from the docs that shape the design: (1) BOTH parameters are mandatory: id (access point: 0 = arrival/entry, 1 = departure/exit) and user (UUID of a user in the device directory). There is no anonymous 'just open' call. (2) success=true only means the request was processed: the actual outcome is result.accessGranted; when false, result.reason is one of invalidAp, invalidCredential, accessBlocked. (3) Error code 18 = access point disabled. (4) The API account needs service group 'API Access Control' with privilege 'Access Control - Control'; this is separate from the Switch API privilege (compare TASK-13), so missing privilege must surface as a clear error. Design decision (2026-10-11): the service takes an optional user UUID; if omitted, a default user UUID configured in the options flow (behaviour, so entry.options) is used; if neither is set, the call raises a clear HA error. Optionally offer users from /api/dir/query in the options selector. Do not log the UUID-to-name mapping at info level. Ground-truth E2E device: fw 3.x; E2E there is currently blocked by TASK-12.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 New API client method for accesspoint/grantaccess sending id and user; unit tests cover access granted, access denied for each reason (invalidAp, invalidCredential, accessBlocked), error code 18, missing privilege/auth failure and endpoint unsupported
- [x] #2 2n_intercom.grant_access service registered, targets a config entry (answer_call/hangup_call pattern), parameters: optional access_point (0 entry default, 1 exit) and optional user UUID
- [x] #3 Options flow gets a default grant-access user (stored in entry.options); service falls back to it and raises a clear HA error when no user is given or configured
- [x] #4 accessGranted=false raises a HomeAssistantError (translated) that includes the reason; the service never reports success when the door was not opened
- [x] #5 services.yaml, strings.json, translations (en/de/cs) updated; README.md documents the service, required device privilege, the user requirement and the audit-log advantage over switch entities
- [x] #6 E2E test in e2e/tests/ marked @pytest.mark.relay (it physically opens the door) verifying that HA grant_access results in ApiAccessRequested on the device; never run without Jan's explicit request
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. api: async_grant_access(access_point, user) -> GrantAccessResult; raise TwoNAuthenticationError on 401/codes 8-10, TwoNUnsupportedError on 404/codes 1/2/4, TwoNDeviceRejectedError(code) otherwise (code 18 = access point disallowed).
2. const CONF_GRANT_ACCESS_USER; options device step gets an optional SelectSelector (custom_value) filled from dir/query users.
3. Service 2n_intercom.grant_access (config_entry_id, access_point 0/1 default 0, user) in __init__.py following answer_call; translated errors incl. denied reason; never succeed when accessGranted=false.
4. services.yaml, strings/translations en/de/cs, icons, README.
5. Unit tests; E2E test marked relay (not run).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Validation: python3 -m unittest discover -s tests -t tests (530 OK), python3 validate.py OK, py_compile OK. E2E 'bash e2e/e2e.sh wip' on staging (E2E intercom fw 3.x, HA 2026.10.1): 13 passed, 3 skipped, 1 failed — the failure is the pre-existing, unrelated TASK-18 options-flow test. E2E relay test test_50_access_control.py::test_grant_access_logs_api_access_requested is written (@pytest.mark.relay, needs E2E_GRANT_USER_UUID in e2e/.env) but NOT run — it physically opens the door; AC#6 stays unchecked until Jan runs 'bash e2e/e2e.sh relays'.

2026-10-12 (TASK-21.6 split): landed on branch task-8-grant-access (4f40c65, rebased on main with TASK-4 + TASK-9 merged); 563 unit tests OK, validate.py OK, CI green. E2E: 20261012-124448 (--relays) passed but the grant test skipped (E2E_GRANT_USER_UUID unset); 20261012-131421 (--relays, run by Jan at 3670c44) passed 16/1 skipped (SIP sensor only), incl. test_grant_access_is_logged_by_device: HA grant_access on access point 0 produced ApiAccessRequested on the device with ap=0, valid=true and matching uuid. AC6 verified. (The E2E test name is test_grant_access_is_logged_by_device, not test_grant_access_logs_api_access_requested as noted earlier.)
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added api.async_grant_access (/api/accesspoint/grantaccess, id+user) with typed errors (denied reasons, code 18, permission, unsupported), the 2n_intercom.grant_access service (config entry target, access_point 0/1, optional user falling back to the options-flow default user picked from dir/query) with translated HomeAssistantErrors, services.yaml/strings/en/de/cs/icons and README docs. Verified by unit tests (test_api, test_init, test_config_flow; 563 OK) and the relay E2E test_grant_access_is_logged_by_device on the E2E intercom fw 3.x (report 20261012-131421: device logged ApiAccessRequested for the HA call).
<!-- SECTION:FINAL_SUMMARY:END -->
