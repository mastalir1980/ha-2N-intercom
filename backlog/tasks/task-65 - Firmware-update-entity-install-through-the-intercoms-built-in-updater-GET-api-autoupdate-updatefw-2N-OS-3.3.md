---
id: TASK-65
title: >-
  Firmware update entity: install through the intercom's built-in updater (GET
  /api/autoupdate/updatefw, 2N OS 3.3+)
status: To Do
assignee: []
created_date: 2026-10-19 14:57
updated_date: '2026-10-24T08:29:00Z'
labels:
  - firmware
  - update-entity
  - manual-close
  - on-hold
milestone: m-1
dependencies:
  - TASK-51
  - TASK-66
references:
  - docs/API_REFERENCE.md
  - custom_components/2n_intercom/update.py
  - custom_components/2n_intercom/api.py
priority: medium
type: feature
ordinal: 70000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up of TASK-51 (shows the installed version, whether the 2N update server has a newer one, and links to the web UI). Goal: an Install action in the HA update entity that only triggers the intercom's own updater; HA downloads and uploads nothing.

Facts:
- Since 2N OS 3.3 the device has GET /api/autoupdate/updatefw, which starts the firmware update on the device; it needs the System Control privilege (confirmed by Jan with the 2N firmware team, 2026-10-19). Not in the public HTTP API manual 3.3.
- Step A (2026-10-19, E2E intercom, update server 204 on all tracks): updatefw answers 200 {"success": true} in ~70 ms and the device does nothing (no reboot, swVersion unchanged). So success only means 'command accepted', not 'update running'. There is no status endpoint (/api/autoupdate, /status, /caps -> code 2 invalid request path) and no update-related log event. Details: docs/API_REFERENCE.md 'Vestavěná aktualizace'.

Open question (blocks this task, answered by TASK-66): when a newer firmware exists, does updatefw install the device's configured track/source or always the newest from the 2N update server? That decides whether Install may be offered for the HA firmware_channel option or must warn that the device setting applies.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Install appears only on devices with 2N OS 3.3 or newer (swVersion check); older devices keep the read-only entity from TASK-51 [unit]
- [ ] #2 Install never runs automatically and never on a downgrade [unit]
- [ ] #3 No E2E test calls updatefw by default; an install test, if added, is marked and excluded from default and wip runs [unit]
- [ ] #4 Jan installs a real update on the E2E intercom from HA and the entity shows the new installed_version [jan]
- [ ] #5 Install calls only GET /api/autoupdate/updatefw (System Control privilege) on the existing dual-auth request path with the usual 2N error parsing; a missing privilege (codes 7-10) and other device errors raise a translated HomeAssistantError and leave no in_progress state [unit]
- [ ] #6 Install is offered only when the update entity shows a newer latest_version; after updatefw returns success the entity is in_progress until /api/system/info swVersion changes after a reboot; if the device neither reboots nor changes swVersion within a timeout, a translated error says the device did not start the update (check its update source and track) and in_progress is cleared [unit]
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 (Jan, v1.6.0 planning): TASK-65/66 stay in v1.6.0 but do not block its release. If 2N has not published a newer firmware for the E2E intercom (so TASK-66 cannot run) when every other v1.6.0 task is Done, both move to the next milestone.
<!-- SECTION:NOTES:END -->
