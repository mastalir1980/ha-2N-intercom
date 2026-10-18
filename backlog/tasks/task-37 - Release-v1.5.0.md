---
id: TASK-37
title: Release v1.5.0
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-15 12:13'
updated_date: '2026-10-18 13:11'
labels:
  - release
milestone: m-0
dependencies:
  - TASK-15
  - TASK-31
  - TASK-41
  - TASK-43
  - TASK-44
  - TASK-45
  - TASK-47
  - TASK-48
  - TASK-49
  - TASK-53
  - TASK-54
  - TASK-55
references:
  - CHANGELOG.md
  - custom_components/2n_intercom/manifest.json
  - README.md
priority: high
type: task
ordinal: 45000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Release of milestone v1.5.0: everything user-facing merged to main since v1.4.0 (2026-10-11). Users get it only through the GitHub release (HACS offers releases, not main). Release flow agreed with Jan on 15 Oct 2026: PRs merge to main continuously; a version is closed when every task of its milestone is Done (To Test items verified by Jan on the real device, plus one manual e2e.sh relays run at the door); then this task bumps the version and writes the changelog, Jan merges it and creates the GitHub release/tag, and the milestone is archived.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 custom_components/2n_intercom/manifest.json version is 1.5.0
- [ ] #2 CHANGELOG.md has a "## 1.5.0 - <date>" section written for users (what changed and what they may need to do), grouped by Features / Fixes / Docs, built from the tasks of milestone v1.5.0 and the commits since v1.4.0; no internal pipeline/tooling changes
- [ ] #3 README and INSTALLATION.md mention every new user-visible option, entity and service from the milestone (check, fix gaps)
- [ ] #4 Full unit suite, validate.py and py_compile green; PR check e2e-pi green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. backlog task list -m v1.5.0 --plain and git log --oneline v1.4.0..origin/main -- custom_components: list user-facing changes.
2. Write the CHANGELOG section (style of the 1.4.0 entry), bump manifest.json.
3. Check README/INSTALLATION for each new option/entity/service; add what is missing.
4. Run the local gates. Do not create tags or releases (Jan does that after the merge).
<!-- SECTION:PLAN:END -->
