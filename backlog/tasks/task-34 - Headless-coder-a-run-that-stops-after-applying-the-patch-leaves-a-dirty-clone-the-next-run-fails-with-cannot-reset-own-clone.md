---
id: TASK-34
title: >-
  Headless coder: a run that stops after applying the patch leaves a dirty
  clone, the next run fails with "cannot reset own clone"
status: To Do
assignee:
  - '@copilot-mac'
created_date: '2026-10-14 14:44'
updated_date: '2026-10-14 14:44'
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
- [ ] #1 The start of every run brings the clone to a clean origin/main even if a previous run left staged, modified or untracked files on any branch (reset/clean before the checkout, or a forced checkout)
- [ ] #2 A stop after git apply in publish() (protected path, symlink, binary, size) leaves the clone clean
- [ ] #3 Stub simulation: a run stopped on a protected path, then main changes the same file, then the next run proceeds past the ready check; bash -n clean
- [ ] #4 tools/coder/README.md (Czech) mentions the recovery command for a broken clone
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. run-task.sh:69: change the clean-up order to `git reset -q --hard && git clean -qfdx && git checkout -q --detach -f origin/main && git reset -q --hard origin/main && git clean -qfdx` (or equivalent) so leftovers of any earlier run never block the checkout.
2. publish(): after git apply --index, every stop path first runs `git reset -q --hard && git clean -qfdx` (a small helper, e.g. stop_clean). Keep the existing checks and their order unchanged.
3. Extend the existing stub simulation from TASK-23 with the scenario from AC #3.
4. README: one line with the recovery command (sudo rm -rf /var/lib/ha2n-coder/repo).
Must not change: the protected-path list, token handling, the never-merge rule. Reinstall on the VM after merge (install-vm.sh).
<!-- SECTION:PLAN:END -->
