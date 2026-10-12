---
id: TASK-21.5
title: Rebase mastalir1980-revize-pull-requestu onto main and land it
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-12 07:12'
updated_date: '2026-10-12 11:24'
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
- [x] #1 Auth-recovery changes (e42bb45, 46d6350) land as their own branch/PR with their unit tests, on top of current main
- [x] #2 `CONFIG_SCHEMA` is declared and hassfest passes; duplicate placeholder changes already in main are dropped
- [x] #3 Setup-wizard back navigation lands as a second branch/PR, sharing the TASK-14 back-navigation helper/constants; strings and all three translations stay in sync
- [x] #4 Version stays 1.4.x (no version/CHANGELOG bump outside a release task)
- [x] #5 Each PR: unit suite + `validate.py` green, `bash e2e/e2e.sh wip` green
- [x] #6 `origin/mastalir1980-revize-pull-requestu` is deleted after both PRs are merged (with Jan's OK)
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

Branch B task-21.5-setup-wizard-back (from main 2d07e3b): analysis of 8dd8b6c vs main showed TASK-14/15 already landed setup-wizard back navigation (CONF_GO_BACK on config device step, last_step labels, user-step prefill), options-flow draft preservation (camera, per-relay via _relay_inputs), and HTTP API vs RTSP credential guidance. Jan decided scope for B: (a) clear stale serial number / default device name when the user goes back and the new host reports none; (b) add the missing config.error.invalid_auth string (used by reauth) to strings.json + en/cs/de; (c) document the 'Return to the previous step' option in README/INSTALLATION. NOT ported (Jan): (d) 8dd8b6c's options-flow merge of saved options for skipped steps (keep camera options when camera disabled, keep saved relays when entry not loaded) — main deliberately drops them (TASK-14). Also not ported: TYPE_CHECKING import refactor, 'HTTP API username' label wording (main already says 'API username' + guidance), CHANGELOG entry.

Branch B changes: config_flow.py user step drops CONF_SERIAL_NUMBER from the draft and resets _default_device_name when the (re)connected host reports no serial/variant (unique id then falls back to host, as for a fresh setup). config.error.invalid_auth added to strings.json + en/cs/de (text taken from 8dd8b6c). README (setup wizard + options flow) and INSTALLATION document the 'Back to the previous step' option. Tests: test_go_back_to_other_host_drops_previous_device_identity, ConfigFlowErrorStringsTests (every errors['base'] key in config_flow.py exists in config.error of all four string files); both fail on main, pass on the branch. Suite 485 OK, validate.py + py_compile OK, version 1.4.0, no CHANGELOG. Follow-up (not fixed, pre-existing): running tests/test_config_flow.py alone fails at import because config_flow.py imports .coordinator at module level and the test loader does not stub it; the full discover run works because other modules load coordinator first (8dd8b6c had moved the import under TYPE_CHECKING).

Branch A merged into main by Jan as 2d07e3b (AC1). Branch B E2E report 20261012-122042 (Jan, on the Pi): passed, deployed_sha 980277c, 12 passed / 5 skipped (SIP sensor disabled, relays, test_50 TASK-8/9 not deployed), nothing pruned. hassfest + HACS GitHub Actions green on task-21.5-setup-wizard-back. AC3/AC4/AC5 checked. Remaining: AC6 (delete origin/mastalir1980-revize-pull-requestu) only after B is merged and with Jan's explicit OK; task stays In Progress until then.

Branch B merged by Jan as 9a3f5d1. origin/mastalir1980-revize-pull-requestu deleted with Jan's explicit OK (was 8dd8b6c); the local branch of the same name is kept as a restore point.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Landed the work from origin/mastalir1980-revize-pull-requestu on top of main in two PRs. Part A (task-21.5-auth-recovery, merge 2d07e3b): cherry-picked e42bb45, fe158c1 (CONFIG_SCHEMA only; placeholder part already in main) and 46d6350 — tolerate up to 3 consecutive auth failures before reauth, recreate HA-managed Digest sessions via a session factory without closing the shared connector, auth retries within first refresh. Part B (task-21.5-setup-wizard-back, merge 9a3f5d1): TASK-14 already provided the setup/options back navigation, so only the remaining 8dd8b6c fixes were ported — stale serial/default name cleared on going back to another host, missing invalid_auth string (en/cs/de), README/INSTALLATION docs. Not ported by Jan's decision: keeping saved options for skipped options-flow steps. Version stays 1.4.0; CHANGELOG text for the release task is in the notes. Unit suite, validate.py, hassfest/HACS CI and Pi E2E (20261012-121220, 20261012-122042) green. Follow-up: tests/test_config_flow.py fails when run alone (module-level .coordinator import).
<!-- SECTION:FINAL_SUMMARY:END -->
