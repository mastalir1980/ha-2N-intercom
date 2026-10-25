---
id: TASK-2.2
title: 'B2: stop fetching switch_caps on every poll cycle'
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-24T08:28:00Z'
updated_date: '2026-10-24T08:29:00Z'
labels:
  - tech-debt
  - coordinator
milestone: m-1
dependencies: []
references:
  - docs/IMPROVEMENTS.md
  - custom_components/2n_intercom/coordinator.py
  - tests/test_coordinator.py
parent_task_id: TASK-2
priority: medium
type: enhancement
ordinal: 79000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: docs/IMPROVEMENTS.md B2. switch_caps is static device configuration, but the poll cycle refetches it every time "as a safety net" (coordinator.py:1316-1324), while io_caps is loaded once. With the minimum scan interval (2 s) that is one extra request per poll to the device; with the default 60 s it is still noise in the device log and an extra failure point.

Current behaviour (fact): switch_caps is loaded at startup (coordinator.py:1201-1205), refreshed on ConfigurationChanged/CapabilitiesChanged (coordinator.py:525-536) and again unconditionally in _async_update_data (coordinator.py:1316-1324).

Expected behaviour: no switch_caps request in a normal poll; caps still follow device changes through the events, after every log (re)subscription, and through a low-frequency safety net.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A normal poll cycle does not call async_get_switch_caps when switch_caps is already cached [unit]
- [ ] #2 ConfigurationChanged and CapabilitiesChanged still refresh switch_caps and add/remove relay entities as today [unit]
- [ ] #3 After a log (re)subscription the switch_caps cache is refreshed once, so changes missed while the subscription was down are picked up [unit]
- [ ] #4 A safety-net refresh of switch_caps runs at most every 10 minutes regardless of scan_interval [unit]
- [ ] #5 E2E: relay switch/cover entities still match /api/switch/caps of the device (HA says X <-> 2N API says X), no relay switching [e2e]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. coordinator.py _async_update_data: call the switch_caps refresh only when the cache is None or the safety-net interval (new const SWITCH_CAPS_SAFETY_INTERVAL = 600 s, tz-aware via homeassistant.util.dt) has elapsed since the last successful fetch; record the fetch time in _refresh_secondary_cache or next to it.
2. Log listener: after a subscription is established (coordinator.py ~1050, where the baseline refresh is forced) refresh switch_caps once.
3. Keep the event-driven refresh path (coordinator.py:525-536) unchanged.
4. Update the comment at coordinator.py:1316 and docs/IMPROVEMENTS.md B2 ("implemented").
5. Unit tests in tests/test_coordinator.py with a fake API counting async_get_switch_caps calls.
Must not change: io_caps handling, relay entity add/remove logic, polling as safety net for states (switch_status, io_status).
<!-- SECTION:PLAN:END -->
