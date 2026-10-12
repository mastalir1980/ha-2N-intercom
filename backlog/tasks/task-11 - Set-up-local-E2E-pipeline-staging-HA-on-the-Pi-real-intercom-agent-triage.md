---
id: TASK-11
title: 'Set up local E2E pipeline: staging HA on the Pi + real intercom + agent triage'
status: In Progress
assignee: []
created_date: '2026-10-11 13:37'
updated_date: '2026-10-11 18:22'
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
Unit tests with stubs (and the planned GitHub CI in TASK-3) cannot catch problems that only show up on a real Home Assistant talking to a real 2N device: HA release changes, intercom firmware changes, event-subscription behaviour, entity availability. We want an agent-runnable pipeline on Jan's Mac that deploys the latest integration to a staging HA on Rob's Berry (separate container ha-staging, port 8124, never the production HA), tests it against the home IP Verso (fw 2.50 LTS), and files failures as Backlog.md bugs. Decisions (2026-10-11): staging HA instead of production; nightly runs are read-only, relays are switched only in manual runs with confirmation; the agent only tests and reports, it does not implement fixes; target is the home Verso only. Code lives in e2e/ (see e2e/README.md); verified end-to-end against mock HA/2N servers, not yet against the real Pi and intercom.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 e2e/.env filled in and 'bash e2e/e2e.sh bootstrap' creates the staging HA, token and 2N config entry on the Pi
- [x] #2 'bash e2e/e2e.sh run' is green against the home IP Verso
- [ ] #3 'bash e2e/e2e.sh relays' passes for the relays listed in E2E_RELAY_NUMBERS
- [x] #4 A deliberately broken build produces a deduplicated bug task via the triage agent
- [ ] #5 Nightly launchd job installed ('bash e2e/e2e.sh schedule') and its first run logged in e2e/reports/nightly.log
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Pipeline code is written (e2e/). Remaining steps are on Jan's Mac: setup -> fill .env -> bootstrap -> run -> relays -> break-build check -> schedule.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-11: first real runs done (bootstrap OK on robsberry, staging port 8124). Correction: the target device is a 2N IP Force 2.0 on fw 3.3.1.82.4 (2N OS 3.x Active track), not an IP Verso on 2.50 — the pipeline is therefore the first test of the integration against 3.x. Findings filed by the triage agent: TASK-12 (code 7 'invalid connection type' + silent failure), TASK-13 (E2E API account lacks Switch privilege).

Validation: bootstrap OK; report e2e/reports/20261011-201937 green (11 passed, 2 skipped: SIP sensor disabled by default, relay test manual-only). Remaining: relay run, broken-build triage check (already observed in practice: agent filed TASK-12/13 and deduplicated on rerun), nightly schedule.

AC #4 evidence: real failing runs 20261011-175902 / -180751 — triage agent created TASK-12 + TASK-13 and on the rerun appended occurrences instead of duplicating.
<!-- SECTION:NOTES:END -->
