---
id: TASK-37
title: Release v1.5.0
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-15 12:13'
updated_date: '2026-10-23 15:45'
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
- [x] #1 custom_components/2n_intercom/manifest.json version is 1.5.0 [unit]
- [x] #2 CHANGELOG.md has a "## 1.5.0 - <date>" section written for users (what changed and what they may need to do), grouped by Features / Fixes / Docs, built from the tasks of milestone v1.5.0 and the commits since v1.4.0; no internal pipeline/tooling changes [unit]
- [x] #3 README and INSTALLATION.md mention every new user-visible option, entity and service from the milestone (check, fix gaps) [unit]
- [x] #4 Full unit suite, validate.py and py_compile green; PR check e2e-pi green [e2e]
- [x] #5 CHANGELOG 1.5.0 has a Security section marked as a breaking change built from the release note in the TASK-67 final summary (Basic only over verified HTTPS, unverified HTTPS counts as insecure, upgrade path via Reconfigure > Allow insecure connection or Digest/trusted certificate), and it states that the 1.4.0 rule "Basic stays enabled over HTTPS" no longer applies [unit]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Inventory user-facing changes from milestone v1.5.0, completed task summaries (especially TASK-67), and commits from v1.4.0 to origin/main.
2. Add the dated 1.5.0 changelog with Features / Fixes / Docs and a breaking Security section; preserve published release notes and bump manifest.json to 1.5.0.
3. Audit README.md and INSTALLATION.md against new options, entities, services and upgrade actions; fill documentation gaps without changing runtime behavior.
4. Add focused release metadata/documentation unit coverage in the existing unittest style; run the full unit suite, validate.py and py_compile. Record evidence in task notes and commit locally on the current branch; leave acceptance criteria and final status to the orchestrator, with e2e-pi pending.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-67 (merged in PR #99) changed the Basic-auth rule from 1.4.0: Basic is no longer sent over HTTPS with an unverified certificate. The 1.4.0 CHANGELOG line saying the fallback stays enabled over HTTPS is now outdated; the 1.5.0 section must carry the copy-ready release note from the TASK-67 final summary and say that the 1.4.0 rule is superseded. Do not rewrite the published 1.4.0 section.

Pre-release gate met on 2026-10-22: all milestone tasks Done; manual e2e.sh relays run: 22 passed, 2 skipped as expected (SIP sensor, unconfigured IO outputs); relays and grant_access pass.

Prepared v1.5.0 dated 2026-10-23 from the completed milestone tasks and integration/documentation commits in v1.4.0..origin/main; excluded internal pipeline/tooling changes. Copied the TASK-67 Security breaking-change release paragraph verbatim and explicitly superseded the old 1.4.0 HTTPS rule without editing published entries. Release notes cover new entities, grant_access/default user, access events, SSDP, firmware channels, doorbell/HomeKit migration, I/O safety, Called ID, snapshots, options and authentication/listener reliability.
Audited README and INSTALLATION against every milestone feature. Added the missing installation guidance, firmware entity example, camera/image toggle clarification and event-based troubleshooting. No runtime changes apart from the manifest version. Added six offline release/documentation tests in tests/test_release.py.
AC #1 evidence: manifest version is 1.5.0 (jq assertion passed), with latest dated changelog consistency covered by test_manifest_version_matches_latest_dated_changelog.
AC #2 evidence: test_v150_has_user_facing_release_groups passes for the dated Features / Fixes / Docs / Security sections; inventory came from completed milestone tasks and commits since v1.4.0.
AC #3 evidence: both guides cover new entity, option and service surfaces; the three guide coverage/safety/migration tests pass.
AC #4 local evidence: Python 3.12.15 full unittest discovery passed (744 tests), validate.py passed and integration py_compile passed. PR e2e-pi remains pending after orchestrator push. No E2E command, device interaction, tag or GitHub release was attempted. No new runtime feature was added; existing E2E coverage is unchanged.
AC #5 evidence: test_v150_security_explains_breaking_change_and_upgrade passes, including verified HTTPS, insecure self-signed HTTPS, Digest/trusted-certificate remedies, Reconfigure opt-in, setup restrictions, Repair guidance and superseding 1.4.0.
Task remains In Progress, assigned @copilot, with all acceptance criteria unchecked for the orchestrator and independent reviewer.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented by the headless coder. Checks green on 047da4540 after 0 fix round(s): e2e-pi=pass, validate=pass, validate=pass. PR: https://github.com/mastalir1980/ha-2N-intercom/pull/106. Done takes effect when the PR is merged.
AC #1: manifest.json diff changes version 1.4.0 -&gt; 1.5.0 (only runtime-dir change). tests/test_release.py::test_manifest_version_matches_latest_dated_changelog asserts manifest version equals the newest dated CHANGELOG heading; the test file passes when run from tests/ (6 tests OK). (proven)
AC #2: CHANGELOG.md has '## 1.5.0 - 2026-10-23' with Security, Features, Fixes and Docs sections in user-facing language, covering the milestone tasks and integration commits since v1.4.0 (grant_access, access events, I/O inputs/outputs, SSDP, firmware entity, doorbell event/last-ring image, Called ID, snapshot, options flow, auth recovery); no pipeline/tooling entries. The 1.4.0 section is untouched (diff only adds lines). tests/test_release.py::test_v150_has_user_facing_release_groups checks the headings. (proven)
AC #3: README.md and INSTALLATION.md diffs add SSDP discovery, image/last-ring entity, extra input/tamper sensors, direct output switches with safety warning, update entity, firmware_channel and grant_access_user options, Called ID behaviour, grant_access service and access events, snapshot size selection. tests/test_release.py::test_both_guides_cover_new_entities_options_and_service, test_both_guides_explain_direct_output_safety and test_both_guides_explain_doorbell_migration assert these terms in both guides; tests pass. (proven)
AC #4: Orchestrator confirmed the full unit suite, validate.py, py_compile and all PR checks including e2e-pi are green on this head. The diff changes only docs, the manifest version and a new offline unit test, so the e2e-pi result applies without new E2E code. (proven)
AC #5: CHANGELOG 1.5.0 begins with '### Security - Breaking change' whose first paragraph is copied verbatim from the TASK-67 final-summary release note (Basic only over verified HTTPS, unverified/self-signed counts as insecure, Digest or trusted certificate, Reconfigure &gt; Allow insecure connection). A following paragraph states it supersedes the 1.4.0 rule 'Basic stays enabled over HTTPS'. tests/test_release.py::test_v150_security_explains_breaking_change_and_upgrade asserts each of these phrases. (proven)
<!-- SECTION:FINAL_SUMMARY:END -->
