---
id: TASK-71
title: >-
  Log subscription is rejected on devices that do not support every base event
  (2N IP Uni, code 12)
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-24T08:27:00Z'
updated_date: '2026-10-24T08:27:00Z'
labels:
  - coordinator
  - log-channel
  - github-issue
  - compatibility
milestone: m-2
dependencies: []
references:
  - https://github.com/mastalir1980/ha-2N-intercom/issues/105
  - custom_components/2n_intercom/coordinator.py
  - custom_components/2n_intercom/api.py
  - tests/test_coordinator.py
  - docs/API_REFERENCE.md
priority: high
type: bug
ordinal: 76000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: GitHub issue #105. On a 2N IP Uni (fw 2.50, integration 1.4.0, HA 2026.10.2, HTTPS) ring detection never works: /api/log/subscribe is rejected with code=12 "invalid parameter value" param=filter. The device rejects the whole subscription when any event in the filter is unknown. Its /api/log/caps lacks InputChanged (the Uni has no inputs). Same code in 1.5.0.

Current behaviour (fact, main @ 5938983): BASE_LOG_EVENTS (coordinator.py:119-129: CallStateChanged, CallSessionStateChanged, SwitchStateChanged, InputChanged, OutputChanged, RegistrationStateChanged, ConfigurationChanged, CapabilitiesChanged, DeviceState) is always subscribed. _build_log_event_list() (coordinator.py:563-578) checks /api/log/caps only for the optional access-control events and DirectoryChanged. The listener loop (coordinator.py:1028-1048) retries the same rejected filter with backoff forever, so the device never delivers ring events.

Expected behaviour: when /api/log/caps is known, every subscribed event (base and optional) is one the device lists. When caps are unknown (None: older firmware or request rejected), keep today's list so existing devices do not change. The IP Uni log caps from the issue: KeyPressed, KeyReleased, OutputChanged, SwitchStateChanged, SwitchOperationChanged, SwitchesBlocked, ApiAccessRequested, DtmfEntered, CallSessionStateChanged, CallStateChanged, RegistrationStateChanged, DeviceState, LoginBlocked, HardwareChanged, DirectoryChanged, DirectorySaved, CapabilitiesChanged, ConfigurationChanged.

Out of scope (tracked for v1.6.0): camera entities on devices without a camera, and surfacing code 10 (missing privilege) on switch/* and system/caps. The reporter offered to test a fix on the device.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 With known log caps, _build_log_event_list() returns only events listed in /api/log/caps, base events included; with the IP Uni caps from issue #105 the list has no InputChanged and keeps CallStateChanged and CallSessionStateChanged [unit]
- [ ] #2 With log caps None (unknown) or empty, the subscribed list is exactly the same as in 1.5.0 (BASE_LOG_EVENTS plus MotionDetected when motion detection is available) [unit]
- [ ] #3 MotionDetected is subscribed only when motion detection is available and, with known caps, /api/log/caps lists it [unit]
- [ ] #4 When known caps lack CallStateChanged or CallSessionStateChanged the integration logs one WARNING that ring detection is not available on this device, and the subscription still starts with the supported events [unit]
- [ ] #5 A CapabilitiesChanged/ConfigurationChanged cache refresh that changes the caps still triggers a resubscribe with the new filtered list (existing behaviour kept) [unit]
- [ ] #6 E2E: diagnostics subscribed_events is non-empty and every entry is in the device /api/log/caps read by e2elib/twon.py (HA says X <-> 2N API says X) [e2e]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. coordinator.py _build_log_event_list(): start from BASE_LOG_EVENTS (+ MotionDetected when motion_detection_available). If self._log_caps is a non-empty frozenset, keep only events in it, then add the optional access/DirectoryChanged events exactly as today. If caps are None or empty, return the 1.5.0 list unchanged.
2. If known caps lack CallStateChanged or CallSessionStateChanged, log one WARNING per coordinator lifetime (flag on the coordinator, no device identifiers in the message).
3. Keep the resubscribe trigger in the cache refresh path (coordinator.py:531-536) as is; it compares tuples, so a filtered list works without changes.
4. Unit tests in tests/test_coordinator.py (or tests/test_coordinator_access.py where the log-caps fixtures live): IP Uni caps from issue #105, caps None, empty caps, MotionDetected with/without caps, missing call events warning, resubscribe on caps change.
5. E2E: extend an existing test (e2e/tests/test_00_setup.py or test_50_access_control.py) to read diagnostics subscribed_events and compare it with twon.log_caps(); no relays, no calls.
6. docs/API_REFERENCE.md: one line in the log channel / firmware quirks section: the device rejects the whole filter (code 12) when any event is unsupported, so every event is checked against /api/log/caps.
Must not change: event-driven ring detection, graceful degradation pattern for unsupported events, the listener backoff, api.py async_get_log_caps() contract (None = unknown).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Before the v1.5.1 release, Jan asks the reporter of issue #105 to test main on the IP Uni (he offered to). His result is recorded here; it does not block the release.
<!-- SECTION:NOTES:END -->
