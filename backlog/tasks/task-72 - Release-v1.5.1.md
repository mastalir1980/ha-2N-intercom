---
id: TASK-72
title: Release v1.5.1
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-24T08:27:00Z'
updated_date: '2026-10-25 15:42'
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
- [x] #1 custom_components/2n_intercom/manifest.json version is 1.5.1 [unit]
- [x] #2 CHANGELOG.md has a "## 1.5.1 - <date>" section above 1.5.0 written for users, with a Fixes entry for the log subscription on devices such as the 2N IP Uni; the published 1.5.0 section is unchanged [unit]
- [x] #3 Full unit suite, validate.py and py_compile green; PR check e2e-pi green [e2e]
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

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented by the headless coder. Checks green on 2b96e1176 after 0 fix round(s): e2e-pi=pass, validate=pass, validate=pass. PR: https://github.com/mastalir1980/ha-2N-intercom/pull/109. Done takes effect when the PR is merged.
AC #1: Diff changes custom_components/2n_intercom/manifest.json version from 1.5.0 to 1.5.1; tests/test_release.py::test_v151_documents_log_subscription_fix asserts manifest version == 1.5.1 and test_manifest_version_matches_latest_dated_changelog checks the manifest/changelog pair. Orchestrator reports the unit suite is green. (proven)
AC #2: CHANGELOG.md diff only adds a '## 1.5.1 - 2026-10-25' section with '### Fixes' above 1.5.0, describing the log subscription fix for devices such as the 2N IP Uni (#105) in user-facing wording; no lines of the 1.5.0 section appear in the diff (unchanged). test_v151_documents_log_subscription_fix checks release order [1.5.1, 1.5.0] and the Fixes content; the date format is validated by the existing consistency test. (proven)
AC #3: Orchestrator confirmed unit suite, validate.py, py_compile and PR check e2e-pi are green on this head. Diff touches only CHANGELOG.md, manifest.json, tests/test_release.py and the task file; no runtime or relay code changed, and no test was weakened (only a test was added). (proven)
<!-- SECTION:FINAL_SUMMARY:END -->
