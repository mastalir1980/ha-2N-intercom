---
id: TASK-1
title: Merge security/secure-by-default-connection branch and release 1.4.0
status: Done
assignee:
  - '@copilot'
created_date: '2026-08-30 09:27'
updated_date: '2026-10-11 18:32'
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
- [x] #1 Branch merged to main with all tests passing (python3 -m unittest discover -s tests -t tests)
- [x] #2 validate.py passes
- [x] #3 manifest.json version bumped to 1.4.0 and CHANGELOG.md updated
- [x] #4 GitHub release/tag 1.4.0 created
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

GitHub HACS validation passed. Hassfest exposed a pre-existing invalid translation placeholder: single quotes around {reason} in invalid_hangup_reason. Removed only those quotes in strings.json and all EN/CS/DE translations to unblock release validation; the separate CONFIG_SCHEMA warning is not part of TASK-1.

Final release-tree verification after the translation fix: staging E2E report 20261011-202945 passed (11 passed, 2 intentionally skipped); its prerequisite full unittest suite, validate.py, and py_compile also passed.

Published artifacts: https://github.com/mastalir1980/ha-2N-intercom/pull/15 and https://github.com/mastalir1980/ha-2N-intercom/releases/tag/v1.4.0. Release is public (not draft or prerelease). Unrelated local files remain untouched and uncommitted.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Released 1.4.0 with verified-TLS-first discovery, guarded plaintext Basic auth, complete opt-in persistence, translations, and upgrade guidance. Verified by 452 unit tests, validate.py, py_compile, Pyright, HACS/hassfest, and read-only staging E2E (11 passed, 2 skipped; report 20261011-202945). PR #15 merged to main as f3eacea7f110ac538f604566d6a5421e645a953e. Published GitHub release v1.4.0 and verified its tag targets that merge commit and its manifest contains 1.4.0. Completion metadata is recorded after publication so merge/release acceptance criteria reflect observed results, not anticipated actions.
<!-- SECTION:FINAL_SUMMARY:END -->
