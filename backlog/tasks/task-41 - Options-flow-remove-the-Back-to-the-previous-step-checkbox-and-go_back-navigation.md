---
id: TASK-41
title: >-
  Options flow: remove the "Back to the previous step" checkbox and go_back
  navigation
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-15 16:20'
updated_date: '2026-10-16 15:27'
labels:
  - config-flow
  - ux
milestone: m-0
dependencies: []
references:
  - custom_components/2n_intercom/config_flow.py
  - custom_components/2n_intercom/strings.json
  - tests/test_config_flow.py
  - e2e/tests/test_40_options_flow.py
  - >-
    backlog/tasks/task-14 -
    Options-flow-show-Next-on-intermediate-steps-and-allow-going-back-to-the-previous-step.md
priority: medium
type: bug
ordinal: 48000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: after the TASK-14 release, the options flow shows a 'Back to the previous step' checkbox on the camera and relay steps (and on the setup device step). Jan does not want this checkbox. Home Assistant data-entry flows have no native Back button, and Jan chose to drop back navigation entirely. The Next/Submit labels from TASK-14 (last_step) stay. Current behaviour: CONF_GO_BACK is an optional boolean on the camera, relay and setup device forms in config_flow.py, with go_back branches in async_step_device, async_step_camera and async_step_relay, and go_back strings in strings.json and translations/{en,de,cs}.json. Expected behaviour: no go_back field on any form; the flow only moves forward; to change an earlier value the user closes the dialog and starts again. Options are still saved only by the final step.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 No form in the options flow or the initial setup flow contains a go_back field
- [ ] #2 Camera and relay steps no longer branch on go_back; the flow is forward-only and saves options only from the final step
- [ ] #3 last_step values from TASK-14 are unchanged (Next on intermediate steps, Submit on the saving step)
- [ ] #4 go_back keys are removed from strings.json and all translations (en/de/cs); validate.py green
- [ ] #5 Unit tests for back navigation in tests/test_config_flow.py are removed or rewritten to assert forward-only flow; full unit suite green on Python 3.12+
- [ ] #6 E2E options-flow test (e2e/tests/test_40_options_flow.py) no longer drives a back navigation and still asserts last_step; bash e2e/e2e.sh wip green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. const.py: remove `CONF_GO_BACK` (line ~23) and its import in config_flow.py (line ~31). Grep the whole repo (`custom_components/`, `tests/`, `e2e/`) for `go_back` / `CONF_GO_BACK` so nothing references it afterwards.
2. config_flow.py, setup flow `async_step_device` (~line 330): drop the `go_back` pop and the branch back to `async_step_user` (~lines 343-348) and the `vol.Optional(CONF_GO_BACK, ...)` field (~line 391). Submit always goes to `_async_create_entry()`.
3. config_flow.py, options flow `async_step_camera` (~line 870): drop the `go_back` pop (~line 879), the `if go_back: return await self.async_step_device()` branch (~line 906) and the schema field (~line 1006). Submit always goes to `_async_after_camera_step()`.
4. config_flow.py, options flow `async_step_relay` (~line 1052): drop the `go_back` pop (~line 1060), the whole back-navigation block (~lines 1065-1072) and the schema field (~line 1122). Keep storing the submitted values in `self._relay_inputs[cap["switch"]]` and the forward logic (next relay, then save) unchanged.
5. Must not change: every `last_step=` value from TASK-14 (lines ~327, 399, 861, 1015, 1131); options are saved only by the final step; `self._data` / `_relay_inputs` draft handling; the user-step prefill and the device-identity handling in `async_step_user` (no refactor in this task). The per-relay step itself stays — removing it is TASK-42.
6. strings.json and translations/en.json, de.json, cs.json: remove every `go_back` key from `data` and `data_description` of the user/device, camera and relay steps (strings.json ~lines 26, 33, 122, 132, 143, 150 and the matching lines in each translation). Keep JSON valid and the four files in sync; run `python3 validate.py`.
7. tests/test_config_flow.py: delete the back-navigation tests (`test_device_step_go_back_returns_to_user_prefilled` ~902, `test_go_back_to_other_host_drops_previous_device_identity` ~937, `test_camera_go_back_returns_to_device_with_prefill` ~1506, `test_relay_go_back_to_camera_and_device` ~1546, `test_relay_go_back_between_relays_not_counted_twice` ~1609). Add one test that walks setup and options flows and asserts no shown form schema contains a `go_back` field, and keep/extend the TASK-14 last_step tests (class at ~1422) so they still pass unchanged.
8. e2e/tests/test_40_options_flow.py: rename the test to `test_options_flow_last_step_forward_only`, remove the back-navigation driving and the `go_back` skip in `_defaults_payload`, assert `"go_back" not in _field_names(step)` on every step, keep the existing last_step assertions and the check that options are unchanged when submitted with defaults. Update the module docstring. Read-only on the intercom; no relay marker needed.
9. Docs: remove the back-navigation sentences in README.md (~line 179 setup, ~line 205 options flow) and INSTALLATION.md (~line 87); replace with: the wizard is forward-only, to change an earlier value close the dialog and start Configure again; nothing is saved until the last step.
10. Validation: unit suite + `validate.py` on Python 3.12+, `py_compile`, green `bash e2e/e2e.sh wip` (headless: PR check `e2e-pi`).
<!-- SECTION:PLAN:END -->
