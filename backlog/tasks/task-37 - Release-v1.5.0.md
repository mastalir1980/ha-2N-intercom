---
id: TASK-37
title: Release v1.5.0
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-15 12:13'
updated_date: '2026-10-22 13:30'
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
  - TASK-51
  - TASK-67
  - TASK-68
  - TASK-69
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
- [ ] #1 custom_components/2n_intercom/manifest.json version is 1.5.0 [unit]
- [ ] #2 CHANGELOG.md has a "## 1.5.0 - <date>" section written for users (what changed and what they may need to do), grouped by Features / Fixes / Docs, built from the tasks of milestone v1.5.0 and the commits since v1.4.0; no internal pipeline/tooling changes [unit]
- [ ] #3 README and INSTALLATION.md mention every new user-visible option, entity and service from the milestone (check, fix gaps) [unit]
- [ ] #4 Full unit suite, validate.py and py_compile green; PR check e2e-pi green [e2e]
- [ ] #5 CHANGELOG 1.5.0 has a Security section marked as a breaking change built from the release note in the TASK-67 final summary (Basic only over verified HTTPS, unverified HTTPS counts as insecure, upgrade path via Reconfigure > Allow insecure connection or Digest/trusted certificate), and it states that the 1.4.0 rule "Basic stays enabled over HTTPS" no longer applies [unit]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. backlog task list -m v1.5.0 --plain and git log --oneline v1.4.0..origin/main -- custom_components: list user-facing changes.
2. Write the CHANGELOG section (style of the 1.4.0 entry), bump manifest.json.
3. Check README/INSTALLATION for each new option/entity/service; add what is missing.
4. Run the local gates. Do not create tags or releases (Jan does that after the merge).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-67 (merged in PR #99) changed the Basic-auth rule from 1.4.0: Basic is no longer sent over HTTPS with an unverified certificate. The 1.4.0 CHANGELOG line saying the fallback stays enabled over HTTPS is now outdated; the 1.5.0 section must carry the copy-ready release note from the TASK-67 final summary and say that the 1.4.0 rule is superseded. Do not rewrite the published 1.4.0 section.

Pre-release gate met on 2026-10-22: all milestone tasks Done; manual e2e.sh relays run: 22 passed, 2 skipped as expected (SIP sensor, unconfigured IO outputs); relays and grant_access pass.
<!-- SECTION:NOTES:END -->
