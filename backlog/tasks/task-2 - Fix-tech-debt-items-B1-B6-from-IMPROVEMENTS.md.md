---
id: TASK-2
title: Fix tech-debt items B1-B6 from IMPROVEMENTS.md
status: To Do
assignee: []
created_date: 2026-08-30 09:27
updated_date: '2026-10-24T08:29:00Z'
labels:
  - tech-debt
dependencies:
  - TASK-1
references:
  - docs/IMPROVEMENTS.md
priority: high
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement the six robustness proposals from docs/IMPROVEMENTS.md: B1 tz-aware timestamps (replace naive datetime.now() with homeassistant.util.dt utcnow/now in coordinator.py and api.py; attributes exported via isoformat must carry an offset); B2 stop refetching switch_caps on every poll cycle (rely on ConfigurationChanged/CapabilitiesChanged events plus one-time load, mirror the io_caps pattern); B3 reuse a shared aiohttp session in _async_request_without_auth instead of creating a new ClientSession per call; B4 document/expose the difference between selected_mode=mjpeg and the actual snapshot-stream fallback in camera attributes; B5 declare minimum supported HA version (aiohttp.DigestAuthMiddleware dependency) in hacs.json/README; B6 narrow overly broad except Exception blocks where a specific exception type is known.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 B1: no naive datetime.now() remains in custom_components/2n_intercom; timestamp attributes are tz-aware
- [ ] #2 B2: switch_caps is not fetched on every poll cycle; event-driven refresh covered by a test
- [ ] #3 B3: _async_request_without_auth no longer constructs a per-call ClientSession
- [ ] #4 B4: camera attributes/docs distinguish native MJPEG from snapshot-stream fallback
- [ ] #5 B5: hacs.json contains a minimum HA version and README documents it
- [ ] #6 B6: broad except Exception narrowed where the failing operation has a known exception type
- [ ] #7 Full test suite passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24 roadmap for v1.6.0: B1 done (TASK-2.1). B5 mostly done: hacs.json declares homeassistant 2026.4.0 (README check left). v1.6.0 takes B2 (TASK-2.2) and B3 together with security review O-3/O-5 (TASK-2.3). B4 and B6 stay for a later version; this parent closes by hand when they are done or dropped.
<!-- SECTION:NOTES:END -->
