---
id: TASK-74
title: Release v1.6.0
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-24T08:29:00Z'
updated_date: '2026-11-21 12:36'
labels:
  - release
milestone: m-1
dependencies:
  - TASK-2.2
  - TASK-2.3
  - TASK-39
  - TASK-6
  - TASK-76
  - TASK-77
  - TASK-82
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Worktree branch task-74-release-v1-6-0 from origin/main.
2. Bump custom_components/2n_intercom/manifest.json to 1.6.0.
3. Add the '## 1.6.0 - <date>' section to CHANGELOG.md (Features / Fixes / Docs) from the implemented milestone tasks: TASK-6, TASK-82, TASK-77, TASK-39, TASK-76, TASK-2.2, TASK-2.3. Do not repeat the 1.5.2 fixes (TASK-73, TASK-12); no audio feature; no tooling changes.
4. Check README.md and INSTALLATION.md against every new option, attribute and event of the milestone; fill the gaps (INSTALLATION.md had none of the 1.6.0 options).
5. Extend tests/test_release.py with a 1.6.0 test and make the 1.5.x tests look their sections up by position below 1.6.0.
6. Full unit suite, validate.py, py_compile; PR check e2e-pi.
7. Jan: merge, GitHub release and tag v1.6.0 from main, archive the milestone.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-14: TASK-73 and TASK-12 moved to milestone v1.5.2 and ship in TASK-81 (release branch from tag v1.5.1). They stay on main, so 1.6.0 contains them too; the 1.6.0 changelog must not list them again as new fixes.

2026-11-15: TASK-79 (camera live talk) moved out of milestone v1.6.0 and put on hold: go2rtc cannot open the intercom's RTSP audio backchannel on fw 3.x (details in TASK-79). The speaker media player (TASK-78) stays in v1.6.0. The 1.6.0 changelog and README must not announce live talk.

2026-11-15 (update): TASK-78 (speaker media player) is also out of milestone v1.6.0 and on hold (decision by Jan). v1.6.0 ships no audio feature; PR 131 must not be merged for this release.

2026-11-21: prepared by Claude on Jan's explicit request in the conversation (release prepared up to his approval). Scope shipped: TASK-6, TASK-82, TASK-77, TASK-39, TASK-76, TASK-2.2, TASK-2.3. Not implemented and proposed to leave the milestone: TASK-5, TASK-7 (still need analysis), TASK-65, TASK-66 (as planned in the description); the dependency list of this task was reduced to the shipped tasks accordingly. Jan's decision is recorded by merging the Backlog change and this PR.

2026-11-21: on macOS the unit suite needs a temporary folder without a symlink in its path (TMPDIR), because event_pictures refuses a media root with a symlinked parent and the default macOS temp folder is under a symlink; plus tests/requirements.txt (Jinja2). With both: 901 tests OK. README now states the symlink rule for the media root.
<!-- SECTION:NOTES:END -->
