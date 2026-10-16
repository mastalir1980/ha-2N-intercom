---
id: TASK-44
title: >-
  Docs: note that relays appear only after they are enabled in the intercom
  settings
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-15 16:37'
updated_date: '2026-10-16 15:27'
labels:
  - docs
milestone: m-0
dependencies:
  - TASK-43
priority: low
type: docs
ordinal: 51000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: a user who activated the relay/switch function on the intercom did not understand that the relay entities appear only after it is enabled in the intercom settings, and that without an enabled relay nothing is shown in Home Assistant. The integration creates relay entities from /api/switch/caps, which lists only enabled relays. Expected behaviour: the user documentation says that if no relay appears, the relay must first be enabled in the intercom's own administration (web interface), and that the integration cannot enable it. The options flow stays as it is.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 README.md (section on relays / the relay control entities) states that relays appear only when enabled in the intercom settings and that the integration does not enable them
- [ ] #2 INSTALLATION.md gets the same note in its troubleshooting or relay section, if such a section exists
- [ ] #3 The wording avoids mentioning admin account names or device-specific paths; uses the neutral term 'intercom settings'
- [ ] #4 validate.py green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. README.md, section "### Door / Gate / Relay control" (~line 46): after the bullet "Relays auto-discovered from `/api/switch/caps`" add a note: only relays that are enabled in the intercom settings are reported by the device and get entities; if no relay entity appears, enable the relay (switch) in the intercom settings first and reload the integration; the integration cannot enable relays itself.
2. README.md, "### Initial setup" paragraph (~line 181, "Relays are not configured during initial setup …"): add the same point in one sentence, linking to the section from step 1.
3. INSTALLATION.md, "## Troubleshooting" (~line 109): add a subsection "### No relay entities appear" with the note from step 1 (enable the relay in the intercom settings, then reload the integration from Settings → Devices & Services). Also add one sentence to "### 5. Verify in Home Assistant" next to the switch/cover entity lines (~line 64).
4. Wording: neutral terms only ("intercom settings", "the intercom's web interface"); no admin account names, menu paths specific to one firmware, host names or device models (public repo rule in CLAUDE.md).
5. Do not change code, strings or translations; the options flow stays as it is. Do not describe the per-relay options step in new text (TASK-42 may remove it).
6. Validation: `python3 validate.py` green. Docs-only change, so the E2E path filter skips `e2e-pi` only if the PR touches nothing but `docs/**/*.md`; README.md/INSTALLATION.md are outside that filter, so `e2e-pi` runs and must be green.
<!-- SECTION:PLAN:END -->
