---
id: TASK-70
title: >-
  CI: hacs.yml and hassfest.yml run third-party actions from mutable refs with
  default GITHUB_TOKEN permissions
status: To Do
assignee:
  - '@copilot-mac'
created_date: '2026-10-21T09:44:00Z'
labels:
  - security
  - bug
  - ci
  - manual-path
dependencies: []
references:
  - .github/workflows/hacs.yml
  - .github/workflows/hassfest.yml
  - .github/workflows/e2e-pi.yml
  - docs/SECURITY-REVIEW-v1.5.0.md
priority: low
type: bug
ordinal: 75000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the security review before v1.5.0 (docs/SECURITY-REVIEW-v1.5.0.md, finding S-4). Supply-chain hardening, low likelihood (official HA / HACS actions) but cheap.

**Current behaviour.** `.github/workflows/hacs.yml` uses `hacs/action@main`, `hassfest.yml` uses `home-assistant/actions/hassfest@master`; neither declares a `permissions:` block, so on `push` to `main` the job runs with the repository's default GITHUB_TOKEN permissions (write scopes unless the repo setting restricts them). `e2e-pi.yml` already sets `contents: read` but uses `actions/checkout@v4` (a movable tag). A compromised or hijacked upstream ref would run with those scopes on every push to main.

**Expected behaviour.** Every workflow declares the least privilege it needs (`permissions: contents: read`), every third-party action is pinned to a full commit SHA with the version in a trailing comment, and Dependabot keeps the pins current. Changes to `.github/` need Jan's review (manual-path).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 hacs.yml and hassfest.yml declare permissions: contents: read at the workflow level [unit]
- [ ] #2 Every uses: of a third-party action in .github/workflows is pinned to a full 40-char commit SHA with the version tag in a comment [unit]
- [ ] #3 A .github/dependabot.yml entry for the github-actions ecosystem (weekly) keeps the pins updated [unit]
- [ ] #4 HACS, hassfest and e2e-pi still pass on a PR and on push to main [jan]
<!-- AC:END -->
