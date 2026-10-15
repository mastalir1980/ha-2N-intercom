---
id: TASK-38
title: >-
  Do not publish the intercom model and firmware build in the public e2e-pi
  check summary
status: To Do
assignee:
  - '@copilot-mac'
created_date: '2026-10-15 12:48'
updated_date: '2026-10-15 12:48'
labels:
  - ci
  - security
  - manual-path
dependencies: []
references:
  - e2e/ci/ci_summary.py
  - e2e/ci/README.md
priority: medium
type: bug
ordinal: 46000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The repo is public, so the e2e-pi check summary written by e2e/ci/ci_summary.py is readable by anyone. main() prints '- intercom: <variant> fw <swVersion>' from context.json (e2e/ci/ci_summary.py:75), which publishes the exact model and firmware build of the E2E intercom. The rest of the summary is already masked (IPs, MACs, host names, serials, env values). Expected: the public summary shows only the firmware major version (e.g. 'fw 3.x') and no model; the full values stay in the private report on the Pi (/var/lib/ha2n-ci/reports/). The private Telegram summary (e2e/scripts/summary.py) is out of scope.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The e2e-pi summary line for the intercom shows only the firmware major version ('fw 3.x', or 'fw ?' when swVersion is missing) and never the variant/model or the full build
- [ ] #2 Unit test in e2e/unit/ covers ci_summary main() with a context.json containing variant + full swVersion and asserts neither appears in the output
- [ ] #3 Masking of IPs, MACs, host names, serials and env values is unchanged (existing tests stay green)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. e2e/ci/ci_summary.py main(): replace the intercom line with a helper that maps swVersion '3.3.1.82.4' -> 'fw 3.x' (first number only; '?' when missing); drop dev['variant'].
2. Add e2e/unit/test_ci_summary.py (or extend the existing ci_summary test if there is one) with a fake report dir.
3. Do not touch the guards in e2e/ci/ (job hook, helper, lock) or e2e-pi.yml. Protected path: Jan reviews the PR.
<!-- SECTION:PLAN:END -->
