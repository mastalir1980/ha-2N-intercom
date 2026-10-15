---
id: TASK-25
title: >-
  Headless coder closes the task (Done, criteria ticked) in a last commit once
  e2e-pi is green
status: Done
assignee:
  - '@claude'
created_date: '2026-10-13 13:49'
updated_date: '2026-10-15 12:55'
labels:
  - ci
  - infra
dependencies: []
references:
  - .github/workflows
  - .github/CODEOWNERS
  - CLAUDE.md
  - .github/copilot-instructions.md
  - tools/coder/run-task.sh
  - tools/coder/README.md
priority: medium
type: task
ordinal: 33000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Tasks pile up in 'In Progress' because closing them is a manual step after every merge (TASK-2.1, TASK-15, TASK-23, TASK-24 at the time of writing). Jan decided on 2026-10-13: his merge is the acceptance, and no extra PRs or new Actions permissions. A workflow after merge was considered first (own PR, auto-merged) and dropped: the Pi must not hold a write token, and any commit pushed after e2e-pi has no checks on the new head, which breaks the coder's wait loop and any future required-check rule. Chosen design: once the headless coder's wait_checks reports green (incl. e2e-pi = pass), run-task.sh adds one last commit to the PR branch that sets the task Done, ticks all acceptance criteria and writes a final summary. Nothing waits for checks after that commit. The status reaches main only when Jan merges the PR; an unmerged PR changes nothing on main. A task labelled manual-close is skipped (for tasks verified only after the merge). Parent tasks are not touched. Limitation: the last commit carries no checks, so if e2e-pi ever becomes a required status check in the main ruleset this has to move to a workflow after merge. PRs not made by the coder follow the same convention by hand: the author sets Done in the PR's last commit once checks are green.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 After wait_checks returns green, run-task.sh adds exactly one commit on the PR branch whose diff touches only files under backlog/ (otherwise it is dropped and the run still ends green with a note) and pushes it; it then ends the run without waiting for checks again
- [x] #2 The commit runs backlog task edit <id> -s Done, --check-ac for every criterion and --final-summary with the PR URL, the checked sha, check names with results and the number of fix rounds
- [x] #3 A task with the label manual-close, or one that is already Done, is skipped with a log line; the run still ends green
- [x] #4 A failure while closing (backlog error, push rejected) never turns a green run red: status green with a message that the task was not closed and has to be closed by hand
- [x] #5 The stub simulation of the run (happy path, fix round, manual-close label, backlog failure, commit touching a non-backlog file) behaves as described; bash -n and shellcheck (if available) are clean
- [x] #6 Rules updated in sync: CLAUDE.md and .github/copilot-instructions.md (merge closes the task for coder PRs; other authors set Done in the last commit once checks are green; manual-close exception; parents closed by hand), tools/coder/prompts/implement.md, the PR body and comment written by run-task.sh, tools/coder/README.md
- [x] #7 Live check: the next coder PR ends with a last commit that sets its task Done with ticked criteria and, after Jan's merge, main shows the task as Done
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. tools/coder/run-task.sh: new function close_task, called after wait_checks succeeds and before the final 'green' status. It reads $DIR/task.txt (labels, status) to skip manual-close or Done; runs in $CLONE on the branch tip; backlog task edit $NUM -s Done, then --check-ac N for each criterion found in backlog task view (lines starting '- [ ] #N'), --final-summary built from $PR_URL, git rev-parse HEAD, $DIR/checks.json (name=bucket) and $ROUND.
2. Guard: git diff --name-only on the new commit must list only paths under backlog/; otherwise git reset --hard HEAD~1 and continue. Commit with the existing coder identity; message 'TASK-N: close task (checks green)'; push with gitauth push (plain fast-forward, no force).
3. close_task never fails the run: every error path logs and falls through to status green with a message that the task still has to be closed by hand.
4. Texts: pr-body.md and the final PR comment in run-task.sh, tools/coder/prompts/implement.md (lines about not ticking/Done: still true for Copilot, add that the orchestrator does it), tools/coder/README.md (the 'left In Progress' paragraph and the status list), CLAUDE.md Definition of done paragraph (~line 160) and .github/copilot-instructions.md (~lines 69 and 81) kept in sync.
5. Verify: bash -n, sample runs of close_task against a throw-away clone with a copy of a task file (normal, manual-close, already Done, backlog failing, non-backlog file changed), parse of the criteria count.
6. Do not change: ruleset, .github/workflows, e2e/ci, the protected-path list, the fix-round logic. tools/coder/ and CLAUDE.md are protected: Jan reviews and merges this PR.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-13: implemented on branch task-25-headless-coder-closes-task (not pushed). run-task.sh: close_task() after wait_checks is green; skips label manual-close / already Done; one commit 'TASK-N: close task (checks green)' that only touches backlog/ (anything else is rolled back); every failure path sets CLOSE_NOTE and the run still ends green. Texts synced: CLAUDE.md, .github/copilot-instructions.md, prompts/implement.md, tools/coder/README.md, PR body and comment. Tested in a throw-away repo with a local bare origin and the real backlog CLI: normal (Done, 6/6 criteria ticked, summary written, pushed), manual-close, already Done, push rejected, edit touching a non-backlog file (rolled back), missing task. Not tested: a real coder run on the VM and shellcheck (not installed). Incident while testing: a test script ran its git reset/clean in the real repo for a moment because the temp dir was not found; uncommitted edits were restored from the autostash commit, nothing was pushed.

2026-10-14 (Claude): merged in PR #24 (checks green). AC #7 (live check) not yet met: the only coder run since then (TASK-27, PR #29) stopped on a protected path and was finished by hand, so no closing commit by the coder exists yet. Close after the next coder PR ends with a 'TASK-N: close task (checks green)' commit.

2026-10-15 (Claude): live check met. Coder run for TASK-26 ended with commit 3783769 'TASK-26: close task (checks green)' touching only backlog/; after Jan merged PR #37, main shows TASK-26 Done with 11/11 criteria ticked. close_task() in run-task.sh matches #1-#4 (only after green wait_checks, backlog/-only commit else rollback, manual-close/already-Done skip, failures keep the run green with CLOSE_NOTE). #5 stub simulation from 2026-10-13; bash -n and shellcheck -S warning clean today. #6 texts in sync (CLAUDE.md, copilot-instructions.md, prompts/implement.md, README, PR body/comment). Cosmetic: the summary lists check names as GitHub reports them, so the hacs and hassfest jobs both show as 'validate=pass'; no change made.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
run-task.sh closes the task in one last backlog-only commit once all PR checks incl. e2e-pi are green; the merge is the acceptance. Verified live on PR #37 (TASK-26 Done on main after merge), plus code review of close_task(), the 2026-10-13 stub simulation and bash -n/shellcheck.
<!-- SECTION:FINAL_SUMMARY:END -->
