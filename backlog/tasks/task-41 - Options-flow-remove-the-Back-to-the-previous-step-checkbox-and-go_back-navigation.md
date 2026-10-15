---
id: TASK-41
title: >-
  Options flow: remove the "Back to the previous step" checkbox and go_back
  navigation
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-15 16:20'
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
