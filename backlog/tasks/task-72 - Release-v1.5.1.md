---
id: TASK-72
title: Release v1.5.1
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-24T08:27:00Z'
updated_date: '2026-10-25 15:39'
labels:
  - release
milestone: m-2
dependencies:
  - TASK-71
references:
  - CHANGELOG.md
  - custom_components/2n_intercom/manifest.json
priority: high
type: task
ordinal: 77000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Patch release for issue #105 (log subscription rejected on devices that do not support every base event, e.g. 2N IP Uni). Decided with Jan on 2026-10-24: ship the fix as 1.5.1 right after it is merged and verified, without waiting for v1.6.0. Release flow as for TASK-37: this task bumps the version and writes the changelog, Jan merges it, creates the GitHub release/tag and archives the milestone. No relay run is needed for this patch unless the diff touches relay code.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 custom_components/2n_intercom/manifest.json version is 1.5.1 [unit]
- [ ] #2 CHANGELOG.md has a "## 1.5.1 - <date>" section above 1.5.0 written for users, with a Fixes entry for the log subscription on devices such as the 2N IP Uni; the published 1.5.0 section is unchanged [unit]
- [ ] #3 Full unit suite, validate.py and py_compile green; PR check e2e-pi green [e2e]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Bump custom_components/2n_intercom/manifest.json from 1.5.0 to 1.5.1.
2. Add a dated 1.5.1 Fixes section above 1.5.0 in CHANGELOG.md, describing the TASK-71 log-subscription fix for devices such as the 2N IP Uni; preserve all published sections unchanged.
3. Extend the existing manifest/changelog tests in tests/test_release.py with focused 1.5.1 release coverage.
4. Run the required full unit suite, validate.py and py_compile with Python 3.12+, record implementation notes, and commit locally on the current branch. Leave acceptance criteria unchecked and e2e-pi/finalization to the orchestrator.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Prepared patch release 1.5.1: bumped manifest.json and added the 2026-10-25 Fixes section describing the TASK-71 log-subscription fix for devices such as the 2N IP Uni (issue #105). All published changelog sections, including 1.5.0, are byte-for-byte unchanged. No runtime or relay code was changed.

Extended tests/test_release.py with test_v151_documents_log_subscription_fix to check the manifest version, changelog release order and user-facing fix details; the existing version/date consistency test remains in place.

Local gates passed with Python 3.12.15: python3 -m unittest discover -s tests -t tests (749 tests), python3 validate.py, and python3 -m py_compile custom_components/2n_intercom/*.py. API failure-path tests emitted existing mock-related RuntimeWarning messages but no test failures.

No Home Assistant/intercom or E2E commands were run on the VM. PR check e2e-pi remains for the orchestrator after pushing. Task stays In Progress and all acceptance criteria remain unchecked for independent review and orchestrator finalization.
<!-- SECTION:NOTES:END -->
