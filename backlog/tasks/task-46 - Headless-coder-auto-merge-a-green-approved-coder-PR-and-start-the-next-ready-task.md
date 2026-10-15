---
id: TASK-46
title: >-
  Headless coder: auto-merge a green, approved coder PR and start the next ready
  task
status: To Do
assignee:
  - '@copilot-mac'
created_date: '2026-10-15 19:32'
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
- [ ] #1 Opt-in: without the root-owned file /etc/ha2n-coder/automerge the coder behaves exactly as today (green, PR waits for Jan); install-vm.sh does not create the file
- [ ] #2 A PR is merged only when all required checks incl. e2e-pi are green on the head commit, the second-model review verdict is approve, and the head commit is unchanged since the checks ran (gh pr merge --match-head-commit); a run without a configured review-model never auto-merges
- [ ] #3 Never auto-merged: PRs of tasks labelled release or manual-path, PRs whose diff touches a protected path (.github/, e2e/ci/, e2e/scripts/, tools/coder/, CLAUDE.md, .github/copilot-instructions.md, backlog/config.yml), and PRs not opened by this run
- [ ] #4 After a successful merge the run records the new end state merged (visible in ha2n-task-status --list) and starts --next once; --next keeps the TASK-35 kill switch, daily limit and readiness rules
- [ ] #5 A rejected merge (conflict, protection, changed head) leaves the state green with the reason and a PR comment; no retry loop
- [ ] #6 Tasks with label manual-close are merged like others; the coder still does not set them Done (they wait for Jan in To Test once TASK-36 lands)
- [ ] #7 Hermes instructions in tools/coder/README.md report the merged end state to Jan exactly once, with the PR link and the next task started (if any)
- [ ] #8 Stub simulation covers: switch off; green+approve merges and starts next; review changes-requested or missing does not merge; release/manual-path/protected-path never merge; changed head refused; merge refusal keeps green; bash -n clean
- [ ] #9 Rules and docs in sync: CLAUDE.md and .github/copilot-instructions.md ("the coder never merges" replaced by the auto-merge rule and its exceptions), tools/coder/README.md (Czech), docs/OVERVIEW.md pipeline section
<!-- AC:END -->
