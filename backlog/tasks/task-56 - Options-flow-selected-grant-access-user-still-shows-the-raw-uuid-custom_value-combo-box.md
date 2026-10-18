---
id: TASK-56
title: >-
  Options flow: selected grant-access user still shows the raw uuid
  (custom_value combo box)
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-18 13:11'
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
- [ ] #1 grant_access_user SelectSelector is built with custom_value=False; unit test
- [ ] #2 Stored uuid in the directory (any letter case) and the unknown-uuid fallback still produce an option whose value equals the stored value; existing TASK-48 tests green
- [ ] #3 Clearing the field still removes grant_access_user from options; unit test
- [ ] #4 Called-id (peer) field is unchanged; full unit suite, validate.py green; e2e-pi green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
config_flow.py async_step_device: grant_user_field custom_value=False. tests/test_config_flow.py: assert the selector config. Do not change the peer selector, option labels or the TASK-48 fallback logic.
<!-- SECTION:PLAN:END -->
