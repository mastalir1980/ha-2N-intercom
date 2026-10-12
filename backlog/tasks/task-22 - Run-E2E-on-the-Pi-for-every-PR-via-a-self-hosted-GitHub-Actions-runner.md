---
id: TASK-22
title: Run E2E on the Pi for every PR via a self-hosted GitHub Actions runner
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-12 17:50'
updated_date: '2026-10-12 18:02'
labels:
  - e2e
  - ci
  - infra
dependencies: []
references:
  - e2e/run.sh
  - e2e/scripts/deploy.sh
  - e2e/nightly.sh
  - e2e/tests/conftest.py
modified_files:
  - .github/workflows/e2e-pi.yml
  - e2e/ci/ha2n-staging
  - e2e/ci/pr-e2e.sh
  - e2e/ci/install-pi.sh
  - e2e/ci/ci_summary.py
  - e2e/ci/README.md
  - e2e/scripts/lock.sh
  - e2e/run.sh
priority: high
type: task
ordinal: 29000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
First building block of an autonomous pipeline: a coding agent on a separate VM (outside the home network) pushes branches; the Pi, which can reach the intercom, must test them without a VPN. GitHub is the only channel: the Pi runs a self-hosted Actions runner (outbound-only) and reports a check on the PR. The repo is public and any push-access workflow can target a self-hosted runner, so the runner user is treated as UNTRUSTED: it has no docker access (production HA runs on the same Pi) and reaches staging only through a fixed, root-owned sudo helper. Physical safety does not rely on test code: the E2E/staging 2N account has Monitoring but no Control privilege, so code from a branch cannot open the door. Full reports stay on the Pi; the PR only gets a sanitised summary. Decisions confirmed by Jan on 2026-10-12: tests come from the PR branch + read-only 2N account; full reports on the Pi; Claude writes this infra.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Workflow .github/workflows/e2e-pi.yml runs on pull_request_target (workflow from main) only for same-repo PRs whose author and actor are in the E2E_PI_ACTORS repo variable, on a runner labelled ha2n-pi, one run at a time
- [ ] #2 The runner user has no docker group; deploy, container logs and the staging lock go only through e2e/ci/ha2n-staging installed root-owned and allowed via sudoers as the staging user
- [ ] #3 The helper refuses non-hex SHAs, commits not reachable from an origin branch, deploys without holding the lock, and anything other than the staging container/dir
- [ ] #4 Mac/nightly runs (e2e/run.sh) and CI runs share one staging lock so two deploys never overlap
- [ ] #5 The PR check shows a sanitised summary (no IPs, MACs, hostnames or account names); full report stays under /var/lib/ha2n-ci/reports on the Pi
- [ ] #6 Runbook e2e/ci/README.md (Czech) covers install, runner registration, read-only 2N account, GitHub settings and the first experiment
- [ ] #7 First experiment done: a trivial branch PR gets a green e2e-pi check from the Pi and production HA is untouched
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. e2e/scripts/lock.sh: staging lock (mkdir lock dir in PI_STAGING_DIR, owner+epoch, stale break) used by run.sh.
2. e2e/ci/ha2n-staging: self-contained helper (lock/unlock/deploy/logs), config from /etc/ha2n-ci/staging.conf, fetches into its own bare mirror, deploys like deploy.sh.
3. e2e/ci/pr-e2e.sh: orchestrator run by the runner (lock, deploy via helper, prune, pytest from the PR checkout with /etc/ha2n-ci/e2e.env, logs, summary, unlock).
4. e2e/ci/ci_summary.py: sanitised markdown summary from junit/summary/context.
5. e2e/ci/install-pi.sh: one-time sudo install (user, helper, sudoers, config, env template, venv).
6. .github/workflows/e2e-pi.yml with guards + concurrency.
7. e2e/ci/README.md runbook; pointers in e2e/README.md, CLAUDE.md, copilot-instructions.md (.github/ and e2e/ci/ changes = human review only).
8. Static checks (bash -n, shellcheck if available, py_compile, actionlint if available); Jan runs install + first experiment.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-12 (Claude): implemented in working tree (not committed): .github/workflows/e2e-pi.yml, e2e/ci/{ha2n-staging,pr-e2e.sh,install-pi.sh,ci_summary.py,README.md}, e2e/scripts/lock.sh, lock in e2e/run.sh, pointers in e2e/README.md, CLAUDE.md, .github/copilot-instructions.md. Static checks: bash -n + shellcheck (warning level) clean, actionlint clean except the custom runner label, ci_summary redaction self-test, lock.sh and helper lock/unlock/validation simulated locally; helper deploy (docker) not runnable off the Pi. Independent security review applied: root-owned compose (/etc/ha2n-ci/staging-compose.yml), stop + remove/extract inside a throwaway container (symlink escape to prod), atomic stale-lock break with mtime fallback, per-PR concurrency group, base.ref == default branch guard, unlock before logs + INT/TERM trap, requirements via stdin (0700 homes). Accepted residual risk for phase 1: branch code shares the runner uid (can fake the check) -> e2e-pi alone never justifies auto-merge. Remaining: Jan installs on the Pi, read-only 2N account + reset-entry, runner registration, E2E_PI_ACTORS, first experiment (AC #7).
<!-- SECTION:NOTES:END -->
