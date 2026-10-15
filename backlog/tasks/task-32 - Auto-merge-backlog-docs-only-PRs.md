---
id: TASK-32
title: >-
  Backlog-only PRs: skip e2e-pi and ship them with a versioned bship (pull +
  duplicate-ID check)
status: In Progress
assignee:
  - '@copilot-mac'
created_date: '2026-10-14 14:32'
updated_date: '2026-10-15 14:14'
labels:
  - ci
  - infra
  - manual-path
dependencies: []
references:
  - .github/workflows/e2e-pi.yml
  - e2e/ci/README.md
  - CLAUDE.md
  - .github/CODEOWNERS
priority: high
type: task
ordinal: 40000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Backlog and docs changes reach main through Jan's bship zsh function (rule in CLAUDE.md since 2026-10-15): it commits only backlog/ and docs/ to a fresh backlog-<timestamp> branch, opens the PR and merges it at once. Re-scoped with Jan on 2026-10-15: the original auto-merge workflow (pull_request_target with contents: write) is dropped, because bship already merges and nobody else opens backlog-only PRs; a write-capable workflow would add risk for no gain.

Two problems remain:
1. Every bship PR starts e2e-pi on the Pi: minutes of runner time and the shared staging lock, which can delay a coder PR, for a change that cannot affect the integration.
2. Duplicate task IDs: on 2026-10-15 two backlog PRs cut from the same main (#38 and #39) both created TASK-38; it needed backlog doctor --fix afterwards. bship branches from the local main without pulling first and does not check IDs.

Current bship (lives only in Jan's ~/.zshrc today):
  bship() {
    local msg="${1:-Backlog update}" br="backlog-$(date +%Y%m%d-%H%M%S)"
    cd ~/programing/ha-2n-intercom || return 1
    if [ -n "$(git status --porcelain -- . ':!backlog' ':!docs')" ]; then
      echo "Changes outside backlog/ and docs/:"; git status --short -- . ':!backlog' ':!docs'; return 1
    fi
    git switch -c "$br" && git add backlog docs && git commit -q -m "$msg" || return 1
    git push -q -u origin "$br" && gh pr create --base main --title "$msg" --body "Backlog-only change." && gh pr merge --merge --delete-branch
    git switch -q main && git pull -q --ff-only
  }
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 e2e-pi.yml does not start for a pull_request_target PR whose changed files are all under backlog/ (except backlog/config.yml) or match docs/**/*.md; every existing guard in e2e-pi.yml (actor allow-list, same-repo, base branch, concurrency, permissions) is unchanged
- [ ] #2 e2e-pi still runs for any PR that also changes another file, including coder PRs whose last commit only touches backlog/ (the filter evaluates the whole PR diff), and for workflow_dispatch
- [ ] #3 bship lives in the repo as tools/bship.zsh (a zsh function, sourced from ~/.zshrc with one line documented in its header); the behaviour of the current function is kept
- [ ] #4 bship refuses (non-zero, clear message, nothing committed) when the checkout is not on main or anything outside backlog/ and docs/ is changed
- [ ] #5 bship runs git pull --ff-only on main before branching (with the uncommitted backlog/docs changes in place) and stops with a clear message if the pull fails
- [ ] #6 bship runs backlog doctor before committing and stops when it reports duplicate IDs, printing the backlog doctor --fix hint; it never runs --fix by itself
- [ ] #7 bship uses an explicit PR body and merge method (gh pr create --title/--body, gh pr merge --merge --delete-branch) and ends on an up-to-date main
- [ ] #8 Verified live: one bship PR merged without an e2e-pi run, one PR touching a non-backlog file still got e2e-pi; bship refused a duplicate-ID case reproduced locally; results in the task notes
- [ ] #9 CLAUDE.md and .github/copilot-instructions.md (in sync) and e2e/ci/README.md mention the e2e-pi path filter and tools/bship.zsh; the auto-merge idea is not documented as existing
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Keep the ordered pull_request_target path filter; do not change any workflow safety guards.
2. Version bship in tools/bship.zsh with main-only/outside-change checks, pull --ff-only before branching, and backlog doctor before committing. Per Jan's PR revision, reject only non-zero doctor exits or case-insensitive duplicate ID-group/Repair preview reports; accept all other zero-exit output. Never run --fix automatically. Preserve explicit PR body/merge method and main refresh.
3. Merge origin/main and resolve both project-rule conflicts by preserving main's Backlog/worktree/noreply wording, adding only the requested bship implementation sentence; keep the E2E path-filter bullets unchanged. Restore the Czech CI runbook title and translate the new section into Czech.
4. Move bship regressions to tools/tests/test_bship.py, adjust the repo-root lookup, use real Backlog 1.53.0 diagnostic messages, and document python3 -m unittest discover -s tools/tests in the script header. Validate tooling and integration suites plus manifest/compile/syntax checks.
5. Commit and push the merge resolution and revisions using the configured GitHub noreply email. Keep task status and acceptance criteria for a separate final commit after checks are green; no PR merge is authorized. Live path-filter verification remains a post-merge gate.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implementation started on the task branch using the existing plan. Live PR verification (AC 8) requires explicit permission to push/merge and must wait until the trusted workflow is on main; no commit or push is authorized yet. Only e2e/ci/README.md will change under e2e/ci/, as explicitly required by AC 9; CI scripts, runner hooks, rulesets, and the coder remain untouched.

Implemented the approved scope: ordered pull_request_target paths exclude backlog/** and docs/**/*.md, then re-include backlog/config.yml. A baseline comparison confirmed every other workflow byte (including guards, permissions, concurrency, and workflow_dispatch) is unchanged. Added tools/bship.zsh with BSHIP_REPO override and the documented source line, main-only/dirty-path checks, pull --ff-only before doctor/branching, fail-closed doctor output validation, explicit PR title/body and merge method, and actionable command-failure messages. Updated both project rule files with identical bship/path-filter paragraphs and e2e/ci/README.md, including required-check and GitHub 300-file filter limitations. No CI scripts, Pi hooks, rulesets, coder, integration code, or release metadata changed.

Local verification: Python 3.14, full unit suite 601 tests passed; validate.py, integration py_compile, zsh -n, and git diff --check passed. The 14 TASK-32 tests exercise real local Git repositories with a stubbed gh CLI, dirty/staged/untracked/renamed outside paths, detached/non-main checkouts, conflicting and non-fast-forward pulls, doctor failure/non-clean output, shipping failures, and final main refresh. With the real installed Backlog CLI and its Node runtime, a clean backlog shipped in the fixture; a duplicate TASK-1 pulled from the fixture origin was explicitly diagnosed (including its task filename) and refused before branching or committing, preserving the local docs edit and printing the manual --fix hint. No doctor --fix was invoked.

Remaining gates: bash e2e/e2e.sh wip exited 2 before unit/deploy/test stages with "run e2e/e2e.sh setup first"; this new worktree lacks e2e/.venv and e2e/.env. No staging or production HA was contacted; empty attempt artifacts were removed. AC 8 live GitHub PR verification has not run: the trusted workflow first needs review and merge to main, and commit/push/merge permission has not been granted. The fixture result is local evidence only, not a live PR result. Task remains In Progress with acceptance criteria unchecked pending the required gates; no commit or push performed.

Jan authorized committing, pushing, and opening the implementation PR after local verification. Merge is explicitly reserved until his review; no merge or live bship PR is authorized in this turn. The local E2E setup and post-merge AC 8 checks remain outstanding.

Jan requested the PR revision: merge origin/main, preserve its Backlog/worktree/noreply rules, remove the exact clean-output comparison, relocate tooling tests, and keep the runbook in Czech. The local Backlog binary is 1.48.0; clean and duplicate 1.53.0 output must be covered independently in fixtures. Task status remains In Progress; final status/criteria changes are deferred until green checks as requested.

PR revision implemented: merged origin/main, retaining its Backlog/worktree/noreply rules verbatim and adding only the requested bship sentence; the existing E2E path-filter bullets are unchanged. Removed the exact clean-output comparison: bship now rejects non-zero doctor exits or case-insensitive duplicate ID-group/Repair preview reports, accepting all other successful output including empty output. The 1.53.0 clean sentence and duplicate warning/repair-preview strings were verified against upstream v1.53.0 sources and added to the stub fixtures; the local real CLI remains 1.48.0. Tooling tests now live under tools/tests with the discovery command documented in the bship header; the CI runbook title is restored and the new section is in Czech as requested. Verification: all 15 tooling tests and all 587 integration unit tests passed separately on Python 3.14; validate.py, integration py_compile, and zsh syntax checks passed. Commit email is set to the requested GitHub noreply address. Task status and criteria remain unchanged for a later final commit after checks are green; no PR merge performed.
<!-- SECTION:NOTES:END -->
