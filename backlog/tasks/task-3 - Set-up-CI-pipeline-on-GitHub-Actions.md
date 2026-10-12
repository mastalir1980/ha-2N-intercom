---
id: TASK-3
title: Set up CI pipeline on GitHub Actions
status: To Do
assignee: []
created_date: '2026-08-30 09:27'
labels:
  - ci
  - quality
dependencies:
  - TASK-1
priority: high
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add a GitHub Actions workflow so every PR and push to main runs the full validation suite. Jobs: (1) unit tests: python3 -m unittest discover -s tests -t tests; (2) python3 validate.py (manifest + HACS compliance); (3) syntax check: python3 -m py_compile custom_components/2n_intercom/*.py; (4) hassfest validation action (home-assistant/actions/hassfest); (5) HACS validation action (hacs/action). Use a Python version matching current Home Assistant requirements. Add a status badge to README.md.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Workflow file exists under .github/workflows/ and triggers on pull_request and push to main
- [ ] #2 Unit tests, validate.py and py_compile run as separate steps/jobs
- [ ] #3 hassfest and HACS validation actions run and pass
- [ ] #4 README.md shows a CI status badge
<!-- AC:END -->
