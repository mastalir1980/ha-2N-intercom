---
id: TASK-46
title: >-
  Headless coder: auto-merge a green, approved coder PR and start the next ready
  task
status: To Test
assignee:
  - '@copilot-mac'
created_date: '2026-10-15 19:32'
updated_date: '2026-10-18 16:05'
labels:
  - agent
  - infra
  - manual-path
dependencies:
  - TASK-35
references:
  - tools/coder/run-task.sh
  - tools/coder/task-status.sh
  - tools/coder/install-vm.sh
  - tools/coder/README.md
  - docs/OVERVIEW.md
  - CLAUDE.md
  - .github/copilot-instructions.md
priority: high
type: task
ordinal: 53000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: Jan decided on 15 Oct 2026 that work on a milestone should flow without waiting for his merge between tasks: when a coder PR passes all checks and the independent second-model review approves it, the orchestrator merges it and the next ready task starts. Tasks in a milestone are chained by dependencies (e.g. v1.5.0: TASK-41 -> 42 -> 43 -> 44), and a dependent task is only ready once the previous one is Done on main, which today happens only when Jan merges. Jan keeps his gates where they matter for users: verifying To Test tasks on the real device and merging/tagging the release (HACS users install releases, not main).

Current behaviour: run-task.sh ends in state green after all PR checks (incl. e2e-pi) are green and the review (TASK-33) approves; it comments on the PR and never merges ("the coder never merges", CLAUDE.md, tools/coder/README.md). TASK-35 adds --next and a 10-minute timer that starts the next ready task, with a kill switch and a daily limit.

Expected behaviour: with the opt-in switch on, a run that reaches green with review verdict approve merges its own PR and then triggers --next once, so the next ready task starts without waiting for the timer. Everything else stays as today. Facts checked: branch protection on main has Required approvals = 0 (tools/coder/README.md), so a merge through the API is allowed once required checks pass; the coder token already has Pull requests RW; TASK-37 Release v1.5.0 carries the label release.

