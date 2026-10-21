---
id: TASK-64
title: >-
  Nightly E2E fails in the deploy stage since 2026-10-16 (permissions in the
  staging config)
status: To Test
assignee:
  - '@copilot-mac'
created_date: '2026-10-18 16:40'
updated_date: '2026-10-21 09:40'
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
- [x] #1 Root cause confirmed and recorded in the task notes [jan]
- [x] #2 e2e/scripts/deploy.sh never writes custom_components on the Pi host: removing the old version, creating custom_components, extracting the archive and writing .e2e_deployed.json all happen inside one throwaway container of the staging HA image that mounts only <staging>/config, with --network none, after the staging container is stopped (same steps as the deploy command in e2e/ci/ha2n-staging) [unit]
- [x] #3 Both --ref and --worktree modes use that path; the old host-side rm/tar and the docker rm fallback are gone [unit]
- [x] #4 `bash e2e/e2e.sh wip` from the Mac deploys and is green while custom_components on staging is owned by root [e2e]
- [ ] #5 The next nightly run on the Pi deploys main and finishes green; e2e/reports/latest on the Pi shows it [jan]
- [x] #6 e2e/README.md and e2e/ci/README.md state the ownership rule: on staging, custom_components/2n_intercom is written only by root inside a throwaway container, by both the helper and deploy.sh [unit]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Preserve every staging/production guard in e2e/scripts/deploy.sh. Stop staging before streaming either archive mode into one network-isolated throwaway container of the staging HA image, mounting only the staging config and performing all removal, extraction and deployment metadata writes inside it. Match the helper positional JSON argument pattern without changing the helper.
2. Document the shared root-in-container ownership rule in e2e/README.md and e2e/ci/README.md.
3. Check shell syntax and available shellcheck; run Python 3.12+ unit tests, validate.py and compile checks. Run read-only e2e.sh wip and verify macOS worktree archive compatibility with the staging image tar and root-owned custom_components.
4. Record per-criterion evidence, leave manual/unverified criteria unchecked, and open the requested PR. User authorized continuing without live E2E on 2026-10-21; record that gate as blocked, not passed.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Not ready yet: needs the deploy log of a failed nightly run (ask the tester agent on the Pi to attach the excerpt).

Root cause confirmed on the Pi (2026-10-21). git archive puts a custom_components/ directory entry owned by root/root (uid 0) into the tar. The e2e-pi helper (e2e/ci/ha2n-staging) extracts that archive as root inside a throwaway container, so tar resets the owner of the existing <staging>/config/custom_components to root:root. The next nightly (deploy.sh, run as the staging user) removes the old 2n_intercom through its docker rm fallback, then 'tar -x' fails with Permission denied because custom_components is root-owned. Seen on the Pi: custom_components is root:root, mtime matches the nightly at 03:31 on 2026-10-20, and 2n_intercom is missing, so staging has no integration until the next e2e-pi deploy. A one-off chown of custom_components only lasts until the next PR deploy. Fix as planned: the nightly deploys through the same helper (sudo -u <staging-user> ha2n-staging deploy). Alternative: deploy.sh extracts inside a container like the helper. AC #1 is satisfied by this note.

Root cause confirmed on the Pi (2026-10-21). git archive puts a custom_components/ directory entry owned by root/root into the tar. The e2e-pi helper (e2e/ci/ha2n-staging) extracts it as root inside a throwaway container, so tar resets the owner of the existing <staging>/config/custom_components to root:root. The next nightly (e2e/scripts/deploy.sh, run as the staging user) removes the old 2n_intercom through its docker rm fallback, then the host-side `tar -x` fails with Permission denied. Seen on the Pi: custom_components is root:root, mtime matches the nightly at 03:31 on 2026-10-20, 2n_intercom is missing. The same failure hits `e2e.sh wip/run` from the Mac, which uses the same deploy.sh over SSH.

Implemented the shared root-in-container deployment ownership rule in deploy.sh; both archive modes stop staging first and use one throwaway staging-image container with --network none and only the config mount. JSON metadata is passed as a positional argument; its timestamp uses portable UTC date formatting on macOS. All staging/production guards and the restart/wait block are unchanged. Documented ownership and the required stop behavior of --no-restart in both READMEs. The helper, PR runner and workflows are unchanged.

Validation: Python 3.14.3, 704 unit tests passed; validate.py, py_compile, bash -n and git diff --check passed. Shellcheck is not installed. Offline SSH-mocked executions of --ref and --worktree verified archive contents, stop-before-extraction ordering, a single config mount, network isolation, the exact inline script and JSON arguments, propagation of extraction failure and both production guards. macOS bsdtar streams contain no AppleDouble files or Python caches. This does not prove compatibility with tar inside the HA image.

Live E2E blocked: bash e2e/e2e.sh wip initially stopped before deployment because the isolated worktree had no E2E virtual environment. A local Python 3.14 virtual environment and test dependencies were subsequently restored, but e2e/.env is still absent. On 2026-10-21 Jan explicitly selected continuing without live E2E and recording the blocker. No staging or production deployment was attempted. Compatibility with the HA image tar and deployment over root-owned custom_components remain unverified. Do not mark AC #4 proven or report the E2E gate green. The next nightly on main also remains manual.

AC #1: root cause confirmed by Jan on the Pi on 2026-10-21 (custom_components root:root, 2n_intercom missing after the 2026-10-20 nightly). AC #4: proven by Jan's 'bash e2e/e2e.sh wip' from the Mac on 2026-10-21 (report 20261021-113135): the working-tree archive deployed through the new container path, the tar in the HA image extracted the macOS bsdtar stream, staging came up, 20 passed and 4 skipped (relay and SIP tests, as expected). Note: AC #4 is tagged [e2e] but was proven by a Mac wip run, because the PR check e2e-pi deploys through the helper, not deploy.sh. AC #5 (next nightly on main) stays manual, so the task stays To Test.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented container-only staging deployment and documented the shared ownership rule. To Test as requested; live E2E is blocked, not green.

AC #1: Manual [jan]. Root cause supplied by Jan is recorded in the implementation notes; left unchecked as requested.
AC #2: Proven by offline execution of deploy.sh with mocked SSH, checking stop ordering, staging image, --network none, the single config mount, and all four write operations inside one container. Production guards are byte-for-byte unchanged.
AC #3: Proven by offline --ref HEAD and --worktree executions: both produce the same container command; the former host rm/tar and docker rm fallback are removed. Extraction failures propagate.
AC #4: Unproven/blocked. e2e.sh wip could not deploy from the isolated worktree; e2e/.env is absent. Jan authorized proceeding without live E2E. macOS bsdtar archive contents passed offline checks, but extraction with the HA image tar and root-owned staging were not verified.
AC #5: Manual [jan]. Await the next nightly after merge and its e2e/reports/latest evidence on the Pi; left unchecked.
AC #6: Proven by review of both README updates describing root-only writes inside one isolated throwaway staging-image container for both deploy entry points.

Checks: 704 unit tests passed on Python 3.14.3; validate.py, py_compile, bash -n, offline deploy checks and git diff --check passed. Shellcheck unavailable. No relay tests or production operations were run.
<!-- SECTION:FINAL_SUMMARY:END -->
