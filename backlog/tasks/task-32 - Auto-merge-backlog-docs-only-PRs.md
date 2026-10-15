---
id: TASK-32
title: >-
  Backlog-only PRs: skip e2e-pi and ship them with a versioned bship (pull +
  duplicate-ID check)
status: To Do
assignee:
  - '@copilot-mac'
created_date: '2026-10-14 14:32'
updated_date: '2026-10-15 13:53'
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
1. .github/workflows/e2e-pi.yml: add paths-ignore under pull_request_target for backlog/** and docs/**/*.md, with a negation that keeps backlog/config.yml relevant (use paths with ! patterns if paths-ignore cannot express it). paths filters evaluate the whole PR diff. Touch nothing else in the file.
2. tools/bship.zsh: port the function from the description; add the on-main check, git pull --ff-only before git switch -c, and a backlog doctor run (the macOS backlog on PATH) whose output is checked for duplicate IDs; keep messages short and in English. Repo path from an env var with ~/programing/ha-2n-intercom as default.
3. Docs/rules: header comment in tools/bship.zsh with the source line; short notes in CLAUDE.md + copilot-instructions.md (together) and e2e/ci/README.md.
4. Verify live (AC 8) and write results to notes.
Must not change: e2e/ci/*, the runner hook on the Pi, the main ruleset, the coder (tools/coder/). Known limit: if e2e-pi ever becomes a required check, a skipped run would block backlog PRs; note this in e2e/ci/README.md.
<!-- SECTION:PLAN:END -->
