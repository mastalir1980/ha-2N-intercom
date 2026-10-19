---
id: TASK-59
title: >-
  Tester agent on the Pi: verify [tester] criteria of To Test tasks on staging
  with a fixed read-only toolbox
status: To Do
assignee:
  - '@copilot-mac'
created_date: '2026-10-18 15:50'
updated_date: '2026-10-18 16:40'
labels:
  - infra
  - agent
  - manual-path
dependencies:
  - TASK-36
  - TASK-57
priority: medium
ordinal: 66000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
After the merge, criteria tagged [tester] are verified by the tester agent (Hermes on the Pi, LAN access to staging HA and the E2E intercom). The agent never gets a free shell for the device: it calls only a deterministic toolbox in tools/tester/ that Jan reviews. Read-only: no relays, no call control, never production HA (port 8123), never prints values from e2e/.env.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 tools/tester/ provides: deploy main to staging (via e2e/ci/ha2n-staging under the shared lock), read-only 2N GET on an allowlist of endpoints using the E2E read-only account, staging HA REST reads (states, config flows in progress, diagnostics), staging log grep, SSDP probe
- [ ] #2 Every command refuses port 8123, switch/relay endpoints and call control endpoints (call/dial, call/answer, call/hangup) - unit tests for each refusal
- [ ] #3 No command output contains values from e2e/.env - test with a fake env file
- [ ] #4 Runs only under e2e/scripts/lock.sh and never overlaps an e2e-pi run
- [ ] #5 Report per task in tools/tester/report.schema.json shape: task id, main commit, per criterion {id, verdict pass|fail|blocked, evidence = command + redacted output excerpt}; posted as a comment on the merged PR
- [ ] #6 A failing criterion becomes a Backlog bug per e2e/agent/triage.md (type bug, label tester) instead of being ticked
- [ ] #7 docs/TESTER.md (Czech) is the operating brief for the agent: trigger, steps, allowed commands, forbidden actions, report format
- [ ] #8 Dry run on TASK-49: staging HA lists the discovered intercom flow; report posted with evidence
- [ ] #9 The tester can read PR check results (e2e-pi, validate) and PR comments with a read-only GitHub token or the public REST API; the token is stored outside the repo and never printed
<!-- AC:END -->
