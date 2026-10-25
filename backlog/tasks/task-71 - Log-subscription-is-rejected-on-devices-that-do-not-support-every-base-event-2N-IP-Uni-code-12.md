---
id: TASK-71
title: >-
  Log subscription is rejected on devices that do not support every base event
  (2N IP Uni, code 12)
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-24T08:27:00Z'
updated_date: '2026-10-25 15:36'
labels:
  - coordinator
  - log-channel
  - github-issue
  - compatibility
milestone: m-2
dependencies: []
references:
  - 'https://github.com/mastalir1980/ha-2N-intercom/issues/105'
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
- [x] #1 With known log caps, _build_log_event_list() returns only events listed in /api/log/caps, base events included; with the IP Uni caps from issue #105 the list has no InputChanged and keeps CallStateChanged and CallSessionStateChanged [unit]
- [x] #2 With log caps None (unknown) or empty, the subscribed list is exactly the same as in 1.5.0 (BASE_LOG_EVENTS plus MotionDetected when motion detection is available) [unit]
- [x] #3 MotionDetected is subscribed only when motion detection is available and, with known caps, /api/log/caps lists it [unit]
- [x] #4 When known caps lack CallStateChanged or CallSessionStateChanged the integration logs one WARNING that ring detection is not available on this device, and the subscription still starts with the supported events [unit]
- [x] #5 A CapabilitiesChanged/ConfigurationChanged cache refresh that changes the caps still triggers a resubscribe with the new filtered list (existing behaviour kept) [unit]
- [x] #6 E2E: diagnostics subscribed_events is non-empty and every entry is in the device /api/log/caps read by e2elib/twon.py (HA says X <-> 2N API says X) [e2e]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Filter BASE_LOG_EVENTS and available MotionDetected against non-empty log caps before adding the existing optional access/DirectoryChanged events; preserve the legacy list for None/empty caps.
2. Warn once per coordinator lifetime when known caps lack either required call event; leave event-driven ring detection, listener backoff, API caps contract and tuple-based resubscribe trigger unchanged.
3. Add unit coverage in tests/test_coordinator_access.py for the issue #105 IP Uni caps, unknown/empty caps, motion combinations, missing-call-event warnings and live cache-refresh resubscription.
4. Extend e2e/tests/test_50_access_control.py to require non-empty diagnostics subscribed_events and compare every event against twon.log_caps(), without relays or calls.
5. Update docs/API_REFERENCE.md for code 12 unsupported-filter rejection; run all required local Python gates, record implementation notes, and commit locally without pushing or finalizing acceptance criteria.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Before the v1.5.1 release, Jan asks the reporter of issue #105 to test main on the IP Uni (he offered to). His result is recorded here; it does not block the release.

Implemented capability filtering for all base/motion subscription events while preserving the existing optional access/directory selection and None/empty-caps fallback. Added a coordinator-lifetime warning flag for missing call events; listener backoff, event-driven ring handling, API caps contract and tuple-based resubscribe trigger remain unchanged.

AC #1: tests/test_coordinator_access.py::LogCapsSubscriptionTests.test_ip_uni_caps_filter_unsupported_base_events checks the exact issue #105 capabilities, removes InputChanged, retains both call events and starts a supported subscription. The supported-access test now also asserts the filtered base-event list.
AC #2: test_no_access_events_without_log_caps covers None/empty caps with and without active motion, preserving the exact legacy subscription list and emitting no warning.
AC #3: test_motion_requires_system_and_log_capabilities_when_known covers all four system-motion/log-motion combinations; unknown/empty caps retain legacy motion behaviour.
AC #4: test_missing_call_events_warn_once_and_still_subscribe covers either/both missing call events, exactly one WARNING across repeated list builds and capability recovery/regression, and successful supported subscriptions.
AC #5: test_caps_events_resubscribe_with_changed_base_event_filter runs the listener for both CapabilitiesChanged and ConfigurationChanged with InputChanged removed and restored; verifies both successive subscription lists. Existing unchanged-caps and access-event resubscribe tests remain green.
AC #6: extended e2e/tests/test_50_access_control.py::test_subscribed_access_events_match_device_log_caps to require non-empty diagnostics subscribed_events and compare every event with independently fetched twon.log_caps(). No relays or calls; execution is pending the e2e-pi PR check.

Updated docs/API_REFERENCE.md to explain whole-filter rejection with code 12 and non-empty-caps filtering. Local Python 3.12 gates passed: targeted coordinator suite (212 tests), full unittest discovery (748 tests), python3 validate.py, and compilation of all integration modules. No E2E/network commands were run on the VM. Task remains In Progress with all acceptance criteria unchecked for orchestrator review/finalization.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented by the headless coder. Checks green on 698f904fe after 0 fix round(s): e2e-pi=pass, validate=pass, validate=pass. PR: https://github.com/mastalir1980/ha-2N-intercom/pull/108. Done takes effect when the PR is merged.
AC #1: coordinator._build_log_event_list now filters base and motion events by non-empty log caps before appending optional events. test_ip_uni_caps_filter_unsupported_base_events uses the exact issue #105 caps. It asserts the subscription is a subset of the caps, has no InputChanged, keeps CallStateChanged and CallSessionStateChanged, and equals the exact expected list. test_access_events_filtered_by_caps and test_all_access_events_when_device_supports_them were adapted to caps that now include base events. That is a legitimate consequence of the new behaviour, not a weakening. (proven)
AC #2: test_no_access_events_without_log_caps was extended with caps None, [], RuntimeError and 'garbage', each with and without motion available. It asserts the exact legacy list (BASE_EVENTS plus MotionDetected when available) and that no WARNING is logged (assertNoLogs). The code branch is `if self._log_caps:`, so None and an empty frozenset keep the 1.5.0 list. (proven)
AC #3: test_motion_requires_system_and_log_capabilities_when_known covers the four combinations of system motion available and MotionDetected listed in log caps. It asserts the exact list and the subscription: MotionDetected is subscribed only when both hold. Unknown caps keep the legacy motion behaviour (criterion 2 test). (proven)
AC #4: test_missing_call_events_warn_once_and_still_subscribe covers CallStateChanged missing, CallSessionStateChanged missing, and both missing. It asserts exactly one WARNING record with the expected message across repeated list builds and caps changes, and that the subscription still starts with the supported events. The code uses the _ring_detection_unavailable_warned flag, once per coordinator lifetime, with no device identifiers in the message. (proven)
AC #5: New test_caps_events_resubscribe_with_changed_base_event_filter drives the real listener loop for both CapabilitiesChanged and ConfigurationChanged, with InputChanged removed and restored. It asserts api.subscriptions == [initial, updated] and that subscribed_log_events matches. The tuple-comparison resubscribe trigger is unchanged in the diff. (proven)
AC #6: test_subscribed_access_events_match_device_log_caps in e2e/tests/test_50_access_control.py now asserts that diagnostics subscribed_events is non-empty and that every entry is in set(twon.log_caps()), read through the independent e2elib client. The orchestrator reports the e2e-pi check green on this head. The test is skipped only if access_control diagnostics are absent (see minor finding). (proven)
<!-- SECTION:FINAL_SUMMARY:END -->
