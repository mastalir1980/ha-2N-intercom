---
id: TASK-14
title: >-
  Options flow: show Next on intermediate steps and allow going back to the
  previous step
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-11 18:42'
updated_date: '2026-10-11 18:57'
labels:
  - config-flow
  - ux
dependencies: []
references:
  - custom_components/2n_intercom/config_flow.py
  - tests/test_config_flow.py
  - 'https://developers.home-assistant.io/docs/data_entry_flow_index/'
priority: medium
type: enhancement
ordinal: 14000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The options flow (Configure on the integration card) walks the user through up to three kinds of screens: `device` → `camera` (only when the camera is enabled) → one `relay` screen per auto-detected relay. Every screen currently shows a "Submit" button, so users cannot tell whether the next click saves or continues, and there is no way to return to an earlier screen to fix a value — the only option is to finish or close the dialog and start over. The initial setup flow (`user` → `device`) has the same problem on a smaller scale.

Home Assistant constraints that shape this task (keep it viable):
- The button label is controlled by the `last_step` argument of `async_show_form`: the frontend shows "Next" when `last_step=False` and "Submit" otherwise. This is supported natively.
- HA data-entry flows have NO native "Back" button. Going back must be modelled inside the flow itself (e.g. an optional "go back" control on the form, or a menu step via `async_show_menu`). The chosen approach and its UX trade-off must be recorded in the implementation plan.
- Whether `device` is the last step depends on the camera toggle on that same form and on detected relays, so the label cannot react live to the toggle; a best-effort label based on current state is acceptable if documented.

Reconfigure and reauth are single-step flows and are out of scope.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 In the options flow, every step that is followed by another step shows "Next"; the step that saves the options shows "Submit" (asserted via `last_step` in unit tests for camera on/off and 0/1/2 detected relays)
- [ ] #2 In the initial setup flow, the `user` step shows "Next" and the final `device` step shows "Submit"
- [ ] #3 From every options-flow step after the first (camera, each relay) the user can return to the previous step without leaving the flow; values already entered in this flow session are pre-filled when going back and forward again
- [ ] #4 Going back never persists partial options: options are saved only by the final step, and a relay screen revisited after going back is not counted twice
- [ ] #5 Going back from the `device` step of the initial setup flow to the `user` step is possible and keeps host/port/username pre-filled; connection is re-validated on the next submit
- [ ] #6 Any new form fields or menu options are translated in `strings.json` and all `translations/{en,de,cs}.json`; `validate.py` and the full unit test suite are green
- [ ] #7 E2E test drives the options flow through the HA flow REST API on staging, asserts the `last_step` values and a back navigation, and leaves the saved options unchanged (flow aborted or original options restored); no relay switching
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Detect relays once in async_step_init (also used for best-effort last_step label on the device step; documented limitation: label cannot react live to the camera toggle).
2. last_step on async_show_form: options device=False when camera enabled or relays detected, camera=False when relays follow, relay=True only on the last relay; setup flow user=False, device stays last.
3. Back navigation modelled as a 'go_back' boolean at the bottom of every form after the first (options: camera + each relay; setup: device). Trade-off: an extra checkbox per form instead of extra menu screens via async_show_menu — chosen because it adds no extra screens/clicks and is trivially testable; recorded here per task requirements.
4. Prefill on revisit: defaults resolve session values (self._data / relay inputs) -> entry.options -> entry.data -> static default.
5. Relay inputs keyed by relay_number in a dict; current relay index tracked in an attribute (HA re-calls async_step_relay without relay_index). Revisiting a relay replaces, never appends twice; options saved only by the final step.
6. Unit tests: last_step matrix (camera on/off x 0/1/2 relays), back navigation with prefill, no double-count, setup-flow back to user with revalidation.
7. Translations for the new go_back field in strings.json + en/de/cs; validate.py + full unit suite green.
8. E2E test driving the options flow via the HA flow REST API on staging: asserts last_step values and a back navigation, leaves saved options unchanged; no relay switching.
<!-- SECTION:PLAN:END -->
