---
id: TASK-66
title: >-
  Spike: real firmware update through GET /api/autoupdate/updatefw - which
  source and track does it use
status: To Do
assignee: []
created_date: '2026-10-19 19:15'
labels:
  - firmware
  - investigation
  - manual-close
milestone: m-1
dependencies: []
references:
  - docs/API_REFERENCE.md
priority: medium
type: spike
ordinal: 71000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Step B of the updatefw investigation for TASK-65. Step A (2026-10-19, docs/API_REFERENCE.md 'Vestavěná aktualizace') showed: with no newer firmware on any track, updatefw answers 200 {"success": true} in ~70 ms and nothing happens; there is no status endpoint and no log event. Open: when a newer firmware exists, which version does updatefw install - the track and source set in the device (AutoUpdate.UpdateServer.UpgradeMode / AutoUpdate.UpdateSource) or always the newest from the 2N update server? This decides whether the HA firmware_channel option (TASK-51) can drive Install in TASK-65.

Run only with Jan present and on his explicit go, when the 2N update server offers a newer firmware for the E2E intercom. It installs real firmware and reboots the device.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Before the test Jan sets the device track in the web UI to a track that differs from the newest offer (e.g. LTS while Active track has a newer version) and the update server answers for all three tracks are recorded [jan]
- [ ] #2 updatefw is called once; the answer, the time until the reboot and the swVersion after the reboot are recorded; it is clear which track was installed (or that nothing was installed) [jan]
- [ ] #3 docs/API_REFERENCE.md 'Vestavěná aktualizace' updated with the result (no host names, no exact device build) and TASK-65 updated (open question 1 answered, channel option decision recorded) [unit]
<!-- AC:END -->
