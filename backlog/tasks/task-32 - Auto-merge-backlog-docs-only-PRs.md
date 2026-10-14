---
id: TASK-32
title: Auto-merge backlog/docs-only PRs
status: To Do
assignee:
  - '@copilot-mac'
created_date: '2026-10-14 14:32'
updated_date: '2026-10-14 14:32'
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
Every Backlog change ships as its own PR from main (rule in CLAUDE.md), and Jan has to merge each one by hand: 4 of the 12 PRs on 12-13 Oct 2026 (#20, #25, #27, #28) were backlog/rules-only. The new grooming agent turns an accepted proposal into a task through such a PR, so without this the pipeline stops at a manual merge every time. Goal: PRs from this repo that change only Backlog task/draft files or Markdown docs merge themselves; everything else keeps Jan's manual merge. Safety constraints: the decision must never run code from the PR (workflow comes from main via pull_request_target, no checkout of the PR head), and the e2e-pi check must not waste the Pi on such PRs.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A same-repo PR into main whose changed files (including the old path of renames) are all under backlog/tasks/, backlog/drafts/, backlog/archive/, backlog/completed/ or match docs/**/*.md is merged automatically without any action by Jan
- [ ] #2 A PR that also changes any other file (e.g. backlog/config.yml, CLAUDE.md, e2e/scripts/, .github/, code, docs/*.py) is not auto-merged and gets no auto-merge comment
- [ ] #3 PRs from forks, or opened by an account that is not in the repo variable E2E_PI_ACTORS, are never auto-merged
- [ ] #4 The workflow uses pull_request_target from main, runs on a GitHub-hosted runner (never the self-hosted Pi runner), never checks out or executes PR code, and has only contents: write + pull-requests: write
- [ ] #5 e2e-pi is not started for PRs whose changes are only in the auto-merge paths (paths-ignore or an equivalent guard in e2e-pi.yml), but still runs for coder PRs whose last commit only touches backlog/
- [ ] #6 Verified live: one backlog-only test PR merged by itself, one mixed PR left open; results written to the task notes
- [ ] #7 CLAUDE.md and .github/copilot-instructions.md (in sync) and e2e/ci/README.md describe the auto-merge rule, its path list and the one-time repo setting "Allow auto-merge"
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. New .github/workflows/backlog-automerge.yml: on pull_request_target (opened, synchronize, reopened, ready_for_review) into main; job if: head repo == this repo and PR author in fromJSON(vars.E2E_PI_ACTORS). runs-on ubuntu-latest, permissions contents: write, pull-requests: write, no actions/checkout of the head.
2. List changed files with gh api --paginate repos/{repo}/pulls/{n}/files (filename + previous_filename); match every path against an explicit allow-list regex; any miss -> exit 0 without merging.
3. All allowed -> gh pr merge --auto --merge (repo uses merge commits). Note: merges by GITHUB_TOKEN do not trigger other workflows; that is fine.
4. e2e-pi.yml: add paths-ignore for the same allow-list on pull_request_target (paths filters evaluate the whole PR diff, so coder PRs with a backlog-only last commit still run). Keep every existing guard in e2e-pi.yml unchanged.
5. Docs + rules (CLAUDE.md and copilot-instructions.md together). Jan enables Settings > General > Allow auto-merge once.
Must not change: e2e/ci/*, the job hook on the Pi, the ruleset on main, the coder.
<!-- SECTION:PLAN:END -->
