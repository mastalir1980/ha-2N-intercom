---
id: TASK-21.7
title: Delete merged and obsolete branches (local + origin)
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-12 07:12'
updated_date: '2026-10-12 12:29'
labels:
  - git
  - maintenance
dependencies:
  - TASK-21.6
parent_task_id: TASK-21
priority: low
type: chore
ordinal: 28000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Merged or obsolete branches are tested every night on the shared staging HA (old layouts pollute it) and make the branch list hard to read. Deleting remote branches cannot be undone easily, so every deletion needs Jan's explicit OK in the conversation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Jan has confirmed the list before anything is deleted
- [x] #2 Deleted on origin and locally: `security/secure-by-default-connection`, `pr-7-savek-cc`, `mastalir1980-revize-pull-requestu`, `e2e-pipeline` (after merge), `copilot/implement-architecture-points-1-3`, `copilot/design-home-assistant-custom-integration`, `copilot/fix-basic-intercom-configuration`, `copilot/add-door-type-selection`, `copilot/start-implementation-phase`; locally also `savek-cc-main-latest`, `task-14-15-options-flow-ux`, `task-4-8-9-access-control-ring-snapshot` and the backup branch once its work is on main
- [x] #3 Any open GitHub PR from these branches (e.g. #7) is closed with a comment pointing to the commit on main
- [x] #4 `e2e/state/last_sha_*` files of deleted branches are removed on the Pi so the nightly does not report them
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Verify every branch's work is on origin/main (git branch --merged; content check for unmerged ones).
2. Check open PRs (gh pr list --state open).
3. Present the exact deletion list to Jan and wait for explicit OK (AC1).
4. Remove worktrees ../ha2n-t20, ../ha2n-t212, ../ha2n-t216 (only symlinks + __pycache__ untracked there) so their branches can be deleted.
5. Delete confirmed branches on origin (git push origin --delete) and locally (git branch -D).
6. Close any open PRs with a comment pointing to the main commit (AC3).
7. Give Jan the command to remove e2e/state/last_sha_* of deleted branches on the Pi (AC4).
8. Record evidence in notes; finalize on a task-21.7-finalize branch.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Pre-deletion check (origin/main d95eb4a):
- Merged into main: copilot/design-home-assistant-custom-integration, copilot/implement-architecture-points-1-3, e2e-pipeline, security/secure-by-default-connection, task-14-15-options-flow-ux, task-20/21.1/21.2/21.3/21.5-*/21.6-finalize, task-4/8/9 branches; savek-cc-main-latest (0 ahead).
- Not merged, verified superseded: copilot/add-door-type-selection (only 'Bump version to 0.1.1', PR #2 merged); copilot/fix-basic-intercom-configuration (PR #3 closed, last commit reverts to main); copilot/start-implementation-phase (PR #1 closed, superseded by #4/#5); pr-7-savek-cc 48375d2 busy-loop fix is on main via TASK-21.3 (LOG_LISTENER_IDLE_DELAY in coordinator.py); mastalir1980-revize-pull-requestu (PR #14 closed) carried into main by TASK-21.5; wip/task-4-8-9-backup = task-4-8-9-access-control-ring-snapshot = 91a58b8, split and merged via TASK-4/9/8 (TASK-21.6).
- Open PRs: none (PR #7 is already merged), so AC3 needs no action.

Jan confirmed the list (A = AC list + backup, B = all merged task-* branches and worktrees) on 2026-10-12.
Deleted on origin (21): security/secure-by-default-connection, pr-7-savek-cc, e2e-pipeline, copilot/{add-door-type-selection,design-home-assistant-custom-integration,fix-basic-intercom-configuration,implement-architecture-points-1-3,start-implementation-phase}, wip/task-4-8-9-backup, task-14-15-options-flow-ux, task-20-e2e-orphan-entities, task-21.1-project-files, task-21.2-e2e-merge, task-21.3-log-listener-idle-delay, task-21.5-{auth-recovery,finalize,setup-wizard-back}, task-21.6-finalize, task-4-access-control-events, task-8-grant-access, task-9-last-ring-image. origin now has only main.
Deleted locally, with tips for restore via git branch <name> <sha> while still in reflog/objects: security/secure-by-default-connection b463fe1, pr-7-savek-cc 48375d2, e2e-pipeline e811875, copilot/add-door-type-selection b9ed7e4, copilot/design-home-assistant-custom-integration 9f1b6a4, copilot/fix-basic-intercom-configuration 43282ee (origin tip 45da3d1), copilot/start-implementation-phase 4aef616, wip/task-4-8-9-backup + task-4-8-9-access-control-ring-snapshot 91a58b8, mastalir1980-revize-pull-requestu 8dd8b6c, savek-cc-main-latest 3e4b24a, task-14-15-options-flow-ux 9fb60f9, task-20 1f732b3, task-21.1 e114768, task-21.2 7b820c7, task-21.3 bccf86a, task-21.5-auth-recovery b2e191d, task-21.5-finalize 1e81679, task-21.5-setup-wizard-back 82695c1, task-21.6-finalize b1d366a, task-4 f999cc7, task-8 f645fe3, task-9 6724f97.
Removed worktrees ../ha2n-t20, ../ha2n-t212, ../ha2n-t216 (untracked content was only .env/.venv symlinks and __pycache__).
AC3: no open PRs existed (gh pr list --state open empty; #7 merged, #1/#3/#8/#14 already closed) - nothing to close.
AC4 pending: Jan removes e2e/state/last_sha_* except last_sha_main on the Pi.

AC4 done by Jan on the Pi 2026-10-12: removed 9 state files from ~/ha-2n-intercom/e2e/state/. The files are named last_sha_origin_<branch> (nightly.sh reads origin/<branch> refs), so the filter used was 'grep -vx last_sha_origin_main'. The command I suggested (keeping last_sha_main) was wrong and would also have removed main's state. last_sha_origin_main kept. /private/tmp/ha2n-t1415-e2e-untracked-backup and /tmp/t216* scratch files on the Mac were left as is, because they were not on the confirmed list.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Deleted all merged and obsolete branches after Jan confirmed the list: 21 on origin (origin now has only main), 23 locally, plus worktrees ha2n-t20/t212/t216. Before deleting, I verified that each branch's work is on main d95eb4a, using git branch --merged and content checks for the unmerged ones. There were no open PRs to close. Jan removed the stale e2e/state/last_sha_origin_* files on the Pi. Branch tips are listed in the notes for restore.
<!-- SECTION:FINAL_SUMMARY:END -->
