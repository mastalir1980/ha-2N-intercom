---
id: TASK-48
title: >-
  Options flow (device step): "Default user for grant access" shows the raw uuid
  instead of the directory user name
status: To Do
assignee: []
created_date: '2026-10-16 14:45'
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
priority: medium
type: bug
ordinal: 55000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: in the Device step of the options flow the field "Default user for grant access" shows a raw directory uuid (e.g. `xxxxxxxx-e657-4671-a19d-…`, lower-case) instead of the user's name (report and screenshot by Jan, 2026-10-16). Users cannot tell which person grant_access will use. Jan reports that TASK-15 (To Test, AC #3 API labels and help texts) did not solve this.

Facts (code on main, e96c963):
- config_flow.py, options device step (~l. 750-770): options are built from `directory_users` (`extract_directory_users` in api.py) with label = name or uuid, value = uuid as the device reports it. If the stored uuid is not among them (case-insensitive compare), a fallback option with label = uuid is appended. Either path can end in a bare uuid on screen.
- `extract_directory_users` returns uuids exactly as the device reports them; its docstring notes the 2N docs show upper-case uuids in dir/query but lower-case in log events.
- On main the Called ID dropdown uses label = peer (`SelectOptionDict(label=peer, value=peer)`), but the same screenshot shows Called ID labels in the form "<name> - <peer>". So the build running on that install is not main, or the screenshot is from another build.

Hypotheses to verify before this task is ready:
1. Case mismatch: the stored value is lower-case (taken from a log event or typed), dir/query returns the same uuid upper-case. The case-insensitive check finds a match, so no fallback is added, but the HA select matches the default value case-sensitively against option values and shows the raw stored string.
2. The stored uuid is not a directory user of this device at all (user removed, uuid from another device), so the fallback label = uuid is shown.
3. dir/query failed or returned no users (no log at WARNING), so only the fallback exists.

Open questions (Jan / Claude analysis): which build runs on the install; does dir/query on the device return the stored uuid, and in which case; should TASK-15 go back to In Progress.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A stored grant-access uuid that exists in the directory (in any letter case) is shown with the user name and stays selected
- [ ] #2 A stored uuid that is not in the directory is shown with an explicit "unknown user" label (translated), not a bare uuid, and the stored value is kept until the user changes it
- [ ] #3 A failed directory lookup is logged at WARNING and the form says that the user list could not be loaded, instead of an empty or uuid-only list
- [ ] #4 Unit tests cover the match (incl. different letter case), the unknown-uuid and the lookup-failure cases; strings.json and translations en, de, cs updated
- [ ] #5 Full unit suite and validate.py green on Python 3.12+; PR check e2e-pi green
<!-- AC:END -->
