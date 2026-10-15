---
id: TASK-11
title: 'Set up local E2E pipeline: staging HA on the Pi + real intercom + agent triage'
status: Done
assignee: []
created_date: '2026-10-11 13:37'
updated_date: '2026-10-15 12:47'
labels:
  - e2e
  - infra
dependencies: []
references:
  - e2e/README.md
priority: high
type: task
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Unit tests with stubs (and the planned GitHub CI in TASK-3) cannot catch problems that only show up on a real Home Assistant talking to a real 2N device: HA release changes, intercom firmware changes, event-subscription behaviour, entity availability. We want an agent-runnable pipeline on Jan's Mac that deploys the latest integration to a staging HA on the Pi (separate container ha-staging, port 8124, never the production HA), tests it against the E2E intercom (fw 3.x; originally planned as the IP Verso fw 2.50), and files failures as Backlog.md bugs. Decisions (2026-10-11): staging HA instead of production; nightly runs are read-only, relays are switched only in manual runs with confirmation; the agent only tests and reports, it does not implement fixes; target is the E2E intercom only. Code lives in e2e/ (see e2e/README.md); verified end-to-end against mock HA/2N servers, not yet against the real Pi and intercom.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 e2e/.env filled in and 'bash e2e/e2e.sh bootstrap' creates the staging HA, token and 2N config entry on the Pi
- [x] #2 'bash e2e/e2e.sh run' is green against the home IP Verso
- [x] #3 'bash e2e/e2e.sh relays' passes for the relays listed in E2E_RELAY_NUMBERS
- [x] #4 A deliberately broken build produces a deduplicated bug task via the triage agent
- [x] #5 Nightly run is scheduled and has produced its first report: nightly runs on the Pi (not the launchd job on the Mac originally planned), report e2e/reports/20261012-033028 on the Pi
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Pipeline code is written (e2e/). Remaining steps are on Jan's Mac: setup -> fill .env -> bootstrap -> run -> relays -> break-build check -> schedule.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-11: first real runs done (bootstrap OK on the Pi, staging port 8124). Correction: the target device is the E2E intercom on fw 3.x, not an IP Verso on 2.50 — the pipeline is therefore the first test of the integration against 3.x. Findings filed by the triage agent: TASK-12 (code 7 'invalid connection type' + silent failure), TASK-13 (E2E API account lacks Switch privilege).

Validation: bootstrap OK; report e2e/reports/20261011-201937 green (11 passed, 2 skipped: SIP sensor disabled by default, relay test manual-only). Remaining: relay run, broken-build triage check (already observed in practice: agent filed TASK-12/13 and deduplicated on rerun), nightly schedule.

AC #4 evidence: real failing runs 20261011-175902 / -180751 — triage agent created TASK-12 + TASK-13 and on the rerun appended occurrences instead of duplicating.

2026-10-12 closing (Claude, approved by Jan): AC #3 evidence: relay runs 20261012-124448 and 20261012-131421 (--relays) passed incl. test_relay_roundtrip[1] and test_grant_access_is_logged_by_device (see TASK-8 notes). AC #5 reworded to match reality: the nightly runs on the Pi; its run 20261012-033028 (trigger 'nightly', branch origin/e2e-pipeline) is the first logged nightly report; it failed on orphaned entities, fixed by TASK-20. AC #2 text still says 'IP Verso' for history; the green run was against the E2E intercom fw 3.x (report 20261011-201937). Description updated to the E2E intercom target.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Local E2E pipeline in place and merged to main (TASK-21.2): staging HA on the Pi (port 8124) bootstrapped by e2e.sh, read-only runs against the E2E intercom fw 3.x, manual relay runs, Backlog triage agent with deduplication, nightly multi-branch runs on the Pi with orphan-entity pruning (TASK-20). Verified by reports 20261011-201937 (green), 20261012-131421 (relays green), triage runs 20261011-175902/-180751 and nightly 20261012-033028.
<!-- SECTION:FINAL_SUMMARY:END -->
