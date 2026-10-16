---
id: TASK-41
title: >-
  Options flow: remove the "Back to the previous step" checkbox and go_back
  navigation
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-15 16:20'
updated_date: '2026-10-16 15:28'
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
1. Remove CONF_GO_BACK, its form fields and backward-navigation branches from initial setup and options flows while preserving last_step and final-step-only saving.
2. Remove go_back translations, rewrite navigation unit and E2E coverage for forward-only progression and draft saving, and update README/INSTALLATION guidance.
3. Run the required Python 3.12+ local gates, record implementation and validation notes, and commit TASK-41 locally without ticking acceptance criteria or marking Done; leave device E2E to the e2e-pi PR check.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented forward-only initial setup and options flows: removed CONF_GO_BACK, all three form fields, all navigation branches, and the setup/camera/relay labels and descriptions in strings.json plus en/de/cs translations. Existing last_step expressions and final-step saving paths are unchanged.
Rewrote unit navigation coverage for setup completion/restart and six camera/relay combinations (camera on/off; zero, one, or two relays), asserting no go_back fields, ordered forward progression, Next/Submit flags, no create_entry before the final submission, and preservation of all draft values. Added restart coverage proving unsaved device/camera changes do not enter a new options session.
Updated the E2E options-flow test to traverse every intermediate form forward, check last_step and absent go_back on every form, retain RTSP password masking checks, and abort before the saving step even in a device-only flow. It checks saved options throughout and after aborting. Updated README and INSTALLATION restart/discard guidance.
Local gates passed on Python 3.12.15: python3 -m unittest discover -s tests -t tests (611 tests), python3 validate.py, and python3 -m py_compile custom_components/2n_intercom/*.py. The changed E2E test also compiles. No device E2E was run on the VM; e2e-pi remains pending for the orchestrator. Acceptance criteria remain unchecked and status remains In Progress.
Follow-up: isolated discovery of test_config_flow.py fails during module loading because its coordinator stub is not initialized independently; the required full-suite discovery initializes the shared stubs and passes. No unrelated test-harness changes were made.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Removed the Back checkbox and backward navigation from setup and options while retaining Next/Submit labels and final-step-only saving. Updated translations, documentation, and forward-only unit/E2E coverage. Local evidence: all 611 unit tests and required validation/compilation gates pass on Python 3.12.15. Device E2E awaits the e2e-pi PR check; task remains In Progress with acceptance criteria unchecked.
<!-- SECTION:FINAL_SUMMARY:END -->
