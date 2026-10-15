---
id: TASK-4
title: Subscribe to access-control events from the 2N log channel
status: Done
assignee:
  - '@copilot'
created_date: '2026-08-30 09:27'
updated_date: '2026-10-15 12:12'
labels:
  - access-control
  - coordinator
milestone: m-0
dependencies:
  - TASK-1
references:
  - docs/ROADMAP-NAVRH.md
priority: high
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The intercom is also an access-control unit, but the integration only subscribes to call/switch/IO/registration/config events plus MotionDetected, so card, PIN, mobile-key and fingerprint access is invisible to Home Assistant. Extend the /api/log/subscribe event list in coordinator.py with access-control events. Event names verified against the 2N HTTP API docs (5.10.1 api log caps, 2026-10-11): CardEntered, CodeEntered, MobKeyEntered, FingerEntered (note: NOT 'FingerEnteredData', which does not exist), UserAuthenticated, UserRejected, AccessTaken, AccessBlocked, AccessLimited, ApiAccessRequested (emitted by /api/accesspoint/grantaccess, see TASK-8). Which events a device supports depends on model, hardware (card reader, keypad, Bluetooth, fingerprint module) and licence: query /api/log/caps and subscribe only to the intersection, instead of probing; an unsupported or malformed event must never break the subscription (same degradation pattern as MotionDetected). Store the latest access event (type, user uuid, resolved user name, credential type, access point / direction, granted or denied, timestamp) in coordinator data for TASK-5 (event entities) and TASK-6 (bus events). Resolve the user uuid to a display name via the existing /api/dir/query client method, with caching. Event payload field names must be taken from the 2N docs or a real device, not guessed. Ground-truth device: IP Force 2.0 fw 3.3.x (see CLAUDE.md); E2E there is currently blocked by TASK-12.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Coordinator reads /api/log/caps and subscribes only to the supported subset of: CardEntered, CodeEntered, MobKeyEntered, FingerEntered, UserAuthenticated, UserRejected, AccessTaken, AccessBlocked, AccessLimited, ApiAccessRequested
- [x] #2 Subscription keeps working when log/caps lacks some of these events or when an unknown/malformed access event arrives (graceful degradation, covered by unit tests)
- [x] #3 Latest access event with parsed attributes (type, user uuid, user name resolved via dir/query with caching, credential type, access point/direction, granted/denied, tz-aware timestamp) is available in coordinator data
- [x] #4 Unit tests cover log/caps intersection, payload parsing for each event type and dir/query name resolution incl. cache and unknown uuid
- [x] #5 E2E test in e2e/tests/ verifies the subscribed event list matches what the device reports in /api/log/caps
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. api: async_get_log_caps() (GET /api/log/caps -> result.events).
2. coordinator: fetch log caps before each (re)subscribe; subscribe base events + (ACCESS_LOG_EVENTS + DirectoryChanged) ∩ caps; no caps -> no access events. CapabilitiesChanged/ConfigurationChanged re-reads caps and requests a resubscribe when the subset changed.
3. coordinator: _process_access_event parses documented params into a frozen AccessEvent (type, credential, ap, direction, granted, reason, uuid, name, session, tz-aware utcTime). Never store code/uid/authid. Malformed -> False.
4. Name resolution: event name param -> cached dir/query map (lowercase uuid) -> throttled async refresh on unknown uuid; DirectoryChanged clears cache.
5. TwoNIntercomData.last_access_event + diagnostics (log caps, subscribed events).
6. Unit tests + E2E test comparing diagnostics subscribed list with device log/caps.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Validation: python3 -m unittest discover -s tests -t tests (530 OK), python3 validate.py OK, py_compile OK. E2E 'bash e2e/e2e.sh wip' on staging (2N IP Force fw 3.3.1.82.4, HA 2026.10.1): 13 passed, 3 skipped, 1 failed — the failure is the pre-existing, unrelated TASK-18 options-flow test. test_50_access_control.py::test_subscribed_access_events_match_device_log_caps passed. Event param names verified against 2N wiki api/log/caps event table (AccessBlocked 'ap,state', AccessLimited 'ap,type,state', AccessTaken 'ap,session', ApiAccessRequested 'ap,valid' + 'session,uuid').
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Coordinator now reads /api/log/caps and subscribes to the supported subset of 10 access-control events plus DirectoryChanged (resubscribes on caps change, degrades gracefully on unsupported/malformed events). Parsed latest AccessEvent (type, credential, access point/direction, granted/denied, reason, user uuid + name via cached dir/query with throttled refresh, tz-aware timestamp) is in coordinator data and diagnostics (identity redacted). Verified by tests/test_coordinator_access.py, test_api, test_diagnostics and the E2E log/caps test.
<!-- SECTION:FINAL_SUMMARY:END -->
