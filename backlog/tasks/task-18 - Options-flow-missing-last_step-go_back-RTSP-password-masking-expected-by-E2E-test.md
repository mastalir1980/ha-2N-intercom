---
id: TASK-18
title: >-
  Options flow missing last_step / go_back / RTSP-password masking expected by
  E2E test
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-11 19:29'
updated_date: '2026-10-15 12:47'
labels:
  - e2e
  - config-flow
dependencies: []
priority: medium
type: bug
ordinal: 18000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
E2E run 20261011-212644 (worktree sha 369e923-dirty) fails on the new, still-untracked test e2e/tests/test_40_options_flow.py::test_options_flow_last_step_and_back_navigation. This is a NEW root cause, distinct from TASK-16 (direct entry["options"] KeyError at line 50): the test now gets past that line and fails on the first real assertion because the deployed options flow does not implement the TASK-14/TASK-15 UX the test asserts.

The test expects three behaviours the committed TwoNIntercomOptionsFlow does not provide:
1. Next/Submit button labels via async_show_form(..., last_step=...): every non-final step should report last_step: False and the final step last_step: True. The code never passes last_step, so HA returns last_step: None for every step. (device form config_flow.py:729, camera :858, relay :959.)
2. Back navigation: every step after the first should offer a go_back boolean field that returns to the previous step keeping session values. No step defines go_back.
3. RTSP password masking (TASK-15): rtsp_password should use a password-type text selector and must NOT suggest the stored value back. The code uses a plain str field with description.suggested_value = current password (config_flow.py:824-828) — both wrong.

Note: TASK-14 and TASK-15 are referenced in the test docstring but do NOT exist in the backlog, so the driving feature is untracked. OPEN QUESTION for Jan: implement the options-flow UX (last_step + go_back + password masking) as described, or drop/gate this new test if the UX is not wanted. Resolve before handing to @copilot.

Evidence (pytest.log):
  tests/test_40_options_flow.py:60: in test_options_flow_last_step_and_back_navigation
      assert flow["last_step"] is (not camera_enabled and not relays)
  E   assert None is ((not True))
  1 failed, 11 passed, 2 skipped
All other E2E tests pass; ha_system_log.json shows no integration errors (only an unrelated third-party rich/segment SyntaxWarning in HA core components/image). Container log lines (RTSP probe skipped, MJPEG 401 with no RTSP creds, unsubscribe code=12 during reload) are expected debug, not failures.

Versions: integration sha 369e923-dirty (worktree), HA 2026.9.0, E2E intercom fw 3.x.
Reproduce: e2e/run.sh --ref 369e923 (no --relays; the relay step is skipped by this test and never switches a relay).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 e2e/tests/test_40_options_flow.py::test_options_flow_last_step_and_back_navigation passes against the deployed integration
- [ ] #2 Options flow sets last_step correctly (False on every non-final step, True on the final step) for the device/camera/relay step sequence
- [ ] #3 Every options-flow step after the first offers a go_back control that returns to the previous step with session values preserved
- [ ] #4 rtsp_password uses a password-type text selector and never suggests the stored password back into the form (TASK-15)
- [ ] #5 Unit test in tests/ covers the options-flow step sequence (last_step + go_back), independent of a live device
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Recurred: run 20261011-214345, sha 369e923-dirty, HA 2026.10.1 (was 2026.9.0), E2E intercom fw 3.x. Same root cause — test_40_options_flow.py:60 `assert None is ((not True))`: options flow still returns last_step: None. 1 failed, 13 passed, 3 skipped (test suite grew: now 17 items). All other tests green; no integration errors in ha_system_log.json (only unrelated rich/segment SyntaxWarning).

Not a bug. The run deployed the wrong code: a parallel session had switched the shared checkout from task-14-15-options-flow-ux to main, so --worktree deploys pushed main (which lacks the TASK-14/15 implementation) while the untracked E2E test expected the new behavior. TASK-14 and TASK-15 do exist — their task files were committed on the feature branch in this session, so they were invisible while the checkout sat on main. The features are implemented and verified on branch task-14-15-options-flow-ux (unit suite + a passing staging run of test_40_options_flow at 21:37).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed as not-a-bug: wrong git ref was deployed to staging due to a parallel session switching the shared checkout; the asserted features exist on branch task-14-15-options-flow-ux and pass on staging.
<!-- SECTION:FINAL_SUMMARY:END -->
