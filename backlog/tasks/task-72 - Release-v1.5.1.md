---
id: TASK-72
title: Release v1.5.1
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-24T08:27:00Z'
updated_date: '2026-10-24T08:27:00Z'
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
1. Bump manifest.json to 1.5.1.
2. Add the 1.5.1 CHANGELOG section (Fixes) from the final summary of TASK-71; do not touch the 1.5.0 section.
3. Extend tests/test_release.py only if it checks the manifest/changelog version pair.
4. Run the unit suite, validate.py, py_compile.
<!-- SECTION:PLAN:END -->
