---
id: TASK-21
title: Consolidate active branches into main
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-12 07:11'
updated_date: '2026-10-12 12:37'
labels:
  - git
  - maintenance
dependencies: []
references:
  - CLAUDE.md
  - e2e/nightly.sh
  - CHANGELOG.md
priority: high
type: chore
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The repo has drifted into many parallel lines of work, and the nightly E2E now tests every origin branch on one shared staging HA. Old-layout branches pollute staging (see the orphaned-entity bug), and each branch diverges further from `main` every day. State on 2026-10-12, against `origin/main` 369e923 (1.4.0):

| Branch | behind / ahead of main | Content |
|---|---|---|
| `origin/e2e-pipeline` | 0 / 3 | E2E pipeline (`e2e/`, `run_tests.sh`); the local `e2e/` working copy has newer, uncommitted tests |
| `task-14-15-options-flow-ux` | 0 / 3, **local only** (worktree `/private/tmp/ha2n-t1415`) | TASK-14/15 options-flow UX |
| `origin/mastalir1980-revize-pull-requestu` | 4 / 4, base 1.3.1 | transient-auth tolerance, `CONFIG_SCHEMA`, session-preserving auth recovery, setup-wizard back navigation |
| `origin/pr-7-savek-cc` | 33 / 1 | `48375d2` fixes the log-listener busy loop (main still has `asyncio.sleep(0)` at `coordinator.py:522`) |
| `task-4-8-9-access-control-ring-snapshot` | uncommitted working tree on top of main (~1650 lines) | TASK-4, TASK-8, TASK-9 |
| `security/secure-by-default-connection`, `savek-cc-main-latest`, `copilot/implement-architecture-points-1-3`, `copilot/design-home-assistant-custom-integration` | 0 ahead | already in main |
| `copilot/fix-basic-intercom-configuration`, `copilot/add-door-type-selection`, `copilot/start-implementation-phase` | 114–124 behind | obsolete Feb drafts, old layout |

Also untracked in the main working tree and not in any commit: `CLAUDE.md`, `.github/copilot-instructions.md`, `docs/`, `backlog/`; plus a stray `custom_components/2n_intercom.zip`.

Measured conflicts (`git merge-tree`): main + revize = 8 hunks; task-14-15 + revize = 59 hunks (`config_flow.py`, `strings.json`, translations, tests); main + pr-7 = 0; task-14-15 + e2e-pipeline = 0.

Merge order (each step = subtask): project files -> e2e-pipeline -> busy-loop fix -> task-14-15 -> revize (rebased) -> TASK-4/8/9 -> branch cleanup. Merge style follows the TASK-1 precedent: `--no-ff` merge commits into `main` (e.g. f3eacea). Nothing is committed, pushed or merged into `main` without Jan's go-ahead in the conversation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 All subtasks are Done
- [x] #2 `origin/main` contains the work from e2e-pipeline, task-14-15, revize, the busy-loop fix and TASK-4/8/9; the full unit suite and `validate.py` are green on main (Python 3.12+)
- [x] #3 `bash e2e/e2e.sh run --ref origin/main` is green after the last merge
- [x] #4 Only branches with unmerged, still-wanted work remain on origin
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Execute the subtasks in dependency order; each subtask = one branch/merge, reviewed by Claude, merged only after Jan's go-ahead.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-12 final check by Claude: all 7 subtasks Done. origin/main c28e833 contains e2e-pipeline (orphan pruning via e2e/scripts/prune_orphans.py from run.sh, nightly runs origin/main first), task-14-15, revize (auth recovery, CONFIG_SCHEMA, setup-wizard back navigation), busy-loop fix (LOG_LISTENER_IDLE_DELAY) and TASK-4/8/9; the backup 91a58b8 is fully contained (diff to main = TASK-14/revize refactors only). Unit suite on Python 3.12.15: 563 OK, validate.py OK. E2E 'e2e.sh run --ref origin/main' after the last merge: green, report on the Pi, confirmed by Jan 2026-10-12 14:36 (Claude cannot read Pi reports). origin has only main plus the already-merged task-21.7-finalize (safe to delete). Duplicate TASK-19 (Claude's failed first create) archived.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
All active branches consolidated into main via 7 subtasks (no-ff merges): project files, E2E pipeline with orphan-entity pruning, log-listener idle-delay fix, options-flow UX (TASK-14/15), auth recovery + setup-wizard back navigation from the revize branch, TASK-4/8/9 split from the working tree; obsolete branches deleted. Verified: 563 unit tests + validate.py green on Python 3.12, E2E run on origin/main green (Jan, Pi report), TASK-8 relay E2E green (20261012-131421).
<!-- SECTION:FINAL_SUMMARY:END -->
