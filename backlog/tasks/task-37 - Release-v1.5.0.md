---
id: TASK-37
title: Release v1.5.0
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-15 12:13'
updated_date: '2026-10-19 18:46'
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
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Inventory completed v1.5.0 milestone tasks and integration commits since v1.4.0; compare the shipped options, entities, services and migration requirements with README.md and INSTALLATION.md.
2. Add the user-facing 1.5.0 changelog under Features / Fixes / Docs, bump manifest.json to 1.5.0, and fill documentation gaps without changing runtime behavior.
3. Add focused release regression coverage in the existing unittest style, then run the full unit suite, validate.py and py_compile with python3.
4. Record implementation evidence and pending e2e-pi in task notes, leave acceptance criteria unchecked and status In Progress, and commit locally on the supplied task branch without pushing or creating a tag/release.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented release preparation from every completed v1.5.0 milestone task and integration commits in v1.4.0..origin/main, including the earlier access-control, last-ring image and IO work as well as the newer discovery, firmware and doorbell migration changes. All other milestone tasks are Done.

AC #1: manifest.json now declares 1.5.0; tests/test_release.py checks that the latest dated changelog version matches the manifest.
AC #2: CHANGELOG.md has a 2026-10-19 release section grouped into Features / Fixes / Docs, covering user-facing changes only. The breaking doorbell migration, HomeKit pairing, firmware installation boundary and latching-output warning are explicit; no pipeline/tooling changes are listed.
AC #3: Audited shipped UI fields, entities and services against both user guides. INSTALLATION.md now covers SSDP/IP changes, last-ring image, all IO inputs/tamper ports, disabled-by-default latching outputs, firmware entity/channel, default grant-access user, grant_access usage/privileges and access-event diagnostics. README adds snapshot selection and the firmware entity example. Both service guides now show the actual config_entry_id data field rather than unsupported target syntax. Four offline release/documentation tests cover metadata, changelog topics, new surfaces and migration/safety warnings.
AC #4: Python 3.12.15 full unit suite passed (708 tests); python3 validate.py and python3 -m py_compile custom_components/2n_intercom/*.py passed. API failure-path test mocks emitted RuntimeWarnings; no runtime code beyond the manifest version was changed. e2e-pi remains pending for the orchestrator after push; no HA/intercom or E2E commands were run here.

Acceptance criteria remain unchecked and status remains In Progress for independent review and orchestrator finalization. No protected paths, tags, GitHub releases or milestone archive were changed.
<!-- SECTION:NOTES:END -->
