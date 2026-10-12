---
id: TASK-23
title: >-
  Headless coding agent on the VM: Copilot CLI turns a ready Backlog task into a
  PR tested by e2e-pi
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-12 19:11'
updated_date: '2026-10-12 19:44'
labels:
  - agent
  - ci
  - infra
dependencies:
  - TASK-22
priority: high
type: task
ordinal: 30000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Second half of the autonomous pipeline (first half: TASK-22, PRs are tested on the Pi as check e2e-pi). Jan wants coding on his separate VM (outside the home network) with GitHub Copilot running locally there (Copilot CLI, headless), started only on his command (no schedule); PRs open under Jan's own account with a fine-grained PAT scoped to this repo (Contents RW, Pull requests RW, no Workflows/Administration); Jan merges, no auto-merge until the phase-2 hardening of the Pi runner. Decisions by Jan on 2026-10-12. Copilot CLI accepts a fine-grained PAT with only the Account permission 'Copilot Requests', so Copilot runs without any repository rights; push and PR creation are done by a deterministic orchestrator (user ha2n-coder), Copilot and all repo code run as a separate sandbox user (ha2n-copilot) whose only output is a diff that the orchestrator checks after applying. The VM cannot run E2E; the e2e-pi check on the PR is the E2E gate.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 One command on the VM (directly or via Hermes) takes a ready task id and ends with a PR from branch task-<id>-<slug> opened by the bot account, or a clear stop reason
- [ ] #2 Copilot runs headless with a token that has no repository rights; push and PR creation are done only by the orchestrator with the bot token
- [ ] #3 Local gates before push: unit tests, validate.py, py_compile on Python 3.12+; a diff touching protected paths (.github/, e2e/ci/, e2e/scripts/, e2e/run.sh, e2e/nightly.sh, e2e/staging/, CLAUDE.md) is never pushed
- [ ] #4 After push the orchestrator waits for e2e-pi; on failure it feeds the public summary back to Copilot, at most 3 fix rounds, then stops and reports
- [ ] #5 Bot is allow-listed for the Pi runner (E2E_PI_ACTORS and /etc/ha2n-ci/allowed-actors) and main is protected so the bot cannot merge
- [ ] #6 Rules updated: .github/copilot-instructions.md and CLAUDE.md describe headless mode (no e2e.sh on the VM, e2e-pi is the gate); runbook for the VM setup
- [ ] #7 First live run: a small ready task becomes a green PR without human edits
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. tools/coder/sandbox.sh (ha2n-copilot): prepare (wipe HOME, kill leftovers, fresh clone), copilot (headless, own token only), gates (root-owned Python 3.12 venv), patch (plain diff).
2. tools/coder/run-task.sh (ha2n-coder): ready check on task metadata, branch task-<n>-<slug>, local gates with <=2 fix rounds, git apply --index then check staged files (protected paths, no renames trick, no symlink/submodule/mode/binary, size), commit + push + PR (label agent) with token only in gitauth/ghx wrappers, wait for PR head + checks, e2e-pi must be 'pass', <=3 CI fix rounds, never merge.
3. prompts/implement.md, prompts/fix.md (.agent-stop contract).
4. install-vm.sh (users, gh apt, uv + /opt Python 3.12, root-owned scripts, sudoers, self-checks), set-token.sh, task-status.sh, README (Czech).
5. Rules: copilot-instructions.md headless section, CLAUDE.md, CODEOWNERS /tools/coder/, pr-e2e.sh -m 'not relay'.
6. Verify: shellcheck; stub simulation of happy path, stop, protected path, rename of protected file, binary, symlink, CI fix round, skipped e2e-pi, bad run id; independent security review applied. Then Jan installs on the VM and does a first live run.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-12 21:13 decision change (Jan): no bot account for now — the orchestrator pushes and opens PRs under Jan's account with a fine-grained PAT scoped to this repo only (Contents RW, Pull requests RW, Metadata R; no Workflows, no Administration). Agent work is marked by a distinct commit author (ha2n-coder (Copilot)), PR label 'agent' and task-* branches. main gets a ruleset: PR required, no force push, no bypass (no required approvals — Jan cannot approve his own PRs). Pi allow-list unchanged (mastalir1980). AC #5 reads accordingly: allow-list already covers the account; the bot can be introduced later.

2026-10-12: implemented in working tree (not committed). Stub simulation in a container (real git, real repo clone, stubbed copilot/gh/backlog): happy path green; .agent-stop -> stopped; .github change -> rejected; rename of e2e/ci file -> rejected (staged-file check, no renames); binary -> diff does not apply -> stopped; symlink -> rejected; e2e-pi fail then fix round -> green; skipped e2e-pi -> not green (now stops with a clear message); invalid --run -> refused; Copilot cannot read the repo token. Bug found by the simulation and fixed: sandbox kept sudo's cwd (unreadable dir), so HOME wipe failed. Independent review findings applied: git am replaced by git apply --index + checks on what is staged (MIME/base64 and rename bypasses), root-owned Python venv, HOME wipe + leftover kill on prepare, run-id validation, lock before 'latest', head-SHA wait before reading checks, e2e-pi must be pass, return codes on reset, token only in git/gh wrappers, header-only ready check, conftest.py protected, pr-e2e.sh deselects relay tests. Known residual (phase 2): Copilot can use curl/network from the sandbox (deny-tool is not a boundary), agent-written e2e tests run on the Pi with the read-only account; no egress firewall yet.
<!-- SECTION:NOTES:END -->
