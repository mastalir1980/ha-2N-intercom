---
id: TASK-35
title: 'Headless coder: start the next ready task automatically (timer on the VM)'
status: In Progress
assignee:
  - '@copilot-mac'
created_date: '2026-10-14 14:48'
updated_date: '2026-10-16 07:16'
labels:
  - agent
  - infra
  - manual-path
dependencies:
  - TASK-34
references:
  - tools/coder/run-task.sh
  - tools/coder/task-status.sh
  - tools/coder/install-vm.sh
  - tools/coder/README.md
  - docs/OVERVIEW.md
priority: high
type: task
ordinal: 43000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Jan decided on 14 Oct 2026 that the coder on the VM starts by itself instead of waiting for "vezmi TASK-N" via Hermes. The human gate moves to the grooming step ("ber") and to the merge. Signal = a ready task on main: To Do, assigned @copilot, dependencies Done. Chain after this task: grooming proposal -> Jan says "ber" -> backlog PR (auto-merged by TASK-32) -> within ~10 minutes the coder picks the task -> PR -> checks -> review (TASK-33) -> one message to Jan -> Jan merges. Guard rails are needed so autostart cannot burn credits in a loop or pick work that is on hold.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Kill switch: without the root-owned file /etc/ha2n-coder/autostart, --next does nothing; a daily limit (/etc/ha2n-coder/max-runs-per-day, default 3) counts runs started by --next in the last 24 h
- [ ] #2 No retry loops: a task whose last run ended stopped or failed is not picked again until its task file on origin/main has changed after that run started
- [ ] #3 install-vm.sh installs a systemd service + timer (every 10 min, user ha2n-coder) that runs --next; the timer is enabled but does nothing until /etc/ha2n-coder/autostart exists
- [ ] #4 Jan is told about every run without asking: the "Pro Hermese" instructions in tools/coder/README.md let Hermes report each new end state (green, review, stopped, failed) from ha2n-task-status --list exactly once
- [ ] #5 Stub simulation: nothing ready; one ready task started; running run blocks a second start; on-hold and manual-path skipped; stopped task not retried until its file changes; kill switch and daily limit; bash -n clean
- [ ] #6 Rules and docs in sync: CLAUDE.md, .github/copilot-instructions.md (ready = picked automatically; label on-hold), tools/coder/README.md (Czech), docs/OVERVIEW.md pipeline section
- [ ] #7 ha2n-run-task --next fetches main, and when no run is in state running it starts the next ready task (To Do, assignee @copilot, all dependencies Done, no label on-hold or manual-path). Order (decided by Jan, 15 Oct 2026): tasks of the earliest open milestone first (open milestones sorted by version number, e.g. v1.5.0 before v1.6.0), then tasks of later milestones, tasks without a milestone last; inside each group priority high > medium > low, then lowest task id. With nothing ready it exits 0 without output noise
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. run-task.sh: new entry `--next` (before the TASK-<n> parse). Steps: kill switch -> daily limit (count runs/*/next.marker of the last 24 h) -> any status file with state=running -> exit. gitauth fetch; for each backlog task (backlog task list --status "To Do" --plain + task view, read-only, in the own clone after reset to origin/main): filter assignee @copilot, labels, dependencies Done; sort; skip tasks whose last run is stopped/failed and whose file has no newer commit (git log -1 --format=%ct origin/main -- <task file> vs run start). Then exec the normal start path for that task and drop a next.marker in the run dir.
2. install-vm.sh: /etc/systemd/system/ha2n-coder-next.{service,timer} (OnBootSec=5min, OnUnitActiveSec=10min, User=ha2n-coder), enable --now. Do not create /etc/ha2n-coder/autostart.
3. task-status.sh: mark auto-started runs in --list.
4. README (Czech): how to switch autostart on/off, limit, Hermes instructions for reporting end states once (Hermes keeps its own list of reported run ids).
Must not change: the ready check of a normal run, protected paths, token handling, never-merge.

Ordering: read open milestones from `backlog milestone list --plain` (active only), sort by semantic version of the name; a task's milestone comes from `backlog task view` (Milestone line). Unit-test the sort in the stub simulation (two milestones + one task without milestone).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Plan confirmed; implementation in progress. Decisions: (1) 'a run is active' = flock on run.lock is held (the same lock the foreground run takes), not a leftover state=running in a status file; a status file that still says running while the lock is free is treated as a crashed run. (2) status files get a started=<epoch> key, used by the retry guard to compare with the task file's last commit on origin/main. (3) The retry guard covers every finished state (stopped, failed, review, green) plus crashed running runs, not only stopped/failed: review/green runs already own a PR branch, so re-running would only end in 'branch already exists'. This extends AC #2; to be confirmed by Jan. (4) Milestone and priority are parsed from task view, sorted with zero-padded keys.

Self-review fixes (2026-10-16):
- last_run_blocks: runs without started= in status (all runs made before this change) blocked their task forever, because the 'file changed after the run started' test could never pass. The start time now falls back to the run id (local time, parsed with python3). Test: test_run_without_started_field_uses_the_run_id_time.
- last_run_blocks: git log now uses --first-parent, so the time counted is when the task change landed on main (the merge commit), not when the commit was written on a branch.
- Foreground ready check (manual starts too): the dependency check matched 'Depends on', but backlog prints 'Dependencies:', so it never fired. Both paths now share deps_done(). Test: test_manual_start_refuses_unmet_dependencies.
- README 'Pro Hermese': Hermes now polls ha2n-task-status --list every 5 min to find auto runs, because it has no other trigger for them.
- Dry run of candidate_row against the real backlog: TASK-45 (High, m-0) then TASK-41; every other To Do task is skipped for the right reason (assignee, manual-path, on-hold, unmet deps).
<!-- SECTION:NOTES:END -->
