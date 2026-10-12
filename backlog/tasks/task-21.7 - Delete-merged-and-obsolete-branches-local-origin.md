---
id: TASK-21.7
title: Delete merged and obsolete branches (local + origin)
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-12 07:12'
updated_date: '2026-10-12 07:13'
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
- [ ] #1 Jan has confirmed the list before anything is deleted
- [ ] #2 Deleted on origin and locally: `security/secure-by-default-connection`, `pr-7-savek-cc`, `mastalir1980-revize-pull-requestu`, `e2e-pipeline` (after merge), `copilot/implement-architecture-points-1-3`, `copilot/design-home-assistant-custom-integration`, `copilot/fix-basic-intercom-configuration`, `copilot/add-door-type-selection`, `copilot/start-implementation-phase`; locally also `savek-cc-main-latest`, `task-14-15-options-flow-ux`, `task-4-8-9-access-control-ring-snapshot` and the backup branch once its work is on main
- [ ] #3 Any open GitHub PR from these branches (e.g. #7) is closed with a comment pointing to the commit on main
- [ ] #4 `e2e/state/last_sha_*` files of deleted branches are removed on the Pi so the nightly does not report them
<!-- AC:END -->
