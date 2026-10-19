---
id: TASK-65
title: >-
  Firmware update entity: install through the intercom's built-in updater (GET
  /api/autoupdate/updatefw, 2N OS 3.3+)
status: To Do
assignee: []
created_date: '2026-10-19 14:57'
updated_date: '2026-10-19 18:14'
labels:
  - firmware
  - update-entity
  - manual-close
  - on-hold
milestone: m-1
dependencies:
  - TASK-51
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

Facts (confirmed by Jan with the 2N firmware team, 2026-10-19): since 2N OS 3.3 the device has GET /api/autoupdate/updatefw, which starts the firmware update on the device. It works from 3.3 on and needs the System Control privilege (same as /api/firmware). It is not in the public HTTP API manual 3.3. It must never be called by tests or E2E without Jan's explicit request, because it starts a real update and a reboot.

Open questions (resolve with Jan before this task is ready):
1. Which source and version does updatefw install: the device's configured AutoUpdate source and track (Active track / LTS / Beta), or always the newest version from the 2N update server? What happens with source 'managed externally' or auto-provisioning? This decides whether the HA channel option from TASK-51 stays or must follow the device.
2. Response and errors: does it return at once and update in the background? Codes when nothing to install or an update is already running?
3. Is there a 3.3+ endpoint for the available version, progress or last result?
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Install appears only on devices with 2N OS 3.3 or newer (swVersion check); older devices keep the read-only entity from TASK-51 [unit]
- [ ] #2 After a successful trigger in_progress is true until /api/system/info swVersion changes to a newer version or a timeout (translated error); the coordinator and log subscription recover through their existing backoff [unit]
- [ ] #3 Install never runs automatically and never on a downgrade [unit]
- [ ] #4 No E2E test calls updatefw by default; an install test, if added, is marked and excluded from default and wip runs [unit]
- [ ] #5 Jan installs a real update on the E2E intercom from HA and the entity shows the new installed_version [jan]
- [ ] #6 Install calls only GET /api/autoupdate/updatefw (System Control privilege) on the existing dual-auth request path with the usual 2N error parsing; a missing privilege (codes 7-10) and other device errors raise a translated HomeAssistantError and leave no in_progress state [unit]
<!-- AC:END -->
