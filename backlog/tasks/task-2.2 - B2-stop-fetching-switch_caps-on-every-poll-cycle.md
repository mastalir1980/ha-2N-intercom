---
id: TASK-2.2
title: 'B2: stop fetching switch_caps on every poll cycle'
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-24T08:28:00Z'
updated_date: '2026-10-25 15:59'
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
- [x] #1 A normal poll cycle does not call async_get_switch_caps when switch_caps is already cached [unit]
- [x] #2 ConfigurationChanged and CapabilitiesChanged still refresh switch_caps and add/remove relay entities as today [unit]
- [x] #3 After a log (re)subscription the switch_caps cache is refreshed once, so changes missed while the subscription was down are picked up [unit]
- [x] #4 A safety-net refresh of switch_caps runs at most every 10 minutes regardless of scan_interval [unit]
- [x] #5 E2E: relay switch/cover entities still match /api/switch/caps of the device (HA says X <-> 2N API says X), no relay switching [e2e]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add SWITCH_CAPS_SAFETY_INTERVAL = 600 seconds and a tz-aware last-success timestamp in coordinator.py; normal polls reuse switch_caps until the cache is absent or the safety interval expires. Record successful switch_caps fetches centrally in _refresh_secondary_cache.
2. Refresh switch_caps once after every successful log subscription before requesting the existing baseline refresh; keep ConfigurationChanged/CapabilitiesChanged and IO/state handling unchanged.
3. Add counting-fake unit coverage for cached polls, timed refreshes and failures, event refreshes and subscription/reconnection; retain relay add/remove behavior. Add or extend the read-only E2E comparison of switch/cover entities with device switch caps.
4. Mark B2 implemented in docs/IMPROVEMENTS.md, run the required Python local gates, and record implementation evidence without checking criteria or finalizing task status. Commit locally on the existing task branch; do not push or run live E2E.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented switch_caps caching with SWITCH_CAPS_SAFETY_INTERVAL = 600 seconds and a timezone-aware timestamp updated centrally only after successful fetches. Polls reuse the cache until absent or expired; failed fetches keep the previous cache/timestamp and remain retryable, as specified by the plan.
Every successful log subscription now refreshes switch_caps before scheduling the existing baseline update. The refresh is inside unsubscribe cleanup so cancellation cannot strand a subscription. ConfigurationChanged/CapabilitiesChanged, IO caps handling, and switch/IO state polling remain unchanged.
Added counting-fake coordinator coverage and real coordinator-to-switch-platform event coverage for dynamic relay addition/removal. Extended the read-only E2E caps comparison to distinguish switch and gate-cover entities using relay overrides. Updated README.md, docs/ARCHITECTURE.md and docs/IMPROVEMENTS.md B2. Live E2E is not run on this VM; e2e-pi must provide the device-level evidence. Acceptance criteria remain unchecked and status remains In Progress for orchestrator review.

Local validation passed on Python 3.12: python3 -m unittest discover -s tests -t tests (758 tests), python3 validate.py, and python3 -m py_compile custom_components/2n_intercom/*.py e2e/tests/test_10_entities.py.
AC #1: test_cached_normal_polls_keep_caps_and_poll_states proves startup fetch is reused by normal polls while switch_status/io_status continue polling; empty caps are cached by test_uncached_poll_fetches_caps_and_caches_empty_result.
AC #2: test_config_and_capability_events_refresh_and_reset_safety_net dispatches both events and proves refresh/listener notification; test_config_and_capability_events_add_and_remove_relay_entities wires the real coordinator to the switch platform and proves entity addition/removal for each event.
AC #3: test_each_subscription_refreshes_caps_once_before_baseline proves startup plus exactly one fetch per initial subscription/reconnection, changed caps visible to baseline updates, and no duplicate baseline fetch. Additional cases prove failed subscriptions do not fetch and cancellation cleans up the subscription.
AC #4: test_safety_net_uses_elapsed_time_not_scan_interval proves no refresh at 599 seconds and refresh at 600/1200 seconds for scan intervals 2, 60 and 600; event refresh resets the timer. Failure tests prove cache retention and retry without advancing the successful-fetch timestamp.
AC #5: e2e/tests/test_10_entities.py::test_relay_switch_and_cover_entities_match_device_caps compares enabled device relay caps with HA switch/cover registry entities, respecting gate overrides and never switching a relay. Compiled locally; execution and device-level evidence remain pending e2e-pi. No criteria checked and no terminal status set.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented by the headless coder. Checks green on 4004d3260 after 0 fix round(s): e2e-pi=pass, validate=pass, validate=pass. PR: https://github.com/mastalir1980/ha-2N-intercom/pull/110. Done takes effect when the PR is merged.
AC #1: tests/test_coordinator.py SwitchCapsRefreshTests.test_cached_normal_polls_keep_caps_and_poll_states: after initialization, 3 polls leave async_get_switch_caps at 1 call while switch_status/io_status are polled 3 times; the new guard in _async_update_data skips the fetch when cache and timestamp are present. Full unit suite (758 tests) passes. (proven)
AC #2: Event path (_async_refresh_caps_from_event) is unchanged. test_config_and_capability_events_refresh_and_reset_safety_net covers both events refreshing switch caps and notifying listeners. tests/test_switch.py test_config_and_capability_events_add_and_remove_relay_entities checks that entities are added and removed for both events. (proven)
AC #3: test_each_subscription_refreshes_caps_once_before_baseline runs two subscriptions (the first drops). Caps are fetched once per subscription (3 calls including startup), and the baseline poll after the second subscription sees the changed caps. test_failed_subscription_does_not_refresh_caps and the cancellation test cover the edge cases. The refresh sits in the listener loop right after the subscription is established, before the baseline request. (proven)
AC #4: test_safety_net_uses_elapsed_time_not_scan_interval, with scan_interval 2/60/600 and a patched dt_util.utcnow: no refetch at 599 s and a refetch at 600 s, then none at 1199 s and one at 1200 s. SWITCH_CAPS_SAFETY_INTERVAL == 600 is asserted. Failed-refresh retry behaviour is covered by test_failed_refresh_retains_caps_and_last_success_for_retry. Time is tz-aware via dt_util. (proven)
AC #5: e2e/tests/test_10_entities.py test_relay_switch_and_cover_entities_match_device_caps compares the HA switch and cover entities with the enabled relays from /api/switch/caps (read-only, no relay switching). The e2e-pi check passed on this head, per the orchestrator. (proven)
<!-- SECTION:FINAL_SUMMARY:END -->
