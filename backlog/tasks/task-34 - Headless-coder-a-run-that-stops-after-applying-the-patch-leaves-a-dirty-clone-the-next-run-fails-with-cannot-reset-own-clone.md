---
id: TASK-34
title: >-
  Headless coder: a run that stops after applying the patch leaves a dirty
  clone, the next run fails with "cannot reset own clone"
status: Done
assignee:
  - '@copilot-mac'
created_date: '2026-10-14 14:44'
updated_date: '2026-10-15 13:46'
labels:
  - agent
  - infra
  - manual-path
dependencies: []
references:
  - tools/coder/run-task.sh
  - tools/coder/README.md
priority: high
type: bug
ordinal: 42000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Evidence (ha2n-task-status --list on the VM, 14 Oct 2026): run 20261013-214615-TASK-27 stopped with "change touches protected paths: e2e/.env.example"; the next run 20261013-222154-TASK-31 stopped at once with "cannot reset own clone" (no Copilot call, no cost). Hypothesis (to confirm from run.log and git status of /var/lib/ha2n-coder/repo): publish() applies the patch with git apply --index and then stop()s on the protected-path check (also on the symlink, binary and size checks) without cleaning, so the staged e2e/.env.example stays in the clone; main then changed the same file (9c298a7), and the next run's first step `git checkout -q --detach origin/main && git reset --hard && git clean -qfdx` (run-task.sh:69) refuses the checkout because staged changes would be overwritten. Effect: after any stop in publish() the coder is blocked for every later task until someone cleans the clone by hand. Workaround until fixed: as root remove /var/lib/ha2n-coder/repo (the next run clones again).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The start of every run brings the clone to a clean origin/main even if a previous run left staged, modified or untracked files on any branch (reset/clean before the checkout, or a forced checkout)
- [x] #2 A stop after git apply in publish() (protected path, symlink, binary, size) leaves the clone clean
- [x] #3 Stub simulation: a run stopped on a protected path, then main changes the same file, then the next run proceeds past the ready check; bash -n clean
- [x] #4 tools/coder/README.md (Czech) mentions the recovery command for a broken clone
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. In tools/coder/run-task.sh, reset and clean the owned clone before a forced detached checkout of origin/main, then reset/clean against origin/main.
2. Add stop_clean for every publish() stop after git apply, preserving all existing checks and their order; report cleanup failures explicitly.
3. Keep the approved hermetic unittest harness under tools/coder/tests/: temporary directories, local bare origin, PATH stubs, no real tokens/network/VM, and clean skips without Bash 4+ or flock. Per Jan's hardening request, before changing PATH reject any set HA2N_CODER_TEST_ROOT (including an empty value) when absolute /usr/bin/id -un identifies ha2n-coder. Fail closed if identity lookup fails. Keep the existing user check unconditional. Test the production refusal by sourcing the unchanged script in an isolated Bash shell with an absolute-name id function stub, without adding another production environment seam; skip the harness when actually running as the production OS user.
4. Keep coverage of protected rejection followed by upstream changes and the next ready check, all clone-cleanup cases and allowed patch limits. Add guard regressions and the requested Czech README sentence about production-user refusal.
5. Run the targeted hermetic suite, bash -n and git diff --check. The previous full integration validation remains green; required staging E2E is blocked by absent worktree configuration. Reinstall on the VM after merge. Protected paths, token handling and the never-merge rule remain unchanged.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Repository inspection confirms the failure: startup checks out origin/main before discarding previous staged changes, and publish() rejection paths stop without cleanup. The TASK-23 notes describe a container-only stub simulation, but no simulation harness is tracked in this checkout. Implementation-plan step 3 therefore needs confirmation: add a persistent local-git/stub regression test in tests/test_coder_run_task.py rather than extend a missing harness. Protected paths, token handling, and the never-merge behavior will remain unchanged.

