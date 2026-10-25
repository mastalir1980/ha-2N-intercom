---
id: TASK-74
title: Release v1.6.0
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-24T08:29:00Z'
labels:
  - release
milestone: m-1
dependencies:
  - TASK-39
  - TASK-73
  - TASK-12
  - TASK-2.2
  - TASK-2.3
  - TASK-6
  - TASK-5
  - TASK-7
references:
  - CHANGELOG.md
  - custom_components/2n_intercom/manifest.json
  - README.md
  - INSTALLATION.md
priority: high
type: task
ordinal: 81000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Release of milestone v1.6.0 ("works on every 2N device, access and security events in automations"). Scope agreed with Jan on 2026-10-24 (docs/ROADMAP-NAVRH.md). Release flow as for TASK-37: all milestone tasks Done (To Test items verified by Jan, one manual e2e.sh relays run), then this task bumps the version and writes the changelog, Jan merges, creates the GitHub release/tag and archives the milestone. TASK-65/66 (firmware Install) are not dependencies on purpose: if they are not Done when everything else is, they move to the next milestone instead of blocking this release.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 custom_components/2n_intercom/manifest.json version is 1.6.0 [unit]
- [ ] #2 CHANGELOG.md has a "## 1.6.0 - <date>" section written for users, grouped by Features / Fixes / Docs, built from the tasks of milestone v1.6.0 and the commits since v1.5.1; no internal pipeline/tooling changes; published sections unchanged [unit]
- [ ] #3 README and INSTALLATION.md mention every new user-visible option, entity, event and Repair issue from the milestone (check, fix gaps) [unit]
- [ ] #4 Full unit suite, validate.py and py_compile green; PR check e2e-pi green [e2e]
<!-- AC:END -->
