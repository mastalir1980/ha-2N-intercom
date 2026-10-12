---
id: TASK-21.5
title: Rebase mastalir1980-revize-pull-requestu onto main and land it
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-12 07:12'
updated_date: '2026-10-12 11:14'
labels:
  - git
  - config-flow
  - auth
dependencies:
  - TASK-21.4
references:
  - custom_components/2n_intercom/config_flow.py
  - custom_components/2n_intercom/coordinator.py
  - custom_components/2n_intercom/__init__.py
  - custom_components/2n_intercom/api.py
parent_task_id: TASK-21
priority: medium
type: chore
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`origin/mastalir1980-revize-pull-requestu` (base 1.3.1, 4 behind / 4 ahead) carries work that main does not have:
- `e42bb45`: tolerate transient auth errors before triggering reauth (main reauths on the first 401)
- `fe158c1`: hassfest fixes incl. `CONFIG_SCHEMA` (missing in main `__init__.py`); the translation-placeholder part may duplicate main's `b463fe1`
- `46d6350`: preserve HA sessions and startup reauth during auth recovery
- `8dd8b6c`: draft-preserving back navigation in the setup wizard

Conflicts measured with `git merge-tree`: 8 hunks against main, 59 against main+TASK-14/15 (`config_flow.py`, `strings.json`, the three translations, `tests/test_config_flow.py`, `tests/test_init.py`, `README.md`, `CHANGELOG.md`). TASK-14 introduced `CONF_GO_BACK`-based back navigation for the options flow. The setup-wizard back navigation must reuse that mechanism, not add a second one.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Auth-recovery changes (e42bb45, 46d6350) land as their own branch/PR with their unit tests, on top of current main
- [x] #2 `CONFIG_SCHEMA` is declared and hassfest passes; duplicate placeholder changes already in main are dropped
- [ ] #3 Setup-wizard back navigation lands as a second branch/PR, sharing the TASK-14 back-navigation helper/constants; strings and all three translations stay in sync
- [ ] #4 Version stays 1.4.x (no version/CHANGELOG bump outside a release task)
- [ ] #5 Each PR: unit suite + `validate.py` green, `bash e2e/e2e.sh wip` green
- [ ] #6 `origin/mastalir1980-revize-pull-requestu` is deleted after both PRs are merged (with Jan's OK)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Branch A task-21.5-auth-recovery (from origin/main, main tree):
1. cherry-pick -x e42bb45 (NUM_AUTH_ERRORS tolerance + session reset), fe158c1 (CONFIG_SCHEMA; drop placeholder part already in main b463fe1), 46d6350 (session_factory, detach instead of close for HA sessions, auth retries in first refresh).
2. Keep main's allow_insecure / dual auth; keep CHANGELOG/version untouched (release task).
3. Every commit green; unit suite, validate.py, py_compile; hassfest + HACS via GitHub Actions on push.
4. Jan runs E2E on the Pi, review, Jan merges --no-ff. STOP.
Branch B task-21.5-setup-wizard-back (from main after A merged): re-implement 8dd8b6c on top of TASK-14 CONF_GO_BACK mechanism, strings + 3 translations in sync, no version/CHANGELOG.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Branch A task-21.5-auth-recovery:
- 3db8c02 = e42bb45 (clean). c7bc5dc = fe158c1 minus placeholder hunks (main already has b463fe1; strings.json/translations kept from main) + 'ensure_package(homeassistant.helpers).config_validation' line pulled forward from 46d6350 so this commit is green on its own (test_config_flow sets helpers.config_validation, so the sys.modules stub alone did not take effect). de78fef = 46d6350; conflict in api.py __init__ resolved keeping both allow_insecure and session_factory; CHANGELOG 'Unreleased / Authentication recovery' section dropped (AC4) - release task should add: tolerate transient auth failures (savek-cc PR #8), recreate HA-managed Digest sessions without closing the shared connector, auth retries within initial setup so invalid credentials still trigger reauth, CONFIG_SCHEMA declared.
- Unit suite 483 OK on HEAD and OK on each intermediate commit; validate.py OK; py_compile OK; version stays 1.4.0. Docker not running locally, hassfest checked via GitHub Actions.

Branch A E2E report 20261012-121220 (Jan, on the Pi): passed, deployed_sha 73261ae, 12 passed / 5 skipped (SIP sensor disabled, relays, test_50 TASK-8/9 not deployed); entry loaded, no auth errors. hassfest + HACS GitHub Actions green on the branch (runs 38240965530, 38240965441). AC2 checked (CONFIG_SCHEMA declared, duplicate placeholder change dropped, hassfest passes). AC1 after Jan's --no-ff merge.
<!-- SECTION:NOTES:END -->
