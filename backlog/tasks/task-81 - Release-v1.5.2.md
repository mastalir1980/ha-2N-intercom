---
id: TASK-81
title: Release v1.5.2
status: To Test
assignee:
  - '@claude'
created_date: '2026-11-14 09:58'
updated_date: '2026-11-15 11:47'
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
- [x] #1 The release branch contains the fixes of TASK-73 and TASK-12 and no v1.6.0 feature: its diff against tag v1.5.1 touches only the two fixes, their tests and docs, manifest.json and CHANGELOG.md [unit]
- [x] #2 custom_components/2n_intercom/manifest.json version is 1.5.2 [unit]
- [x] #3 CHANGELOG.md has a "## 1.5.2 - <date>" section above 1.5.1 written for users, with a Fixes entry for each of the two bugs; published sections are unchanged [unit]
- [x] #4 Full unit suite, validate.py and py_compile are green on the release branch [unit]
- [x] #5 E2E on the release branch build is green on the E2E intercom (e2e.sh run on the branch or PR check e2e-pi) [e2e]
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

Release PR: https://github.com/mastalir1980/ha-2N-intercom/pull/128 (task-81-release-v1-5-2 -> release-1.5, base at tag v1.5.1). Checks on head e8ec3c1: HACS validate pass, hassfest validate pass. The PR check e2e-pi is skipped by design for PRs whose base is not the default branch; E2E was run by workflow_dispatch on commit e8ec3c1: passed, 22 passed, 0 failed, 1 skipped, read-only, no relays (https://github.com/mastalir1980/ha-2N-intercom/actions/runs/43593998307). Unit suite 774 tests OK and validate.py green locally. Open: merge, GitHub release and tag v1.5.2 from release-1.5, milestone archive, forward-port of the 1.5.2 changelog section to main.

2026-11-15 (Claude): Jan merged PR #128 into release-1.5 (merge commit a533532) and asked Claude to publish the release. GitHub release and tag v1.5.2 created from release-1.5 at a533532, marked latest: https://github.com/mastalir1980/ha-2N-intercom/releases/tag/v1.5.2. Forward-port of manifest version, CHANGELOG section and release test to main: PR https://github.com/mastalir1980/ha-2N-intercom/pull/129 (850 unit tests OK, validate.py green locally). Milestone v1.5.2 is not archived: TASK-73 is still To Test (manual-close, waiting for the reporter of issue #105).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
v1.5.2 released from release-1.5 (tag v1.5.1 + TASK-73 + TASK-12 + version bump).
AC #1: proven - diff v1.5.1..e8ec3c1 is 21 files: the two fixes, their tests and docs, manifest.json, CHANGELOG.md.
AC #2: proven - manifest.json on release-1.5 has version 1.5.2; tests/test_release.py asserts it.
AC #3: proven - CHANGELOG.md section '## 1.5.2 - 2026-11-14' above 1.5.1 with Fixes entries; tests/test_release.py test_v152_documents_camera_and_refused_call_fixes.
AC #4: proven - 774 unit tests OK, validate.py and py_compile green on e8ec3c1; HACS and hassfest checks pass on PR #128.
AC #5: proven - E2E on the Pi via workflow_dispatch on e8ec3c1: 22 passed, 0 failed, 1 skipped (run 43593998307).
AC #6: manual - release and tag v1.5.2 exist (created by Claude on Jan's instruction); milestone archive is still open and is Jan's call while TASK-73 is To Test.
<!-- SECTION:FINAL_SUMMARY:END -->
