---
id: TASK-48
title: >-
  Options flow (device step): "Default user for grant access" shows the raw uuid
  instead of the directory user name
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-16 14:45'
updated_date: '2026-10-16 16:22'
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
- [ ] #1 A stored grant-access uuid that exists in the directory in any letter case is shown with the user name, stays selected, and is saved unchanged when the form is submitted - unit test
- [ ] #2 A stored uuid that is not in the directory is shown with a translated "Unknown user (<uuid>)" label, not a bare uuid, and the stored value is kept until the user changes it - unit test
- [ ] #3 A directory user without a name is shown with a translated label, not a bare uuid - unit test
- [ ] #4 A failed directory lookup (exception or 2N success:false) is logged once at WARNING and the device step shows the translated error directory_unavailable; the form can still be submitted - unit test
- [ ] #5 dir/query is requested with uuid in fields - unit test
- [ ] #6 E2E (read-only): the device step's grant_access_user options carry the names that dir/query returns on the E2E intercom (HA says name <-> 2N says name)
- [ ] #7 strings.json and translations en, de, cs updated; full unit suite, validate.py and py_compile green on Python 3.12+; PR check e2e-pi green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. api.py `async_get_directory`: request `"fields": ["uuid", "name", "callPos.peer"]` so uuids are always returned. Do not change its return/raise behaviour for other callers (coordinator name cache).
2. config_flow.py `_async_get_directory_choices`: return a third value `directory_ok: bool` — False when the call raised or when the device answered `success: false` (add a small way to detect it, e.g. a keyword `raise_on_device_error=True` on `async_get_directory` used only here, raising `TwoNAPIError`). Log the failure once at WARNING with the host (no credentials), replacing `_LOGGER.exception` (keep the traceback only at DEBUG). Update both callers (user-step Called ID list ~l. 345 and options device step).
3. config_flow.py options device step, grant-user options:
   - Find the stored uuid in `directory_users` case-insensitively. When found, build that option with `value = the stored string exactly` (so `suggested_value` matches and the stored value is unchanged on save) and `label = name`.
   - Users with an empty name: label `"<uuid> (no name)"`-style text from the label helper below, not a bare uuid.
   - Stored uuid not in the directory: one extra option, value = stored uuid, label = translated "Unknown user (<uuid>)".
   - Label texts via a helper in the style of `_all_calls_label(language)` (en, de, cs).
4. When `directory_ok` is False on the first show of the device step, return the form with `errors={"base": "directory_unavailable"}`; add `options.error.directory_unavailable` ("The user list could not be loaded from the intercom; the stored user is kept.") to strings.json and translations en/de/cs. Submitting the form must still work.
5. tests/test_config_flow.py: (a) stored lower-case uuid + directory upper-case uuid -> option value equals stored string, label = name, suggested_value equals it; (b) unknown uuid -> extra option with the "Unknown user" label, value kept on submit; (c) dir/query raises / success:false -> WARNING logged, errors base directory_unavailable, stored value kept; (d) user without name -> labelled, not bare; (e) async_get_directory sends `uuid` in fields.
6. e2e: add `dir_users()` to e2e/e2elib/twon.py (POST /api/dir/query with fields uuid,name; independent of api.py). In e2e/tests/test_40_options_flow.py add a read-only check: start the options flow, read the `grant_access_user` selector options of the device step, and assert every directory user with a name from twon appears with label == name ("HA says name ⇄ 2N dir/query says name"); abort the flow without submitting. Never print uuids or names in assertion messages beyond counts.
7. Must not change: entry.data vs entry.options split (grant_access_user stays in options); the stored uuid string is never rewritten unless the user picks another option; dual auth in api.py; Called ID behaviour (only the directory_ok plumbing).
<!-- SECTION:PLAN:END -->
