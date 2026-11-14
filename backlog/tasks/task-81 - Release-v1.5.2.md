---
id: TASK-81
title: Release v1.5.2
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-14 09:58'
updated_date: '2026-11-14 10:03'
labels:
  - release
  - manual-path
milestone: m-3
dependencies:
  - TASK-12
  - TASK-73
references:
  - CHANGELOG.md
  - custom_components/2n_intercom/manifest.json
  - tests/test_release.py
priority: high
type: task
ordinal: 86000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Patch release for issue #105: no camera entities on devices without a camera (TASK-73) and visible errors instead of empty entities when the device refuses API calls (TASK-12).

Decided with Jan on 2026-11-14: 1.5.2 is a bugfix-only release cut from a release branch that starts at tag v1.5.1, not from main, because main already carries unreleased v1.6.0 features that are still in To Test. The two fixes are cherry-picked from main (commits 29ed316 and 1914bd1) onto that branch and adapted where they touch code that only exists on main.

Flow: branch release-1.5 from tag v1.5.1 is the PR base; the work branch task-<id>-release-v1-5-2 carries the cherry-picks, the version bump and the changelog. Jan merges the PR into release-1.5 and creates the GitHub release/tag v1.5.2 from release-1.5. The changelog section is then forward-ported to main in a separate docs change so main's CHANGELOG.md lists 1.5.2. No relay run is needed: the diff does not touch relay commands.

The headless coder cannot run this task (it only branches from main), hence manual-path.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The release branch contains the fixes of TASK-73 and TASK-12 and no v1.6.0 feature: its diff against tag v1.5.1 touches only the two fixes, their tests and docs, manifest.json and CHANGELOG.md [unit]
- [ ] #2 custom_components/2n_intercom/manifest.json version is 1.5.2 [unit]
- [ ] #3 CHANGELOG.md has a "## 1.5.2 - <date>" section above 1.5.1 written for users, with a Fixes entry for each of the two bugs; published sections are unchanged [unit]
- [ ] #4 Full unit suite, validate.py and py_compile are green on the release branch [unit]
- [ ] #5 E2E on the release branch build is green on the E2E intercom (e2e.sh run on the branch or PR check e2e-pi) [e2e]
- [ ] #6 Jan creates the GitHub release and tag v1.5.2 from release-1.5 and archives the milestone [jan]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Branch release-1.5 at tag v1.5.1 (PR base) and work branch task-81-release-v1-5-2.
2. Cherry-pick 29ed316 (TASK-73) and 1914bd1 (TASK-12); drop the parts that belong to v1.6.0 code (KeyPressed ring, MJPEG stream E2E test) and keep the 1.5.1 switch-caps polling.
3. Bump manifest.json to 1.5.2, add the 1.5.2 changelog section, extend tests/test_release.py.
4. Full unit suite, validate.py, py_compile; E2E on the branch.
5. Jan merges into release-1.5, tags v1.5.2 from it; forward-port the changelog section to main.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-14 (Claude): worktree branch task-81-release-v1-5-2 built locally from tag v1.5.1 (not pushed yet): f495a25 TASK-73, b7d3f78 TASK-12, e8ec3c1 version bump + changelog. Conflicts resolved by hand: coordinator.py (no KeyPressed ring handler on 1.5.1; switch caps are still refreshed on every poll there, now skipped only when the device answered code 1), e2e/tests/test_10_entities.py (the MJPEG stream test from main is not included). Diff against v1.5.1: 21 files, only the two fixes with their tests and docs, manifest.json, CHANGELOG.md. Local checks: 774 unit tests OK (venv with tests/requirements.txt), validate.py green, py_compile OK. E2E not run on this branch yet.
<!-- SECTION:NOTES:END -->