Jan approved a new persistent regression harness specifically in tools/coder/tests/ (not tests/), with hermetic local Git/stub execution, Bash 4+/flock skip behavior, and environment-only test seams stripped by sudo env_reset. No simulation harness from TASK-23 will be assumed.

Implemented startup reset/clean before forced checkout of origin/main, followed by an explicit reset to origin/main. Added stop_clean to every publish() stop after git apply, including apply/commit/push failures; cleanup failures retain an explicit stop reason. Added the approved environment-only temporary-root seam without bypassing the user check; protected-path checks/order, token wrappers and never-merge behavior are unchanged. Added tools/coder/tests/test_run_task.py with full-orchestrator local-origin/PATH-stub coverage, and documented recovery/testing in the Czech runbook.

Verification on Python 3.14: all 12 hermetic coder regressions passed, including protected rejection -> upstream edit of the same file -> next run ready; dirty branch/detached startup with staged, unstaged, untracked and ignored leftovers; symlink/mode/binary/size/apply/commit rejection cleanup; and an accepted patch at exactly 40 files / 2500 lines pushed only to the temporary local origin. Bash 3.x skip was observed before installing local Bash 5/flock prerequisites; missing-flock skip was verified separately. Full integration suite: 587 tests passed; validate.py, integration/test py_compile, bash -n tools/coder/*.sh and git diff --check passed.

Completion gate blocked: bash e2e/e2e.sh wip exited before running tests with 'run e2e/e2e.sh setup first'. This isolated worktree has neither e2e/.venv nor e2e/.env. No staging/production/device operation ran, and no credentials were read or copied. The empty report artifacts from the preflight attempt were removed. Leave TASK-34 In Progress and acceptance boxes unchecked until the required staging E2E gate is green. No commit, push or VM reinstall performed; reinstall tools/coder/install-vm.sh after merge.

Jan requested one pre-commit hardening change: before PATH is changed, reject HA2N_CODER_TEST_ROOT for the actual production account using absolute /usr/bin/id -un, exit 2 with the exact requested message, add a regression and one README sentence. No commit or push was requested. The regression can simulate the absolute id in a sourced test-only Bash shell, so no extra runtime identity override will be introduced.

Hardening implemented: before PATH changes, any set HA2N_CODER_TEST_ROOT (including an empty value) now checks /usr/bin/id -un and exits 2 with 'test override refused for the production user' for ha2n-coder. Identity lookup failures also fail closed with an explicit error. No configurable identity executable or additional runtime bypass was added. Tests mock absolute id only inside a sourced, isolated Bash process, with a conflicting PATH stub to prove the guard runs before PATH-dependent work; the harness skips when actually run as the production OS user. Added the requested README sentence. All 14 hermetic regressions, bash -n tools/coder/*.sh and git diff --check passed. Existing E2E setup blocker and In Progress status remain unchanged; no commit or push performed.

2026-10-15 (Claude): review of 922835b before merge: start-of-run reset/clean before a forced detached checkout of origin/main; every publish() stop after git apply goes through stop_clean; test override HA2N_CODER_TEST_ROOT is refused when /usr/bin/id says ha2n-coder, and sudoers has no SETENV/env_keep. 12 hermetic tests in tools/coder/tests passed on bash 5.1 + flock (Linux), bash -n clean. PR #42 checks green on 922835b (e2e-pi, hassfest/HACS validate). Merged 2026-10-15 before the closing commit, so closed here in a backlog PR. VM reinstall (install-vm.sh) still to do, together with TASK-33.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
run-task.sh now cleans the coder's own clone before checking out origin/main and after every rejected patch (stop_clean), so a stopped run no longer breaks the next one. Verified by 12 hermetic regression tests in tools/coder/tests (incl. protected-path stop -> main edits the same file -> next run passes the ready check), bash -n and green PR checks on #42. README documents the recovery command and how to run the tests.
<!-- SECTION:FINAL_SUMMARY:END -->
