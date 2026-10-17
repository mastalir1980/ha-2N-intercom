---
id: TASK-52
title: >-
  Docs: list the HTTP API account privileges the integration and E2E need (incl.
  System - Control for the directory)
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-17 09:34'
updated_date: '2026-10-17 09:52'
labels:
  - docs
milestone: m-0
dependencies: []
references:
  - README.md
  - e2e/README.md
  - docs/API_REFERENCE.md
  - TASK-48
priority: low
type: docs
ordinal: 59000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: TASK-48's E2E check failed on PR #71 with 2N error code 10 (insufficient privileges) on /api/dir/query. 2N documents all /api/dir/* functions under the System service group with the System - Control privilege; the E2E account only had System - Monitoring. Enabling System - Control made e2e-pi green. Neither README.md nor e2e/README.md lists this privilege, so users and the E2E setup end up with accounts that silently lose directory features (user names for access events, called-ID peers, grant-access user list -> directory_unavailable in the options flow).

Current: README.md mentions privileges only per feature (I/O control under 'Direct IO output switches', Access Control - Control under 'Grant access vs. switch entities'). e2e/README.md step 2 lists monitoring: System, Switch, I/O, Phone/Call, Camera, Logging; control: Switch, I/O, Phone/Call. System - Control is missing in both.

Expected: one table in README.md of HTTP API account privileges per feature, and a corrected list in e2e/README.md. Facts about privileges come from docs/API_REFERENCE.md and the 2N HTTP API docs (https://wiki.2n.com/hip/hapi/latest/en/5-prehled-funkci-http-api); do not invent privileges not stated there.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 README.md has a section (under Configuration) with a table: privilege (group - Monitoring/Control) -> features that need it, covering at least System - Monitoring, System - Control (dir/query: called-ID peers, grant-access user list, user names for access events), Switches, I/O, Phone/Calls, Camera, Access Control - Control (grant_access)
- [ ] #2 README.md says what happens without System - Control: the integration works, but directory features degrade and the options device step shows directory_unavailable; it also notes that System - Control allows system configuration changes, so users know what they grant
- [ ] #3 The existing per-feature privilege notes in README.md (Direct IO output switches, Grant access vs. switch entities) point to the new table instead of duplicating or contradicting it
- [ ] #4 e2e/README.md step 2 lists System - Control for the E2E account with the reason (dir/query, TASK-48 E2E check)
- [ ] #5 No code or tests change; validate.py green; PR check e2e-pi green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Read docs/API_REFERENCE.md and the official 2N HTTP API function overview to confirm privilege-to-feature mappings.
2. Add the HTTP API account privileges table under Configuration before Initial setup in README.md, explain directory degradation and System - Control risks, and replace per-feature privilege duplication with table links while preserving error behaviour.
3. Add System - Control and its dir/query / TASK-48 rationale to step 2 of e2e/README.md in Czech, leaving the rest unchanged.
4. Keep code, tests, protected paths, CHANGELOG.md and manifest version unchanged. Run the three required local Python gates, record implementation notes, and commit locally on the existing branch; leave acceptance criteria unchecked and status In Progress for the orchestrator.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added README Configuration > HTTP API account privileges with privilege-to-feature mappings for System, Switches, I/O, Phone/Calls, Camera and Access Control, plus links to the official 2N function overview/log subscription documentation and docs/API_REFERENCE.md. Documented missing System - Control degradation, the non-blocking directory_unavailable options error, retained saved UUIDs, and the broader system-configuration permission. Replaced the direct-output and grant-access privilege duplication with links while preserving error behaviour.
Updated only the control list in e2e/README.md step 2 and its System - Control rationale (/api/dir/query, grant-access user names, TASK-48). Code, tests, protected paths, CHANGELOG.md and manifest are unchanged.
Local gates on Python 3.12.15 passed: all 655 unit tests, python3 validate.py, and py_compile for the integration; git diff --check passed. No device/E2E commands were run. The orchestrator must obtain a green e2e-pi PR check before finalization; status remains In Progress and all acceptance criteria remain unchecked.
<!-- SECTION:NOTES:END -->
