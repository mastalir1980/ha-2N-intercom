---
id: TASK-64
title: >-
  Nightly E2E fails in the deploy stage since 2026-10-16 (permissions in the
  staging config)
status: To Do
assignee:
  - '@copilot-mac'
created_date: '2026-10-18 16:40'
updated_date: '2026-10-21 08:16'
labels:
  - e2e
  - infra
  - manual-path
dependencies: []
references:
  - e2e/nightly.sh
  - e2e/scripts/deploy.sh
  - e2e/ci/ha2n-staging
  - e2e/ci/pr-e2e.sh
  - e2e/ci/README.md
priority: high
type: bug
ordinal: 69000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Reported by the tester agent on 2026-10-18: every nightly E2E run (e2e/nightly.sh, started by Hermes) fails in the deploy stage since 2026-10-16; the last green nightly report is from 2026-10-14. Symptom as reported: root-owned files in the staging config directory. The PR check e2e-pi deploys through the root-owned helper e2e/ci/ha2n-staging as the staging user and is green on every PR (#54 to #83), so only the nightly path is broken. Hypothesis (not verified): since the PR runner (TASK-22) the staging config is written by the staging user or by root from the HA container, and e2e/scripts/deploy.sh, run by the nightly as a different user, can no longer remove or write custom_components/2n_intercom (deploy.sh falls back to a throwaway container only for rm, not for tar -x or the .e2e_deployed.json write). Consequence: no clean E2E run on main between PRs; evidence for criteria that need an E2E run on main (e.g. a release) is missing.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Root cause confirmed with the deploy log of a failed nightly run (excerpt without host names or secrets in the task notes)
- [ ] #2 The nightly run deploys and finishes green on main; e2e/reports/latest shows the run
- [ ] #3 The nightly and the PR check e2e-pi share one deploy path or one ownership rule, so the two cannot break each other again; e2e/README.md and e2e/ci/README.md describe it
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Get the failing deploy log from the Pi (e2e/reports/<timestamp>/ of a nightly after 2026-10-16). Compare file ownership under the staging config with the user the nightly uses. Preferred fix: the nightly deploys through the same helper (sudo -u <staging-user> ha2n-staging deploy) instead of e2e/scripts/deploy.sh over SSH. Protected paths (e2e/nightly.sh, e2e/scripts/, e2e/ci/) need Jan's review.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Not ready yet: needs the deploy log of a failed nightly run (ask the tester agent on the Pi to attach the excerpt).

Root cause confirmed on the Pi (2026-10-21). git archive puts a custom_components/ directory entry owned by root/root (uid 0) into the tar. The e2e-pi helper (e2e/ci/ha2n-staging) extracts that archive as root inside a throwaway container, so tar resets the owner of the existing <staging>/config/custom_components to root:root. The next nightly (deploy.sh, run as the staging user) removes the old 2n_intercom through its docker rm fallback, then 'tar -x' fails with Permission denied because custom_components is root-owned. Seen on the Pi: custom_components is root:root, mtime matches the nightly at 03:31 on 2026-10-20, and 2n_intercom is missing, so staging has no integration until the next e2e-pi deploy. A one-off chown of custom_components only lasts until the next PR deploy. Fix as planned: the nightly deploys through the same helper (sudo -u <staging-user> ha2n-staging deploy). Alternative: deploy.sh extracts inside a container like the helper. AC #1 is satisfied by this note.
<!-- SECTION:NOTES:END -->
