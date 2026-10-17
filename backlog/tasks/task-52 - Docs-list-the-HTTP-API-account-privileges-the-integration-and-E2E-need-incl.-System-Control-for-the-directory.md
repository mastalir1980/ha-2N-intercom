---
id: TASK-52
title: >-
  Docs: list the HTTP API account privileges the integration and E2E need (incl.
  System - Control for the directory)
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-17 09:34'
updated_date: '2026-10-17 09:34'
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
1. Read docs/API_REFERENCE.md (privilege notes per endpoint) and the 2N function overview linked in the description; build the privilege -> feature table only from those sources.
2. README.md: add a subsection 'HTTP API account privileges' under '## Configuration' (before 'Initial setup') with the table and the note for missing System - Control. Replace the duplicated privilege sentences in 'Direct IO output switches' and 'Grant access vs. switch entities' with a short pointer to the table (keep the feature-specific error behaviour text).
3. e2e/README.md step 2: add System to the control list with the reason (dir/query - grant-access user names, TASK-48 E2E). Keep the rest of the step unchanged; the file stays in Czech.
4. Must not change: code, tests, e2e/ci, e2e/scripts, CHANGELOG.md, manifest version. No host names, IPs or the E2E intercom's device model (public repo).
<!-- SECTION:PLAN:END -->