Approach (for the implementer to confirm in the plan): after the green/approve step in run-task.sh, if /etc/ha2n-coder/automerge exists, call gh pr merge with --merge and --match-head-commit <sha the checks ran on>; on success record state merged, then exec the --next entry from TASK-35 (which still applies its kill switch, daily limit and readiness rules). On any refusal keep state green and leave the PR for Jan. Must not change: protected paths stay out of reach of the coder, token handling, the ready check, the review step, the e2e-pi gate.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Opt-in: without the root-owned file /etc/ha2n-coder/automerge the coder behaves exactly as today (green, PR waits for Jan); install-vm.sh does not create the file
- [ ] #2 A PR is merged only when all required checks incl. e2e-pi are green on the head commit, the second-model review verdict is approve, and the head commit is unchanged since the checks ran (gh pr merge --match-head-commit); a run without a configured review-model never auto-merges
- [x] #3 Never auto-merged: PRs of tasks labelled release or manual-path, PRs whose diff touches a protected path (.github/, e2e/ci/, e2e/scripts/, tools/coder/, CLAUDE.md, .github/copilot-instructions.md, backlog/config.yml), and PRs not opened by this run
- [ ] #4 After a successful merge the run records the new end state merged (visible in ha2n-task-status --list) and starts --next once; --next keeps the TASK-35 kill switch, daily limit and readiness rules
- [x] #5 A rejected merge (conflict, protection, changed head) leaves the state green with the reason and a PR comment; no retry loop
- [x] #6 Tasks with label manual-close are merged like others; the coder still does not set them Done (they wait for Jan in To Test once TASK-36 lands)
- [ ] #7 Hermes instructions in tools/coder/README.md report the merged end state to Jan exactly once, with the PR link and the next task started (if any)
- [x] #8 Stub simulation covers: switch off; green+approve merges and starts next; review changes-requested or missing does not merge; release/manual-path/protected-path never merge; changed head refused; merge refusal keeps green; bash -n clean
- [x] #9 Rules and docs in sync: CLAUDE.md and .github/copilot-instructions.md ("the coder never merges" replaced by the auto-merge rule and its exceptions), tools/coder/README.md (Czech), docs/OVERVIEW.md pipeline section
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. run-task.sh: AUTOMERGE_FILE=/etc/ha2n-coder/automerge (opt-in, existence check at merge time). After the green/approve step and close_task: auto_merge() checks eligibility (switch on; review-model configured and verdict approve; task labels not release/manual-path; git diff origin/main...HEAD has no PROTECTED path; only the PR_URL opened by this run).
2. close_task pushes a new head (backlog-only) and GitHub re-runs all checks incl. e2e-pi on it (verified on PR #37), so when the head moved since the checks ran, wait_checks runs again in a soft mode (timeout/red -> no merge, state green) before merging.
3. gh pr merge --merge --match-head-commit <head the checks were green on>. Success -> state merged, release run.lock (fd 9) and run $0 --next once (kill switch, daily limit, readiness stay in --next); status gets next= field. Refusal -> state green with the reason + PR comment, no retry.
4. Switch off -> unchanged comment/status. install-vm.sh only reports the switch state.
5. Tests: gh stub pr merge (success/refusal/changed head); cases of AC #8.
6. Docs: CLAUDE.md + copilot-instructions (in sync), tools/coder/README.md (incl. Hermes), docs/OVERVIEW.md.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented (uncommitted, stacked on TASK-35):
- run-task.sh: opt-in switch /etc/ha2n-coder/automerge (root-owned, never created by install-vm.sh; self-check prints ON/off). New auto_merge(): merges only this run's own PR ($PR_URL from open_pr) when REVIEW_ON and verdict approve, task labels exclude release/manual-path, PR diff touches no PROTECTED path, and checks are green on the exact head; uses gh pr merge --merge --match-head-commit <sha>. No retry on refusal; state stays green with the reason in the status message and a PR comment.
- Decision: the close commit is a new PR head and GitHub re-runs all checks incl. e2e-pi on it (seen on PR #37), so auto_merge waits for checks again (wait_checks soft: timeout/red -> no merge). manual-close tasks get no close commit and merge on the already-checked head; the task is not set Done.
- After a merge: state merged, status line next=, and trigger_next releases run.lock (fd 9) and runs $0 --next once (output in runs/<run>/next.log). --next keeps its kill switch, daily limit and readiness rules: without /etc/ha2n-coder/autostart nothing is started (auto-merge then only merges).
- Assumption: 'PR opened by this run' is guaranteed by merging only $PR_URL of this run plus --match-head-commit; there is no separate gh author check.
- Tests: gh stub handles pr merge (success/refusal/head moved); 12 new tests cover every AC #8 case; protected paths are tested by running the auto_merge body in a harness (end-to-end it is unreachable because publish/close_task already reject protected paths).
- Docs: CLAUDE.md + .github/copilot-instructions.md (auto-merge rule and exceptions), tools/coder/README.md (Auto-merge section, merged state, Hermes reporting), docs/OVERVIEW.md.
- Validation: coder suite 54/54, unit tests 594 OK, validate.py OK, bash -n, git diff --check.
- Untested (VM only): real gh pr merge messages, real e2e-pi re-run on the close commit, systemd/sudo detach of the run started by --next.
- Open for Jan: accept the second e2e-pi wait per PR? Should merged branches be deleted (currently not)? Should a manual run also trigger --next (currently yes, if autostart is on)?

Rebased (uncommitted work) onto TASK-35 d421faa: no conflicts; auto_merge reads labels from HEADER only, does not use deps_done. Re-validated: coder suite 57/57, unit tests OK, validate.py OK, bash -n, git diff --check.

Jan's decisions (2026-10-16): (1) keep waiting for the re-run of all checks incl. e2e-pi on the close commit; (2) delete the remote branch on merge: gh pr merge --merge --match-head-commit <sha> --delete-branch (local cleanup unchanged; stub deletes the ref, tests assert it is gone after a merge and kept when not merged; README/CLAUDE.md/copilot-instructions/OVERVIEW updated); (3) any run that merges starts --next once, the autostart file stays the master switch. TASK-35 review findings were already fixed in d421faa (deps_done via --json with fallbacks, stopped runs without branch do not block, backlog version in install-vm.sh); TASK-46 sits on it. Validation: coder suite 57/57, unit tests OK, validate.py OK, bash -n, git diff --check.

2026-10-16 (Claude review): merged via PR #59 (fa6ed9f). Verified: coder stub suite 57/57 OK incl. the auto-merge cases; rules identical in CLAUDE.md and .github/copilot-instructions.md. Decisions from Jan: wait for checks again on the close commit, delete the remote branch on merge, any merging run starts --next once. Open until verified on the VM: AC #2 (real gh pr merge --match-head-commit after the second e2e-pi run), AC #4 (merged state and --next via systemd/sudo), AC #6 (manual-close merge), AC #7 (Hermes reports the merge once).

AC evidence (tester review 2026-10-18): stub simulation tests in tools/coder/tests; rules in CLAUDE.md + copilot-instructions. #2, #4, #7 wait for the first real auto-merge on the VM.
<!-- SECTION:NOTES:END -->
