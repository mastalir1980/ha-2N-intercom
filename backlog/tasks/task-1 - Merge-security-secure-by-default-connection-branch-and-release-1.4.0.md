---
id: TASK-1
title: Merge security/secure-by-default-connection branch and release 1.4.0
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-08-30 09:27'
updated_date: '2026-10-11 18:28'
labels:
  - security
  - release
dependencies: []
references:
  - docs/IMPROVEMENTS.md
priority: high
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The branch security/secure-by-default-connection implements security items S1-S3 from docs/IMPROVEMENTS.md (TLS verify-first auto-detection, HTTP as last resort with warning, Basic-auth refusal over plaintext HTTP with allow_insecure opt-in), including tests and translations. Merge it to main before it goes stale, bump version, update CHANGELOG.md and release 1.4.0.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Branch merged to main with all tests passing (python3 -m unittest discover -s tests -t tests)
- [x] #2 validate.py passes
- [x] #3 manifest.json version bumped to 1.4.0 and CHANGELOG.md updated
- [ ] #4 GitHub release/tag 1.4.0 created
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Verify the existing security changes and complete only release-related gaps; exclude unrelated work in progress.
2. Run unit tests, manifest validation, compilation, and the read-only staging E2E pipeline; resolve or report blockers before publishing.
3. Bump the integration to 1.4.0, update release notes, commit TASK-1 changes, and merge to main via a pull request.
4. Publish the v1.4.0 tag and GitHub release, verify remote artifacts, and record the completed acceptance criteria.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Pre-release inspection found that allow_insecure was exposed but not forwarded to reconfigure, reauth, or directory API clients. Complete the option wiring and regression coverage before publishing; keep behavioral opt-in in entry.options and connection identity in entry.data.

Release validation 2026-10-11: 452 unittest tests passed; validate.py passed with manifest 1.4.0; py_compile and Pyright passed (0 errors). Read-only staging E2E report e2e/reports/20261011-202652: 11 passed, 2 skipped (disabled SIP sensor, physical relay test intentionally excluded). An initial SSH no-route failure was transient; independent SSH/HTTP checks and the full retry succeeded. Added request-path and config-flow regressions for secure defaults, reconfigure/reauth/directory opt-in propagation, and option persistence. Merge and published tag/release criteria remain pending until verified remotely.
<!-- SECTION:NOTES:END -->
