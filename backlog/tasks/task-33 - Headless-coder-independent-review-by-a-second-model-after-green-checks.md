---
id: TASK-33
title: 'Headless coder: independent review by a second model after green checks'
status: To Do
assignee:
  - '@copilot-mac'
created_date: '2026-10-14 14:32'
updated_date: '2026-10-14 14:32'
labels:
  - agent
  - infra
  - manual-path
dependencies: []
references:
  - tools/coder/run-task.sh
  - tools/coder/sandbox.sh
  - tools/coder/prompts/implement.md
  - tools/coder/prompts/fix.md
  - tools/coder/task-status.sh
  - tools/coder/README.md
  - CLAUDE.md
priority: high
type: task
ordinal: 41000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Copilot may adjust tests until they pass, so every coder PR needs an independent review against the task's acceptance criteria and the architecture rules. Today Jan asks Claude for it by hand, and findings have no way back to the coder (manual steps 5 and 6 in the pipeline map, 14 Oct 2026). Decision by Jan (14 Oct 2026): the reviewer is GitHub Copilot CLI running a different model than the coder (coder: /etc/ha2n-coder/model); recommended: a Claude model from the Copilot model list, so the reviewer comes from a different vendor than the GPT coder. After this task Jan gets one message per PR with checks + review verdict and only decides about the merge.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 With /etc/ha2n-coder/review-model set, after wait_checks is green the orchestrator runs one review round in the sandbox with that model (and /etc/ha2n-coder/review-effort if set); without the file the review is skipped and the run behaves as today, with a note in the status message
- [ ] #2 The reviewer gets the task (description, acceptance criteria, plan), the full diff against origin/main and the architecture rules + definition of done from CLAUDE.md, and writes a JSON verdict {verdict: approve|changes, findings: [{severity: blocking|minor, file, line, summary}]}; any file change it makes is discarded
- [ ] #3 The verdict and findings are posted as one PR comment (no cost figures, no secrets, no host data); unparsable reviewer output is reported as "review failed" and never as approve
- [ ] #4 Blocking findings are fed back to the coder as one extra fix round (label review-fix-1), followed by checks and one more review; at most one review-fix round per run
- [ ] #5 close_task (TASK-25) runs only after verdict approve; with remaining blocking findings the run ends in a new state "review" with the findings in the message, and the task stays In Progress
- [ ] #6 Each reviewer call is logged in cost.csv with label review-N and its model; ha2n-task-status shows the verdict
- [ ] #7 Stub simulation covers: approve, changes then fixed, changes not fixed, missing review-model, unparsable output; bash -n clean
- [ ] #8 Rules and docs updated in sync: CLAUDE.md, .github/copilot-instructions.md (definition of done: review by second model for coder PRs; Claude reviews on request), tools/coder/README.md (Czech: setup of review-model, states), "Pro Hermese" instructions (message includes verdict)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. tools/coder/prompts/review.md: reviewer prompt (English) = act as reviewer only, inputs, checklist (each AC proven by a test or check, tests not weakened, architecture rules from CLAUDE.md, secrets, scope), output contract = JSON file .review.json in the sandbox root.
2. sandbox.sh: new mode "review" that takes the model/effort from review-model/review-effort, runs copilot without write tools if the CLI supports deny flags, and returns only .review.json (orchestrator also resets the tree afterwards).
3. run-task.sh: review() after wait_checks green -> parse JSON (jq) -> gh pr comment -> if blocking findings and REVIEW_ROUNDS=1 not used: fix round with findings as input (reuse the ci-fix path, label review-fix-1) -> push -> wait_checks -> review again. close_task only on approve. New status state "review". log_cost label review-N.
4. task-status.sh: show verdict; README + rules.
Must not change: the protected-path guard, token handling (reviewer never sees the repo token), max fix rounds for CI, the never-merge rule.
<!-- SECTION:PLAN:END -->
