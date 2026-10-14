---
id: TASK-35
title: 'Headless coder: start the next ready task automatically (timer on the VM)'
status: To Do
assignee:
  - '@copilot-mac'
created_date: '2026-10-14 14:48'
updated_date: '2026-10-14 14:49'
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
Jan decided on 14 Oct 2026 that the coder on the VM (Trufalín) starts by itself instead of waiting for "vezmi TASK-N" via Hermes. The human gate moves to the grooming step ("ber") and to the merge. Signal = a ready task on main: To Do, assigned @copilot, dependencies Done. Chain after this task: grooming proposal -> Jan says "ber" -> backlog PR (auto-merged by TASK-32) -> within ~10 minutes the coder picks the task -> PR -> checks -> review (TASK-33) -> one message to Jan -> Jan merges. Guard rails are needed so autostart cannot burn credits in a loop or pick work that is on hold.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ha2n-run-task --next fetches main, and when no run is in state running it starts the highest-priority ready task (To Do, assignee @copilot, all dependencies Done, no label on-hold or manual-path; order: priority high > medium > low, then lowest task id); with nothing ready it exits 0 without output noise
- [ ] #2 Kill switch: without the root-owned file /etc/ha2n-coder/autostart, --next does nothing; a daily limit (/etc/ha2n-coder/max-runs-per-day, default 3) counts runs started by --next in the last 24 h
- [ ] #3 No retry loops: a task whose last run ended stopped or failed is not picked again until its task file on origin/main has changed after that run started
- [ ] #4 install-vm.sh installs a systemd service + timer (every 10 min, user ha2n-coder) that runs --next; the timer is enabled but does nothing until /etc/ha2n-coder/autostart exists
- [ ] #5 Jan is told about every run without asking: the "Pro Hermese" instructions in tools/coder/README.md let Hermes report each new end state (green, review, stopped, failed) from ha2n-task-status --list exactly once
- [ ] #6 Stub simulation: nothing ready; one ready task started; running run blocks a second start; on-hold and manual-path skipped; stopped task not retried until its file changes; kill switch and daily limit; bash -n clean
- [ ] #7 Rules and docs in sync: CLAUDE.md, .github/copilot-instructions.md (ready = picked automatically; label on-hold), tools/coder/README.md (Czech), docs/OVERVIEW.md pipeline section
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. run-task.sh: new entry `--next` (before the TASK-<n> parse). Steps: kill switch -> daily limit (count runs/*/next.marker of the last 24 h) -> any status file with state=running -> exit. gitauth fetch; for each backlog task (backlog task list --status "To Do" --plain + task view, read-only, in the own clone after reset to origin/main): filter assignee @copilot, labels, dependencies Done; sort; skip tasks whose last run is stopped/failed and whose file has no newer commit (git log -1 --format=%ct origin/main -- <task file> vs run start). Then exec the normal start path for that task and drop a next.marker in the run dir.
2. install-vm.sh: /etc/systemd/system/ha2n-coder-next.{service,timer} (OnBootSec=5min, OnUnitActiveSec=10min, User=ha2n-coder), enable --now. Do not create /etc/ha2n-coder/autostart.
3. task-status.sh: mark auto-started runs in --list.
4. README (Czech): how to switch autostart on/off, limit, Hermes instructions for reporting end states once (Hermes keeps its own list of reported run ids).
Must not change: the ready check of a normal run, protected paths, token handling, never-merge.
<!-- SECTION:PLAN:END -->
