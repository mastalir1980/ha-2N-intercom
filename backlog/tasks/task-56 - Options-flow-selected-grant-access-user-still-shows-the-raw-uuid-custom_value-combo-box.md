---
id: TASK-56
title: >-
  Options flow: selected grant-access user still shows the raw uuid
  (custom_value combo box)
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-18 13:11'
updated_date: '2026-10-18 13:22'
labels:
  - bug
  - config-flow
  - access-control
  - manual-close
milestone: m-0
dependencies: []
priority: medium
ordinal: 63000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: after TASK-48 the dropdown list shows names, but the selected value in the closed field of 'Default user for grant access' is still the raw uuid (Jan, 2026-10-18). Cause: config_flow.py async_step_device builds grant_user_field with SelectSelector(custom_value=True). HA frontend renders custom_value selects as ha-generic-picker and passes the raw stored value without mapping it to the option label (ha-selector-select.ts). Without custom_value it renders ha-select, which shows the label and is clearable. Expected: the closed field shows the user name; the unknown-uuid fallback option from TASK-48 keeps stored values selectable, so custom input is not needed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 grant_access_user SelectSelector is built with custom_value=False; unit test
- [x] #2 Stored uuid in the directory (any letter case) and the unknown-uuid fallback still produce an option whose value equals the stored value; existing TASK-48 tests green
- [x] #3 Clearing the field still removes grant_access_user from options; unit test
- [x] #4 Called-id (peer) field is unchanged; full unit suite, validate.py green; e2e-pi green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Set only grant_user_field in config_flow.py async_step_device to custom_value=False; preserve the peer selector, option labels and TASK-48 UUID fallback logic. 2. Update selector regression coverage in tests/test_config_flow.py, retaining stored-UUID case, unknown-user fallback and clearing coverage. 3. Run the full unit suite, validate.py and integration py_compile with python3; record implementation notes and commit locally without ticking acceptance criteria or setting Done. E2E is deferred to the orchestrator's e2e-pi PR check.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed only the grant-access user selector to custom_value=False so Home Assistant uses the labelled, clearable dropdown. Extended the directory-user unit test to assert this selector configuration and preserve the called-ID selector's custom-value dropdown and peer option. Existing stored-UUID case, unknown-user fallback and clearing tests remain unchanged and pass. Updated the README option description to remove manual UUID input and explain clearing the default. Python 3.12.15: all 675 unit tests passed; validate.py and integration py_compile passed. No E2E commands were run; e2e-pi and the manual-close UI confirmation remain pending. Task remains In Progress and acceptance criteria are unchecked.
<!-- SECTION:NOTES:END -->
