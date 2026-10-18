---
id: TASK-36
title: >-
  Headless coder: per-criterion evidence from the reviewer; tick only proven
  criteria, To Test when any remain
status: Done
assignee:
  - '@copilot-mac'
created_date: '2026-10-15 12:13'
updated_date: '2026-10-18 16:37'
labels:
  - agent
  - infra
  - manual-path
dependencies: []
references:
  - tools/coder/run-task.sh
  - tools/coder/README.md
  - CLAUDE.md
priority: high
type: task
ordinal: 44000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
close_task in tools/coder/run-task.sh (around line 478-514) ticks every unchecked criterion (line 495) without any evidence, and for manual-close tasks it ticks nothing. Result: TASK-31/45/47/49 reached Done with 0 of 8-9 criteria ticked although most were proven by unit tests. review.md already tells the reviewer that a criterion without proof is blocking, but its JSON only carries verdict + findings, so the per-criterion result is lost. Fix: the reviewer returns a status and evidence for every criterion; close_task ticks only proven ones and sets To Test when anything is left.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 review.md output contract adds criteria: [{id, status: proven|manual|unproven, evidence}] covering every criterion of the task; run-task.sh validates it (all ids present, known status, evidence non-empty for proven); invalid output = review failed as today
- [x] #2 The reviewer uses the verifier tag at the end of a criterion when present: [unit]/[e2e] must be proven in the diff or by a green check, [tester]/[jan] are reported as manual; an unproven [unit]/[e2e] criterion is a blocking finding
- [x] #3 close_task ticks only proven criteria and appends one line per criterion (AC #n: evidence) to the final summary; without a configured review-model nothing is ticked
- [x] #4 Status after green checks: Done when every criterion is proven and the task has no manual-close label; otherwise To Test; tasks already Done or To Test are left alone
- [x] #5 Stub simulation in tools/coder/tests covers: all proven -> Done, all ticked; mixed -> To Test, only proven ticked; manual-close -> To Test; malformed criteria -> review failed, nothing ticked
- [x] #6 Rules in sync (CLAUDE.md, .github/copilot-instructions.md, tools/coder/README.md): meaning of To Test, evidence lines in the final summary, manual-close kept as explicit marker
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Extend review.md with per-criterion evidence and verifier-tag rules. Validate exact criterion IDs, statuses, evidence and tag semantics in run-task.sh; retain only sanitized results for finalization.
2. Update close_task to tick only proven criteria, append AC evidence lines and choose Done only for a fully proven task without manual-close; otherwise choose To Test, including without a review model. Leave Done/To Test tasks unchanged and preserve the backlog-only guard, non-fatal finalization and single closing commit.
3. Extend hermetic pipeline simulations for evidence validation, verifier tags, partial/no evidence, existing terminal statuses and auto-merge of the closing commit.
4. Synchronize CLAUDE.md, .github/copilot-instructions.md and tools/coder/README.md. Run coder regressions and required Python validation, then staging E2E if configured.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented the per-criterion reviewer contract and strict validation of complete numeric IDs, statuses, proven evidence and trailing verifier tags. Sanitized evidence is included in the PR review comment and final task summary. Finalization checks only proven criteria, chooses Done only with complete proof and no manual-close label, otherwise To Test (including when review is disabled), and leaves Done/To Test tasks unchanged. Added a stale-criteria guard while retaining the backlog-only diff guard, non-fatal finalization and a single closing commit. Updated both rule files and the coder README.
Validation: the complete integration suite passed (675 tests) on Python 3.14 after installing tests/requirements.txt in an isolated session venv; validate.py and py_compile passed. The initial coder simulation suite passed (67 tests); final additional safety regressions are being verified.
E2E blocker: bash e2e/e2e.sh wip exited 2 with "run e2e/e2e.sh setup first". This worktree has neither the E2E venv nor its local environment configuration. No staging or production system was contacted. Leave TASK-36 In Progress and do not claim the full definition of done until a configured staging E2E run is green. No commit or push was requested or performed.

Final verification: all 70 coder regression tests passed (including finalization rollback, stale evidence rejection and pre-checked criteria without a reviewer).
AC #1: malformed/missing/duplicate/unknown IDs, invalid statuses and empty proven evidence are rejected by test_review_json_with_malformed_criteria_is_failed, test_review_json_without_criteria_is_failed and test_review_must_cover_checked_and_unchecked_criteria.
AC #2: verifier-tag semantics are covered by test_all_criteria_proven_sets_done_and_ticks_all, test_unproven_automated_tags_block_even_an_approve_verdict and test_manual_tags_cannot_be_reported_as_proven.
AC #3: remote task contents and AC evidence lines are asserted by the all-proven/mixed tests and the missing-reviewer tests; test_review_comment_is_sanitised also checks stored evidence.
AC #4: status transitions and existing Done/To Test states are covered by test_manual_close_sets_to_test_even_with_all_criteria_proven, test_mixed_evidence_sets_to_test_and_ticks_only_proven and test_done_or_to_test_task_is_left_unchanged.
AC #5: hermetic simulations cover all required cases and test_automerge_merges_manual_close_after_to_test_commit_checks verifies the new finalization commit is checked before merge.
AC #6: CLAUDE.md, .github/copilot-instructions.md and tools/coder/README.md consistently document per-criterion evidence, To Test and the explicit manual-close marker. The shared status rules were compared for consistency.
All implementation criteria have local evidence; task status and acceptance checkboxes remain unchanged pending the mandatory staging E2E gate.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged in PR #86. AC #1: tests review_json_with_malformed_criteria/without_criteria/must_cover_checked_and_unchecked. AC #2: unproven_automated_tags_block_even_an_approve_verdict, manual_tags_cannot_be_reported_as_proven. AC #3: mixed_evidence_sets_to_test_and_ticks_only_proven, missing_reviewer_preserves_existing_ticks. AC #4: all_criteria_proven_sets_done, manual_close_sets_to_test, done_or_to_test_task_is_left_unchanged. AC #5: 13 new stub simulations in tools/coder/tests. AC #6: CLAUDE.md, copilot-instructions, tools/coder/README.md in sync. Checks green on ef7e6b8 incl. e2e-pi.
<!-- SECTION:FINAL_SUMMARY:END -->
