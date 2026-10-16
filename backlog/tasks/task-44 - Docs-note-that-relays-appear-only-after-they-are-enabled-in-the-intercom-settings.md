---
id: TASK-44
title: >-
  Docs: note that relays appear only after they are enabled in the intercom
  settings
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-15 16:37'
updated_date: '2026-10-16 16:09'
labels:
  - docs
milestone: m-0
dependencies:
  - TASK-43
priority: low
type: docs
ordinal: 51000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: a user who activated the relay/switch function on the intercom did not understand that the relay entities appear only after it is enabled in the intercom settings, and that without an enabled relay nothing is shown in Home Assistant. The integration creates relay entities from /api/switch/caps, which lists only enabled relays. Expected behaviour: the user documentation says that if no relay appears, the relay must first be enabled in the intercom's own administration (web interface), and that the integration cannot enable it. The options flow stays as it is.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 README.md (section on relays / the relay control entities) states that relays appear only when enabled in the intercom settings and that the integration does not enable them
- [ ] #2 INSTALLATION.md gets the same note in its troubleshooting or relay section, if such a section exists
- [ ] #3 The wording avoids mentioning admin account names or device-specific paths; uses the neutral term 'intercom settings'
- [ ] #4 validate.py green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add a note immediately after relay auto-discovery in README.md explaining that only relays enabled in the intercom settings get entities, how to enable them and reload the integration, and that the integration cannot enable them. Add one linked sentence to Initial setup.
2. Add the same prerequisite beside the switch/cover list in INSTALLATION.md and a No relay entities appear troubleshooting subsection with the Home Assistant reload location. Use neutral wording without device-specific settings paths or account names.
3. Keep this docs-only: do not change code, strings, translations, tests, or the options flow, and do not add descriptions of per-relay options.
4. Run the requested Python 3.12 local gates (full unittest suite, validate.py, py_compile), review the diff, and record implementation notes. Leave device E2E to e2e-pi, keep all criteria unchecked and the task In Progress, and commit locally on the current branch without pushing.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Updated README.md in Door / Gate / Relay control immediately after the /api/switch/caps auto-discovery bullet, and added a linked prerequisite sentence under Initial setup. Both explain that only relays enabled in the intercom settings appear, that missing relays must be enabled there before reloading the integration, and that the integration cannot enable relays.

Updated INSTALLATION.md beside the switch/cover entity list and added No relay entities appear under Troubleshooting, including the Home Assistant integration reload location. New wording uses neutral intercom settings/web-interface terminology without account names or device-specific administration paths. No code, strings, translations, options-flow behavior, or tests were changed; no new per-relay options description was added. This is documentation-only, with no runtime behavior requiring new unit or E2E tests.

Local gates passed on Python 3.12.15: full unittest discovery (624 tests), python3 validate.py, python3 -m py_compile custom_components/2n_intercom/*.py, and git diff --check. Device E2E was not run on the VM; the e2e-pi PR check remains the orchestrator gate after push. Acceptance criteria remain unchecked and status remains In Progress as required for headless execution.
<!-- SECTION:NOTES:END -->
