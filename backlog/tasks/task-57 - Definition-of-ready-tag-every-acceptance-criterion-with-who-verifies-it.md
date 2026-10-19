---
id: TASK-57
title: 'Definition of ready: tag every acceptance criterion with who verifies it'
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-18 15:47'
updated_date: '2026-10-19 06:26'
labels:
  - process
  - manual-path
dependencies: []
priority: high
ordinal: 64000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The reviewer (TASK-36) and the tester agent need to know which criteria are theirs. Every criterion ends with one tag: [unit] = a unit test proves it; [e2e] = a test in e2e/tests proves it (PR check e2e-pi); [tester] = verified by the tester agent on staging after the merge (read-only, no relays, no calls); [jan] = needs Jan (physical button, calls, relays, Control4, a real IP change).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 CLAUDE.md and .github/copilot-instructions.md: definition of ready point 3 requires the tag and explains the four values
- [x] #2 The grooming agent prompt writes the tag on every proposed criterion
- [x] #3 Open tasks assigned @copilot in To Do and the tasks in To Test are retagged via the backlog CLI
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-18 (Claude): grooming scheduled task prompt now requires a verifier tag on every proposed criterion and manual-close for any [jan] criterion (AC #2). Retagged TASK-37 and TASK-51 (To Do, @copilot) and TASK-35, TASK-46 (To Test; checked criteria re-checked) (AC #3). CLAUDE.md DoR point 3 and .github/copilot-instructions.md on branch backlog-verifier-tags, waiting for PR (AC #1).
<!-- SECTION:NOTES:END -->
