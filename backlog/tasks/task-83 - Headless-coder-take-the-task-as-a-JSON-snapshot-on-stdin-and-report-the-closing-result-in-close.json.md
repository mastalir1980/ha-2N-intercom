---
id: TASK-83
title: >-
  Headless coder: take the task as a JSON snapshot on stdin and report the
  closing result in close.json
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-23 10:06'
updated_date: '2026-11-24 09:26'
labels:
  - agent
  - infra
  - manual-path
dependencies: []
references:
  - tools/coder/run-task.sh
  - tools/coder/task-status.sh
  - tools/coder/install-vm.sh
  - tools/coder/README.md
  - tools/coder/tests/test_run_task.py
priority: high
type: task
ordinal: 87000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: tasks move from Backlog.md to Jira Cloud (Jan, 2026-11-23). The coder must not hold a Jira token. The Hermes agent on the VM reads the task through the Atlassian MCP server, starts the coder and writes the result back to Jira. So ha2n-run-task must accept the task as a JSON snapshot on stdin and report the closing result in a file, instead of reading the task with the backlog CLI and committing a Backlog edit to the PR.

Current behaviour: run-task.sh reads the task with backlog task view, picks the next task with backlog task list (--next), and close_task commits a backlog task edit as the last commit of the PR.

Expected behaviour: a new mode ha2n-run-task --task-stdin <KEY> (KEY like HA2N-9). The snapshot schema:
{"key": "HA2N-9", "summary": "...", "status": "To Do", "labels": ["exec-koder", "camera"], "fixVersion": "v1.7.0" or null, "priority": "High", "updated": "2026-11-23T10:00:00Z", "description": "markdown", "acceptance_criteria": [{"id": 1, "text": "... [unit]", "checked": false}], "plan": "markdown", "blocked_by": [{"key": "HA2N-4", "status": "Done"}]}
In this mode the coder never calls the backlog CLI and never commits Backlog changes. The existing Backlog mode (TASK-<n>, --next) stays unchanged until the cutover; removing it is a later task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ha2n-run-task --task-stdin <KEY> reads the snapshot from stdin before going to the background (size limit 256 KB) and validates it: key equals the argument, status To Do, label exec-koder, no label on-hold or manual-path, every blocked_by status Done, at least one acceptance criterion. Any failure stops the run with a clear message; stub test for each rejection [unit]
- [ ] #2 The run stores task.json and renders task.txt in the same plain layout that backlog task view --plain produces today, so the implement and review prompts and the criteria parser work unchanged; stub test parses the criteria from a rendered snapshot [unit]
- [ ] #3 In task-stdin mode close_task makes no Backlog edit and no extra commit. It writes close.json in the run dir: key, target status (Done or To Test by the current rules, incl. manual-close and unproven criteria), every criterion with id, text, status and evidence, the summary text, PR URL, head SHA and merged true or false; stub test [unit]
- [ ] #4 ha2n-task-status --close-json <run> prints close.json, and ha2n-task-status --pending-close lists finished runs whose close.json has merged false; stub tests [unit]
- [ ] #5 The daily run limit (max-runs-per-day) and the last-failed-run guard also apply to task-stdin runs; the guard compares the snapshot field updated instead of the task file commit time; stub test [unit]
- [ ] #6 Auto-merge rules are unchanged; release and manual-path labels are read from the snapshot; stub test [unit]
- [ ] #7 The Backlog mode (TASK-<n> and --next) works unchanged; the existing coder stub suite is green; bash -n is clean [unit]
- [ ] #8 tools/coder/README.md documents the snapshot schema, the close.json fields and the call for the hermes user: sudo -n -u ha2n-coder /usr/local/bin/ha2n-run-task --task-stdin HA2N-<n> < task.json; install-vm.sh allows that call in sudoers [unit]
- [ ] #9 Jan runs one small task end to end on the test Jira project through the Hermes agent [jan]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Argument parsing: add --task-stdin <KEY>; read stdin into a temp file in the foreground (before launch_bg), then move it to $DIR/task.json.
2. Small python3 helper (inline, like the existing ones) validates the snapshot and renders task.txt in the backlog view --plain layout (Status, Labels, Milestone, Priority, Description, Acceptance Criteria with - [ ] #n lines, Implementation Plan).
3. Wrap every backlog task view call in one function that returns task.txt in task-stdin mode; candidate_row and pick_next are not used in this mode.
4. close_task: in task-stdin mode reuse the evidence logic (close-evidence.txt) but write close.json instead of backlog task edit + commit + push. auto_merge sets merged in close.json.
5. last_run_blocks: in task-stdin mode compare the snapshot updated (epoch) with the last failed run.
6. task-status.sh: add --close-json and --pending-close.
7. install-vm.sh: sudoers rule for hermes must allow --task-stdin (check how arguments are matched today).
8. Tests in tools/coder/tests/test_run_task.py with a stub snapshot; README.
Must not change: the PROTECTED list, the review flow, auto-merge rules, the Copilot sandbox (no token inside), the Backlog mode.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-24 (Claude, on Jan's request): implemented on branch task-83-coder-task-stdin. run-task.sh: --task-stdin <KEY> (snapshot_check validates and renders task.txt, snapshot_accept applies the 256 KB limit, the daily limit and the updated-based retry guard in the foreground), close_json/close_merged instead of the Backlog close commit, no --next after a merge in this mode. task-status.sh: --close-json, --pending-close. sandbox.sh: the branch-name check also accepts <key>-<n>-<slug> (needed for the ha2n-<n>-... branch; nothing else in the sandbox changed). The implement/review prompts are unchanged; the rendered prompt gets a note that the task is not in Backlog.md. Deviation from the plan: sudoers needed no change (the rule has no argument list), install-vm.sh only documents it. Open point for Jan: Jira bumps 'updated' on every comment or transition, so writing a failed result back to Jira re-arms the retry guard; the daily limit still holds. Local: 80 coder stub tests green (70 before), bash -n clean.
<!-- SECTION:NOTES:END -->
