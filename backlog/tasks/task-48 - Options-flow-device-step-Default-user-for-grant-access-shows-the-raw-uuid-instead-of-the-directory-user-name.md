---
id: TASK-48
title: >-
  Options flow (device step): "Default user for grant access" shows the raw uuid
  instead of the directory user name
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-16 14:45'
updated_date: '2026-10-17 09:34'
labels:
  - bug
  - config-flow
  - access-control
milestone: m-0
dependencies: []
references:
  - custom_components/2n_intercom/config_flow.py
  - custom_components/2n_intercom/api.py
  - custom_components/2n_intercom/strings.json
  - tests/test_config_flow.py
  - TASK-15
  - TASK-8
  - custom_components/2n_intercom/translations
  - e2e/e2elib/twon.py
  - e2e/tests/test_40_options_flow.py
  - docs/API_REFERENCE.md
priority: medium
type: bug
ordinal: 55000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: in the Device step of the options flow the field "Default user for grant access" shows a raw directory uuid (lower-case, e.g. `xxxxxxxx-e657-4671-a19d-…`) instead of the user's name (report and screenshot by Jan, 2026-10-16). Users cannot tell which person grant_access will use. TASK-15 (labels and help texts) does not cover this; it stays in To Test on its own criteria.

Facts (code on main 9593640):
- config_flow.py `async_step_device` (~l. 735-760): options are `SelectOptionDict(label=user["name"] or user["uuid"], value=user["uuid"])` with the uuid exactly as dir/query reports it. The stored value is shown via `description={"suggested_value": current_grant_user}`. If the stored uuid matches an option only case-insensitively, no fallback is added, but the HA select compares the suggested value with option values case-sensitively, so it renders the raw stored string. 2N reports uuids upper-case in dir/query and lower-case in log events (docstring of `extract_directory_users`, docs/API_REFERENCE.md "Jména uživatelů"), and the screenshot shows lower-case: this path alone produces the reported symptom.
- If the stored uuid is not in the directory, the fallback option has label = uuid (bare uuid on screen).
- api.py `async_get_directory` asks dir/query for `"fields": ["name", "callPos.peer"]` — `uuid` is not requested. `extract_directory_users` drops users without a uuid. If the device honours `fields` strictly, the user list is empty and only the bare-uuid fallback is left.
- `async_get_directory` returns `[]` silently on a 2N error (`success: false`, logged via log_device_error); `_async_get_directory_choices` turns exceptions into `([], [])` after `_LOGGER.exception`. The form cannot tell "no users" from "lookup failed".
- Users with an empty name are shown as a bare uuid as well.

The fix below covers all these causes, so it does not depend on which one hit Jan's install.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A stored grant-access uuid that exists in the directory in any letter case is shown with the user name, stays selected, and is saved unchanged when the form is submitted - unit test
- [x] #2 A stored uuid that is not in the directory is shown with a translated "Unknown user (<uuid>)" label, not a bare uuid, and the stored value is kept until the user changes it - unit test
- [x] #3 A directory user without a name is shown with a translated label, not a bare uuid - unit test
- [x] #4 A failed directory lookup (exception or 2N success:false) is logged once at WARNING and the device step shows the translated error directory_unavailable; the form can still be submitted - unit test
- [x] #5 E2E (read-only): the device step's grant_access_user options carry the names that dir/query returns on the E2E intercom (HA says name <-> 2N says name)
- [x] #6 strings.json and translations en, de, cs updated; full unit suite, validate.py and py_compile green on Python 3.12+; PR check e2e-pi green
- [x] #7 dir/query keeps fields name/callPos.peer (no uuid field); the uuid that 2N returns with every entry is kept - unit test, confirmed on the E2E intercom fw 3.x
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Request uuid in directory fields and add opt-in device-error raising while preserving existing API callers.
2. Return directory availability from the flow helper, log lookup failures once at WARNING, preserve stored UUID case in named options, and add localized fallback labels and the non-blocking error.
3. Extend unit coverage for selection persistence, fallback labels, lookup failures and request fields; add an independent read-only directory/options E2E comparison.
4. Update related docs, run all local Python gates, record implementation notes, and commit on the current task branch. Leave criteria unchecked and status In Progress for orchestrated E2E/review.

5. Fix the TASK-48 directory-query regression: keep UUIDs as response metadata rather than selectable directory data fields in both clients, add offline request/metadata/auth/error regressions, and report only the numeric device error code from the E2E client. Document the correction to AC #5, run the local Python gates, and commit without closing the task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented case-insensitive grant-access user matching with the stored UUID preserved exactly in the selected option and saved value. Added localized unknown/unnamed labels (en/de/cs), explicit uuid directory fields, and opt-in device-error raising for flow lookups while preserving default API behavior for coordinator callers. Lookup failures now produce one WARNING with the host and a DEBUG-only traceback; the translated directory_unavailable error does not block submission. Called ID behavior and dual authentication are unchanged.

Added regression coverage for mixed-case UUID persistence, unknown-user persistence, localized fallback labels, exceptions and actual success:false responses, single-warning logging without credentials, directory request fields, and options error translations. Added an independent POST dir_users() E2E client and a read-only options-label comparison that aborts without submitting and reports only counts. Updated README and API reference.

Local validation on Python 3.12.15: full unittest discovery passed (628 tests), validate.py passed, integration py_compile passed; both changed E2E Python files compile. Standalone config-flow discovery depends on coordinator stubs loaded by full-suite discovery (existing test-bootstrap limitation); no unrelated bootstrap changes were made. E2E was not run on this headless machine and remains gated by the orchestrator/PR e2e-pi check. Acceptance criteria remain unchecked and status remains In Progress as instructed.

PR-check fix: the new read-only E2E comparison failed in its independent directory request before contacting the HA options flow. TASK-48 had added uuid to fields in both clients; UUID belongs to each returned entry as metadata, not the selectable directory data fields. Restored the integration request to name/callPos.peer and made the independent client select name while retaining returned UUIDs. This corrects the premise of AC #5 (explicit uuid field selection); the criterion remains unchecked rather than claiming it is met. The supplied check summary omits the device error code, so device confirmation remains pending e2e-pi; the E2E client now reports numeric error codes only, without raw descriptions or directory data. Added six offline regressions covering both request shapes/UUID preservation, per-service Basic retry, device errors and HTTP failure propagation; four failed before the fix and all pass afterward. No existing E2E assertions were weakened, skipped or deleted. Python 3.12.15 local gates passed: 634 unit tests, validate.py, integration py_compile, and both related E2E files compile. E2E was not run on the VM; status remains In Progress and all criteria remain unchecked.

Review after merge (PR #71): the first e2e-pi failure was not caused by uuid in fields. The E2E API account lacked System - Control; 2N documents /api/dir/* under System - Control and answered error 10 (insufficient privileges). After the privilege was enabled, e2e-pi passed. AC #5 was reworded: 2N returns uuid with every entry without asking for it, so the integration does not request it. docs/API_REFERENCE.md corrected accordingly (the claim that uuid in fields rejects the query on fw 3.x was unverified and was removed).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Grant-access user in the options device step is shown by directory name (case-insensitive uuid match, stored value kept), with translated labels for unknown and unnamed users and a non-blocking directory_unavailable error when dir/query fails. Verified by unit tests (634, Python 3.12), validate.py, and the read-only E2E check on the Pi (e2e-pi green on PR #71). dir/query needs System - Control.
<!-- SECTION:FINAL_SUMMARY:END -->
