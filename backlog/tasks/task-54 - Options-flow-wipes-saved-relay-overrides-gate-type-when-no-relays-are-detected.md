---
id: TASK-54
title: >-
  Options flow wipes saved relay overrides (gate type) when no relays are
  detected
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-18 10:19'
labels:
  - config-flow
  - relay
  - homekit
milestone: m-0
dependencies: []
references:
  - custom_components/2n_intercom/config_flow.py
  - custom_components/2n_intercom/cover.py
  - custom_components/2n_intercom/switch.py
  - tests/test_config_flow.py
priority: high
type: bug
ordinal: 61000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: a gate relay configured as `gate` (cover entity, exposed to HomeKit as a gate) silently turned back into a plain switch on a real install after an upgrade; the cover entity stayed `unavailable` and disappeared from Apple Home. The relay overrides (name, door/gate type, pulse) live only in `entry.options["relays"]`.

Current behaviour (code, `custom_components/2n_intercom/config_flow.py`): `_async_after_camera_step` (around line 1144) does `self._data[CONF_RELAYS] = []` when `self._detected_relays` is empty, and `_async_create_entry` (around line 1234) then saves `self._data` as the whole options dict. `_detected_relays` comes from `coordinator.switch_caps` (`_refresh_detected_relays`, around line 789) and is empty whenever the entry is not loaded or the caps fetch failed or returned nothing at that moment. So one pass through Configure in that state erases every saved relay override. `cover.py` only creates covers from `entry.options["relays"]` with type gate, so the gate is lost. The same happens to an override for a relay that is temporarily not in caps when the user walks the relay steps (only detected relays are written back).

Expected behaviour: the options flow never drops saved relay overrides it did not show to the user. With no detected relays it keeps the saved `relays` list unchanged; with detected relays it updates the shown ones and keeps saved overrides for relay numbers that were not shown.

Approach / pointers: `_async_after_camera_step` and the final branch of `async_step_relay` in `config_flow.py`; merge with `self._current_option(CONF_RELAYS, [])` keyed by `relay_number`. Must not change: relay step fields and their defaults, `entry.data`/`entry.options` split, other options keys. Tests in `tests/test_config_flow.py`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Options flow with zero detected relays (entry not loaded or empty switch caps) saves options whose `relays` equals the previously saved list, incl. a gate override; unit test
- [ ] #2 Options flow with detected relays updates only the relays shown in the relay steps and keeps saved overrides for relay numbers that were not shown; unit test
- [ ] #3 A relay saved as gate stays a cover entity (not a switch) after an options flow pass with empty caps followed by a reload; unit test on setup of cover + switch platforms
- [ ] #4 Unit suite + validate.py green on Python 3.12+; `bash e2e/e2e.sh wip` (or PR check e2e-pi) green
<!-- AC:END -->
