---
id: TASK-76
title: >-
  Reload the entry once per config change and build DeviceInfo in one
  constructor call
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-31T10:28:00Z'
updated_date: '2026-10-31T10:29:00Z'
labels:
  - ha-compat
  - config-flow
  - tech-debt
milestone: m-1
dependencies: []
references:
  - custom_components/2n_intercom/__init__.py
  - custom_components/2n_intercom/config_flow.py
  - custom_components/2n_intercom/coordinator.py
  - tests/test_config_flow.py
  - tests/test_init.py
  - tests/test_coordinator.py
  - >-
    https://contributors.home-assistant.io/blog/2026/05/07/config-entry-listener-together-with-reloading-methods/
  - https://contributors.home-assistant.io/blog/2026/10/13/device-info-class/
  - https://github.com/home-assistant/core/pull/169198
priority: medium
type: enhancement
ordinal: 82000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Two small Home Assistant compatibility fixes found in the HA developer blog. No user-visible change apart from one reload instead of two after reauth, reconfigure or an SSDP host change.

**1. Double reload (fact from code; user-visible effect not observed).**
`__init__.py:586` registers an update listener (`async_update_options`, `:590-594`) that reloads the entry on every entry update. The reauth flow (`config_flow.py:641-647`), the reconfigure flow (`:734-746`) and the SSDP host change (`:492-497`) call `async_update_entry(...)` and then reload again themselves. In HA core, `async_update_entry` schedules every update listener when the entry changed (`homeassistant/config_entries.py`, `_async_save_and_notify`, read on `dev` 2026-10-27), so each of these flows requests two reloads. HA says this "can cause the integration to reload twice and/or create a race condition" and deprecates the combination from 2026.6 (https://contributors.home-assistant.io/blog/2026/05/07/config-entry-listener-together-with-reloading-methods/, checked 2026-10-26).
The 2026.12 error (core PR https://github.com/home-assistant/core/pull/169198, read 2026-10-27) is raised only inside `async_update_reload_and_abort` and `_abort_if_unique_id_configured(updates=...)`, which we do not call today, so there is no deadline. The fix below starts using `async_update_reload_and_abort`, so the update listener must be removed in the same change. `OptionsFlowWithReload` raises `ValueError` while any update listener is registered.

**2. DeviceInfo dict-style writes.**
`coordinator.py:1724-1754` (`get_device_info`) creates `DeviceInfo(...)` and then writes `configuration_url`, `serial_number`, `hw_version` and `connections` with `info["..."] = ...`. From HA 2026.11 `DeviceInfo` is a dataclass; `[]` writes still work through a compatibility layer that "will be deprecated and removed in a later version"; unset fields read as `UNDEFINED`, not `None` (https://contributors.home-assistant.io/blog/2026/10/13/device-info-class/, checked 2026-10-27).

**Current behaviour.** Reauth / reconfigure / SSDP host change: entry updated, then two reloads are requested (update listener + explicit `async_reload`). `get_device_info` mutates the `DeviceInfo` after construction.

**Expected behaviour.** Every config change requests exactly one reload through the HA-provided mechanism. `DeviceInfo` is built with all fields in one constructor call and works with both the TypedDict (HA 2026.4-2026.10) and the dataclass (HA 2026.11+) form.

Minimum HA is 2026.4.0 (`hacs.json`). `OptionsFlowWithReload`, `async_update_reload_and_abort` and `async_schedule_reload` exist in HA 2026.4.0 (`homeassistant/config_entries.py` at tag 2026.4.0, checked 2026-10-27).

Reauth/reconfigure cannot be exercised by E2E (it does not change real credentials), so the reload behaviour of those flows is unit-tested and confirmed by Jan on staging.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The entry registers no update listener: `add_update_listener` and `async_update_options` are removed from `__init__.py`; a unit test asserts setup registers no update listener [unit]
- [ ] #2 `TwoNIntercomOptionsFlow` extends `config_entries.OptionsFlowWithReload`; a unit test asserts the base class [unit]
- [ ] #3 Successful reauth ends with `async_update_reload_and_abort(entry, data=merged)` and reason `reauth_successful`, with no separate `async_update_entry` or `async_reload` call; a unit test asserts exactly one reload request and the updated data [unit]
- [ ] #4 Successful reconfigure ends with `async_update_reload_and_abort` keeping today's data and `allow_insecure` option handling, reason `reconfigure_successful`; unit tests assert exactly one reload and that data and options equal today's values (adapt `test_reconfigure_with_valid_credentials_updates_and_aborts` and `test_reconfigure_stores_and_forwards_insecure_opt_in`) [unit]
- [ ] #5 An SSDP host change updates the entry and requests exactly one reload via `hass.config_entries.async_schedule_reload`; identity verification and logging are unchanged; a unit test asserts one reload [unit]
- [ ] #6 Reauth on an entry that is not loaded (setup failed with an auth error) still updates the entry and reloads it once; unit test with a not-loaded entry [unit]
- [ ] #7 `get_device_info` passes all fields (identifiers, name, manufacturer, model, sw_version and, when present, configuration_url, serial_number, hw_version, connections) to one `DeviceInfo(...)` call; no `info[...] =` writes on DeviceInfo remain in `custom_components/` (checked in the PR diff); existing `DeviceInfoTests` stay green [unit]
- [ ] #8 Existing E2E tests stay green on the E2E intercom: `test_00_setup` (device sw_version and serial match the device), `test_20_lifecycle::test_reload_entry`, the `test_40` options-flow tests and the `test_firmware` configuration_url check [e2e]
- [ ] #9 After the merge, the staging HA system log shows no `has an update listener` or `OptionsFlowWithReload` message for `2n_intercom` after an HA restart [tester]
- [ ] #10 On staging, Jan changes one option (e.g. scan interval) and runs one reconfigure with unchanged values: each time the entry returns to loaded, entities come back and the HA log shows one reload per action [jan]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. `__init__.py`: delete `entry.async_on_unload(entry.add_update_listener(async_update_options))` (`:586`) and `async_update_options` (`:590-594`); replace `tests/test_init.py::test_async_update_options_reloads_entry` with a test that setup registers no update listener. Keep the MAC backfill `async_update_entry` at `:548` (runs during setup, no reload wanted).
2. `config_flow.py`:
   - `class TwoNIntercomOptionsFlow(config_entries.OptionsFlowWithReload)`; `_async_create_entry` unchanged.
   - reauth (`:640-647`): `return self.async_update_reload_and_abort(self._reauth_entry, data=merged, reason="reauth_successful")`.
   - reconfigure (`:733-746`): `return self.async_update_reload_and_abort(self._reconfigure_entry, data=merged, options={**self._reconfigure_entry.options, CONF_ALLOW_INSECURE: allow_insecure}, reason="reconfigure_successful")`.
   - SSDP (`:492-497`): keep `async_update_entry`, replace `self.hass.async_create_task(self.hass.config_entries.async_reload(...))` with `self.hass.config_entries.async_schedule_reload(entry.entry_id)`.
   - Pass `reason=` explicitly so the integration's own strings (`strings.json:76-77`) keep being used; no translation change.
3. `coordinator.py` `get_device_info`: collect the optional fields (configuration_url, serial_number, hw_version, connections) in a local `kwargs` dict only when present, then `return _DeviceInfo(identifiers=..., name=..., manufacturer="2N", model=..., sw_version=..., **kwargs)`. Do not read DeviceInfo fields with `.get()`.
4. Unit-test stubs (`tests/test_config_flow.py` `_BaseFlow` / `FakeConfigEntries`, `tests/test_coordinator.py` DeviceInfo stub, `tests/test_init.py` fakes): add `OptionsFlowWithReload`, `async_update_reload_and_abort` (updates the entry and records one reload, also for a not-loaded entry) and `async_schedule_reload` as needed. Do not import real HA in unit tests.
5. Docs: update `docs/ARCHITECTURE.md` only if it describes the update listener / reload path. No README or CHANGELOG change (release task only).

Must not change: config split (`entry.data` = identity, `entry.options` = behaviour; reauth must not merge options, see `test_reauth_does_not_merge_options`); the `allow_insecure` handling in reconfigure/reauth; SSDP identity verification (TASK-68); dual auth in `api.py`; entity unique_ids and device identifiers.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Approved by Jan in Telegram, 2026-10-27 (grooming 2026-10-27, alternative B; milestone v1.6.0 confirmed by Jan). Spec by Steve.
<!-- SECTION:NOTES:END -->
