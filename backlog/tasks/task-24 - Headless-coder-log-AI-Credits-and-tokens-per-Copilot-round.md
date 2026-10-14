---
id: TASK-24
title: 'Headless coder: log AI Credits and tokens per Copilot round'
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-13 12:55'
updated_date: '2026-10-14 14:31'
labels:
  - agent
  - infra
dependencies: []
references:
  - tools/coder/sandbox.sh
  - tools/coder/run-task.sh
  - tools/coder/task-status.sh
  - tools/coder/README.md
priority: medium
type: task
ordinal: 32000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Jan wants to know what each headless coder run costs before running more tasks (TASK-23). Copilot CLI prints a summary at the end of a -p run (verified on the VM with gpt-6.1-sol, 2026-10-13): lines 'AI Credits <n> (<time>)' and 'Tokens ↑ <in> (<written> written) • ↓ <out>'. With -s (silent), which sandbox.sh uses, only the answer is printed, so the cost is not visible today. Each round's output already goes to /var/lib/ha2n-coder/runs/<run>/copilot-<round>.log. Costs are logged in AI Credits, not money (the conversion is unknown). The repo is public, so cost must stay on the VM and never go into PR comments or commits. This touches tools/coder/, a protected path: the headless coder cannot do it; it needs Jan's review (CODEOWNERS).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 sandbox.sh no longer passes -s to copilot, so the AI Credits and Tokens lines appear at the end of each copilot-<round>.log
- [ ] #2 After every Copilot round run-task.sh appends one CSV line to /var/lib/ha2n-coder/cost.csv: timestamp, run id, task id, model, round label (implement or fix N), AI credits, tokens in, tokens out, duration
- [ ] #3 If the summary lines are missing or unparsable, the CSV line is still written with empty cost fields and the run does not fail
- [ ] #4 ha2n-task-status --list shows the total AI credits per run as an extra column; single-run view shows the per-round lines
- [ ] #5 Exit-code handling still works without -s: exit 3 (.agent-stop) and the failure stop messages behave as before
- [ ] #6 Cost is never written to PR comments, commit messages or anything pushed; tools/coder/README.md (Czech) documents the file and its columns
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. tools/coder/sandbox.sh (copilot case, ~line 63): drop -s from the copilot call; keep --no-ask-user, --allow-all-tools and the deny-tool flags unchanged.
2. tools/coder/run-task.sh copilot_round (~line 95): after the call, parse copilot-$ROUND.log with grep/sed for the 'AI Credits <n>' and 'Tokens ↑ <in> ... ↓ <out>' lines (strip k/M suffixes carefully or keep the raw text), append one line to $BASE/cost.csv (create with header if missing). Empty fields if not found. Never fail the run because of parsing. The tail -5 shown in run.log will now be the summary, which is fine.
3. tools/coder/task-status.sh: in --list add a column with the sum of credits from the run's rows in cost.csv; the single-run view prints that run's rows.
4. tools/coder/README.md: describe cost.csv, columns, that costs are AI credits, and that nothing is pushed or posted.
5. Do not change: the deny-tool flags, the protected-path checks, the PR/comment code. Verify with the stub simulation used for TASK-23 (a stub copilot that prints the summary lines, one that prints none) and shellcheck.
6. Protected path: tools/coder/ is not changeable by the headless coder; Jan reviews the PR (CODEOWNERS).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-13: implemented on branch task-24-headless-coder-log-ai-credits (not committed). sandbox.sh: -s removed. run-task.sh: log_cost() parses 'AI Credits' / 'Tokens' from copilot-$ROUND.log after every Copilot call and appends to $BASE/cost.csv (labels implement, local-fix-N, ci-fix-N; model/effort from the sandbox echo lines, first match). task-status.sh: cr column in --list, per-call rows in the single-run view. README documents cost.csv. Tested: parser on sample logs (normal, ANSI + k/M suffix, no summary, missing log), task-status.sh against a fake runs dir; bash -n on all three scripts. Not tested: real Copilot run on the VM; shellcheck not installed here. Unverified: that the Copilot CLI flag for reasoning effort is --effort (already in the working tree for /etc/ha2n-coder/effort).

2026-10-13: verified on the VM (copilot --help): the flag is --reasoning-effort <none|minimal|low|medium|high|xhigh|max>, not --effort; sandbox.sh fixed accordingly.

2026-10-14 (Claude): merged in PR #23 (checks green). Still open: evidence from a real run that /var/lib/ha2n-coder/cost.csv gets one line per Copilot call (the TASK-27 run 20261013-214615 happened after the merge; if the VM was reinstalled before it, its lines should be there). Jan to run 'ha2n-task-status --list' on the VM; if the cr column is filled, close.
<!-- SECTION:NOTES:END -->
