---
id: DRAFT-1
title: 'Per-button doorbell: tell which call button was pressed'
status: Draft
assignee: []
created_date: '2026-10-13 19:54'
labels:
  - ring-detection
  - needs-design
dependencies: []
references:
  - docs/API_REFERENCE.md
  - custom_components/2n_intercom/coordinator.py
  - custom_components/2n_intercom/binary_sensor.py
  - 'https://github.com/mastalir1980/ha-2N-intercom/issues/10'
priority: low
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: multi-button intercoms (IP Verso with several buttons, IP Force 2/4-button, MDU installations) serve more apartments or purposes, but the integration has one doorbell for the whole device. Users cannot automate "button 2 = office" today; the only workaround is the called_id peer filter, which is one filter per config entry.

Evidence (TASK-29, IP Force 2.0 fw 3.3.x): a visitor button press emits CallSessionStateChanged with originator=button and info="<button number>" (info="1" observed). CallStateChanged carries the dialled peer. A call into the intercom has originator=incoming and no info. See docs/API_REFERENCE.md, firmware quirks section.

Not decided yet (Jan: "needs thinking") - this draft is NOT ready for @copilot:
- Shape: one binary_sensor per button vs. one doorbell event entity (TASK-5) with the button number as an attribute / event type vs. both.
- How to learn the button list and names (which 2N API exposes configured buttons and their labels? keypad / display directory calls have no button number).
- Behaviour on fw that does not send originator/info (fw 2.50 unverified).
- Relation to the called_id filter (replace, keep, or migrate).
Depends on the ring-detection fix that follows TASK-29.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Design decision on entity shape and button discovery is recorded in this task and approved by Jan
- [ ] #2 Button number of a ring is available in HA for automations, verified on the IP Force with a real button press
- [ ] #3 A call into the intercom never fires any per-button doorbell
<!-- AC:END -->
