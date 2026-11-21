---
id: TASK-82
title: >-
  Save ring and access-event pictures to the HA media browser with retention
  (opt-in)
status: Done
assignee:
  - '@copilot'
created_date: '2026-11-21T10:11:00Z'
updated_date: '2026-11-21 12:37'
labels:
  - camera
  - access-control
  - config-flow
milestone: m-1
dependencies: []
references:
  - custom_components/2n_intercom/coordinator.py
  - custom_components/2n_intercom/image.py
  - custom_components/2n_intercom/__init__.py
  - custom_components/2n_intercom/config_flow.py
  - custom_components/2n_intercom/const.py
  - custom_components/2n_intercom/strings.json
  - custom_components/2n_intercom/translations/en.json
  - custom_components/2n_intercom/translations/de.json
  - custom_components/2n_intercom/translations/cs.json
  - README.md
  - tests/_stubs.py
  - tests/test_image.py
  - tests/test_coordinator_access.py
  - tests/test_config_flow.py
  - tests/test_init.py
  - tests/test_translations.py
  - e2e/tests/test_40_options_flow.py
  - >-
    https://github.com/home-assistant/core/blob/2026.4.0/homeassistant/components/media_source/local_source.py
  - >-
    https://github.com/home-assistant/core/blob/2026.4.0/homeassistant/core_config.py
priority: medium
type: feature
ordinal: 86000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: the integration keeps only the picture of the last ring, in RAM. `coordinator.py` stores it in `_ring_snapshot` / `_ring_snapshot_time` (set by `_async_capture_ring_snapshot`) and `image.py` `TwoNIntercomLastRingImage.async_image` serves it as `image.<intercom>_last_ring`. Every ring overwrites it and a Home Assistant restart empties it. Users who were away cannot see who rang, or who used a card or the keypad, during that time. Other doorbell integrations save ring pictures to the Home Assistant media browser with a retention period. This task adds that as an opt-in option.

**Current behaviour (fact from code).**
- `_async_capture_ring_snapshot` (coordinator.py) runs once per counted ring. It is started from `_process_log_event` (call events, only for `new_ring`) and from `_process_key_pressed_event` (`ring_on_keypress`), and only when `_ring_snapshot_enabled` is true and `camera_present is not False`. It calls `api.async_get_snapshot(source=...)`, skips the 1 s live-view cache, keeps the previous image on failure and logs a warning.
- `_ring_snapshot_enabled` is the `enable_camera` option (`__init__.py` `async_setup_entry`). `_get_platforms` forwards `camera` + `image` only when the camera is enabled and `camera_present is not False`.
- Access events: `_process_access_event` parses `CardEntered`, `CodeEntered`, `MobKeyEntered`, `FingerEntered`, `ApiAccessRequested` (credential events with a `granted` flag from `valid`), plus `UserAuthenticated`, `UserRejected`, `AccessTaken`, `AccessBlocked`, `AccessLimited`. It fires `2n_intercom_event` with the types in `const.py` `ACCESS_BUS_EVENT_TYPES` (`card_entered`, `code_entered`, ...). No picture is taken for any access event.
- Nothing is written to disk. The integration has no timers apart from the log listener and the keypress ring clear.

**Expected behaviour.**
- New option **Save event pictures** (`save_event_pictures`, bool, off by default because the pictures show people) in `entry.options`. It is shown in the options flow only when the camera is enabled and the device has a camera (`camera_present is not False`), i.e. on the existing Camera step.
- When it is turned on, the user must enter **Keep pictures for (days)** (`event_picture_retention_days`, integer 1..365). There is no default. Submitting the option on without a retention value, or with a value outside 1..365, shows a form error and saves nothing.
- Pictures are JPEG files in the Home Assistant local media folder, so they appear in Media → My media without an own media source: `<media dir>/2n_intercom/<device folder>/<YYYY-MM-DD>/<HHMMSS>-<kind>.jpg` (local time). `<kind>` is `ring`, `access-granted` or `access-denied`. File and folder names never contain credentials, card numbers, PINs, user names, user UUIDs or peers. The device folder is the slugified entry title (fallback `intercom`). All path parts are sanitised: only `[a-z0-9_-]`, no `..`, no separators, and the final path must resolve inside `<media dir>/2n_intercom/`.
- Media folder: `hass.config.media_dirs["local"]`, else the only entry when exactly one is configured, else none. HA sets `local` by default (`/media` on HA OS, `<config>/media` otherwise). If none exists, or it is not writable, the options flow shows an error when the option is turned on. At runtime the integration logs one warning per setup and saves nothing. Ring and access event handling never fail because of it.
- Ring: the existing capture at ring time also saves the picture as `ring`. The in-RAM last-ring image works exactly as today.
- Access events: one picture for the credential events `CardEntered`, `CodeEntered`, `MobKeyEntered` and `FingerEntered`, named `access-granted` when `granted` is true and `access-denied` when it is false. `ApiAccessRequested` is excluded: the API caller (often Home Assistant itself) is not at the door. `UserAuthenticated`, `UserRejected`, `AccessTaken`, `AccessBlocked` and `AccessLimited` do not capture, because they follow a credential event of the same attempt and would take a second picture of the same person.
- Throttle: at most one saved picture per entry every 10 seconds, across all kinds. A ring capture counts as well, so a ring and a card swipe within 10 s save one picture, and a run of wrong PINs or card swipes saves at most 6 pictures per minute. 10 s is longer than one access attempt (credential event plus follow-up events arrive within about a second) and still keeps a new visitor who arrives later. A throttled event is not captured at all (no extra request to the device). The ring capture itself is never throttled, so the last-ring image stays as it is today; only the save is skipped.
- Retention: a cleanup removes pictures older than the retention period and then empty date folders, only inside the entry's own `2n_intercom/<device folder>/`. It runs once at setup and then every 24 hours, in the executor. The timer is cancelled on unload. No max-files cap: retention plus the throttle limit the size, and a cap would need a directory scan on every save.
- After a restart with the option on, the last-ring image shows the newest saved `ring` picture (its time comes from the file time) until the next ring. With the option off, the last-ring image is empty after a restart, as today.
- All file IO (write, cleanup, finding the newest ring picture, the writable check) runs in the executor. A failed write is logged at warning level without the path of a user or any credential, and it never breaks event handling or the in-RAM image.
- Not changed: event-driven ring detection, the `called_id` filter, snapshot resolution from `camera/caps`, dual auth in `api.py`, the `2n_intercom_event` payload and the existing entities.

**Privacy (must be in README).** The pictures show people. They are stored on the Home Assistant disk, every Home Assistant user with media access can see them, and they are part of Home Assistant backups. Renaming the integration entry starts a new device folder; the old folder is no longer cleaned and must be deleted by hand.

**HA API availability (checked in home-assistant/core at the minimum version 2026.4.0 from hacs.json).** `hass.config.media_dirs` exists, with default `{"local": ...}` (`core_config.py`). `media_source/local_source.py` builds "My media" from `hass.config.media_dirs`. `hass.config.is_allowed_path`, `helpers/event.py` `async_track_time_interval`, `hass.async_add_executor_job` and `ConfigEntry.async_on_unload` exist. `OptionsFlowWithReload` (already used) reloads the entry after an options change.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The options flow Camera step has `save_event_pictures` (bool, default off) and `event_picture_retention_days` (1..365, no default); the fields are not shown when the camera is off or the device has no camera, and turning the camera off removes both keys from the saved options; values are stored in `entry.options`, never in `entry.data` [unit]
- [x] #2 Turning the option on without a retention value, or with 0 or 366, shows the field error `retention_required` and does not save; 1 and 365 are accepted; a missing or not writable media folder shows `media_dir_unavailable` [unit]
- [x] #3 Path helpers: `resolve_media_root` prefers `local`, uses the only entry otherwise and returns None for none or several without `local`; `device_folder_name` turns titles such as `../Front Door/`, `Vchod č.1` and an empty title into names of `[a-z0-9_-]` only (fallback `intercom`); `build_picture_path` gives `2n_intercom/<folder>/<YYYY-MM-DD>/<HHMMSS>-<kind>.jpg` in local time, adds `-2` for a second picture in the same second, rejects unknown kinds and never resolves outside `2n_intercom/` [unit]
- [x] #4 With the option on, a counted ring writes one `...-ring.jpg` with the bytes of the existing ring capture, and the in-RAM last-ring image is updated exactly as before; with the option off (or no store) no file is written and the existing ring snapshot tests stay green unchanged [unit]
- [x] #5 With the option on, `CardEntered`, `CodeEntered`, `MobKeyEntered` and `FingerEntered` with valid=true write `...-access-granted.jpg` and with valid=false `...-access-denied.jpg`; `ApiAccessRequested`, `UserAuthenticated`, `UserRejected`, `AccessTaken`, `AccessBlocked` and `AccessLimited` capture nothing; an access capture never changes the last-ring image; the `2n_intercom_event` payloads in `tests/test_coordinator_access.py` stay unchanged [unit]
- [x] #6 Saved file and folder names never contain the card uid, PIN, mobile-key id, user name, user UUID or peer from the replayed events (test asserts on the written paths) [unit]
- [x] #7 Throttle: events within 10 s of the last capture start (ring or access) request no snapshot and write no file; a ring within the throttle window still updates the in-RAM last-ring image; a fake monotonic clock shows a new capture is allowed after 10 s [unit]
- [x] #8 A failing snapshot, a write that raises OSError, and a missing or not writable media folder never raise out of the event handlers: the ring still counts, the bus event still fires, the in-RAM image is unchanged, and only one warning per setup is logged for the missing folder; the warning contains no credential or user data [unit]
- [x] #9 Retention cleanup on a temporary folder deletes `.jpg` files older than the retention and then empty date folders, keeps newer files, never touches files outside the entry device folder or symlink targets, and runs in the executor; the 24 h timer is registered with `entry.async_on_unload` and is cancelled on unload [unit]
- [x] #10 After setup with the option on and saved pictures present, the last-ring image returns the newest saved ring picture with `image_last_updated` from its file time; with the option off it starts empty as today; access pictures are never used for it [unit]
- [x] #11 All file IO (write, cleanup, newest-ring lookup, writable check) goes through `hass.async_add_executor_job` (checked in the diff and by the tests); strings.json and translations en/de/cs contain the new option labels, descriptions and both errors with the same keys (`tests/test_translations.py` green); README.md has the two option rows, the event picture section and the privacy note; CHANGELOG.md and the version are not changed (checked in the PR diff) [unit]
- [x] #12 On the E2E intercom, an E2E test in `e2e/tests/test_40_options_flow.py` opens the options flow over the HA REST API, sees both new fields on the Camera step, submits `save_event_pictures` on without retention and gets the field error `retention_required` on the same step, then aborts the flow; the saved options are unchanged and no ring, call or relay is triggered [e2e]
- [x] #13 After the merge on staging the tester agent sees the new option and retention field on the Camera options step, and the HA system log shows no error from `2n_intercom` after enabling it and restarting [tester]
- [x] #14 On the real intercom, one ring plus one valid and one wrong card or keypad code: Media → My media → 2n_intercom shows a ring picture and access-granted / access-denied pictures with the expected names; after a restart the last-ring image shows the last ring picture [jan]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. New module `custom_components/2n_intercom/event_pictures.py` with no HA imports in its pure helpers, so it can be unit-tested with a temporary folder:
   - `resolve_media_root(media_dirs: dict[str, str]) -> Path | None` (prefer `local`, else the only entry, else None).
   - `device_folder_name(title: str) -> str` (lowercase, `[a-z0-9_-]` only, collapse others to `_`, strip, fallback `intercom`).
   - `build_picture_path(root, device_folder, kind, local_time) -> Path`: kind must be one of `ring`, `access-granted`, `access-denied` (ValueError otherwise). Append `-2`, `-3`, ... when the file exists. Assert that the resolved path is inside `root / "2n_intercom"`.
   - `write_picture(path, data) -> bool` (mkdir parents, write to a temp file then rename; return False on OSError, never raise).
   - `cleanup_pictures(device_dir, older_than: datetime) -> int` (delete `*.jpg` with mtime before the cut-off, then empty date folders; never follow symlinks or leave `device_dir`; OSError per file is logged at debug and skipped).
   - `newest_ring_picture(device_dir) -> tuple[bytes, datetime] | None` (newest `*-ring*.jpg` by name order of date folder + file, mtime as tz-aware UTC).
   - `is_writable(root) -> bool`.
   - Class `EventPictureStore(hass, entry, media_root, retention_days)`: `try_reserve() -> bool` (10 s throttle on `time.monotonic`: returns True and marks the slot when the last reserved capture is at least 10 s ago, else False), `async_save(kind, data)`, `async_cleanup()`, `async_load_newest_ring()`, all via `hass.async_add_executor_job`. One warning per setup when the media folder is missing or not writable (store disabled).
2. `const.py`: `CONF_SAVE_EVENT_PICTURES = "save_event_pictures"`, `DEFAULT_SAVE_EVENT_PICTURES = False`, `CONF_EVENT_PICTURE_RETENTION_DAYS = "event_picture_retention_days"`, `EVENT_PICTURE_RETENTION_MIN = 1`, `EVENT_PICTURE_RETENTION_MAX = 365`, `EVENT_PICTURE_MIN_INTERVAL = 10` (s), `EVENT_PICTURE_CLEANUP_INTERVAL = timedelta(hours=24)`, folder name `EVENT_PICTURE_FOLDER = DOMAIN`.
3. `coordinator.py`:
   - Constructor gets `picture_store: EventPictureStore | None = None` (None = feature off, so the existing tests and behaviour stay unchanged).
   - `_async_capture_ring_snapshot`: call `store.try_reserve()` before the snapshot request; after a successful capture (after `_publish_event_state()`), if the slot was reserved, save the bytes as `ring` with the store's `async_save` in a separate task, so the ring path never waits for the disk and a failed save does not touch `_ring_snapshot`.
   - `_process_access_event`: after `_fire_bus_event`, for `event_name` in CardEntered/CodeEntered/MobKeyEntered/FingerEntered with `granted` not None, if a store exists, `camera_present is not False` and `store.try_reserve()`, start `_async_capture_event_picture(kind)`. That method calls `api.async_get_snapshot(source=...)` the same way as `_async_capture_ring_snapshot` (same source from `_camera_transport_info`), never updates `_ring_snapshot`, and on error logs at debug and returns. Do not change the bus payload or the `AccessEvent`.
   - The slot is reserved when a capture starts (not when it ends), so two events in the same second never request two snapshots. The ring capture itself always runs; only its save depends on the reservation.
4. `__init__.py` `async_setup_entry`: when `save_event_pictures` is on, the camera option is on and `camera_present is not False`, create the store with `resolve_media_root(hass.config.media_dirs)` and the retention from options. If the retention is missing or invalid (hand-edited entry), log one warning and leave the store off. Pass it to the coordinator (or attach before `async_start_log_listener`). Before forwarding platforms, `await store.async_load_newest_ring()` and set `_ring_snapshot` / `_ring_snapshot_time` when `_ring_snapshot` is still None. Run `async_cleanup()` once as a background task (`entry.async_create_background_task`) and register `async_track_time_interval(hass, ..., EVENT_PICTURE_CLEANUP_INTERVAL)` with `entry.async_on_unload(...)`.
5. `config_flow.py` `TwoNIntercomOptionsFlow.async_step_camera`: add `vol.Required(CONF_SAVE_EVENT_PICTURES, default=session or False): cv.boolean` and `vol.Optional(CONF_EVENT_PICTURE_RETENTION_DAYS, description={"suggested_value": saved})` with a NumberSelector 1..365 step 1 box unit `d`. On submit: coerce to int; if saving is on and the value is missing or outside 1..365, set `errors[CONF_EVENT_PICTURE_RETENTION_DAYS] = "retention_required"` and show the form again; if saving is on and `resolve_media_root` returns None or the folder is not writable (checked with `hass.async_add_executor_job`), `errors["base"] = "media_dir_unavailable"`. When saving is off, drop the retention key. In `async_step_device`, when the camera is turned off, also pop both new keys (same loop as the camera keys).
6. Strings: `strings.json` and `translations/en.json`, `de.json`, `cs.json` together: `options.step.camera.data` + `data_description` for both keys, `options.error.retention_required`, `options.error.media_dir_unavailable`. German and Czech must be real translations. `icons.json` only if a new entity/service would need it (none planned).
7. README.md: two rows in "Options flow parameters" (Camera step), one paragraph "Event picture history" (folder layout, kinds, 10 s throttle, retention, restart behaviour of the last-ring image, media folder requirement, rename caveat) and the privacy note from the description; update the last-ring image bullet in Features. Do not touch CHANGELOG.md or the version.
8. Tests in the style of `tests/test_image.py` / `tests/test_coordinator_access.py` / `tests/test_config_flow.py` / `tests/test_translations.py` (stubs in `tests/_stubs.py`): new `tests/test_event_pictures.py` for the module, plus coordinator, init, image-restart, config-flow and translation cases (see criteria). E2E: one test in `e2e/tests/test_40_options_flow.py` next to `test_options_flow_last_step_and_forward_only_navigation`: reach the Camera step, check both fields, submit saving on without retention, assert the `retention_required` field error, abort in `finally` and assert the options are unchanged; skip (pytest.skip with a reason) when the E2E entry has the camera off or the device reports no camera. Like the existing test it never submits the saving step. Check the retention before the media folder, so the result does not depend on whether the staging media folder is writable.
9. Size: one PR. The new module holds the file logic, the other files get small hooks, and the strings/README changes are short; splitting storage, access events and options would leave intermediate PRs with an option that does nothing or files without cleanup.

Must not change: architecture rules in CLAUDE.md (event-driven ring detection, dual auth, `entry.data` vs `entry.options`, no secrets in logs, tz-aware time via `homeassistant.util.dt`, broad `except Exception` only for logged degradation).

Execution: implement the approved nine-step plan without changing its design. Build executor-only storage and coordinator/setup hooks; add Camera options validation and en/de/cs translations; document privacy and add the non-saving REST options-flow E2E check. Cover path safety, retention, restore, throttle, event payloads and failure degradation with unit tests, run the required local gates, and commit locally without changing acceptance criteria or terminal status.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Approved by the maintainer on 2026-11-21. Decisions: storage as JPEG files in the HA local media folder (no own media source); retention required when the option is on (1..365 days, no default); pictures for rings and for credential access events; 10 s throttle; no max-files cap (retention plus throttle bound the size). Out of scope: own media_source platform, video clips, pictures for motion events.

Implemented executor-only local-media storage, sanitised JPEG paths with atomic writes and symlink rejection, entry-owned daily retention cleanup, and restoration of the newest saved ring before image platform forwarding. Coordinator hooks share a capture-start monotonic reservation across ring and credential events; ring RAM updates are independent of saving and access captures leave the ring cache untouched. Capture and filesystem degradation logs deliberately omit exception text and paths to avoid exposing user or credential data. Existing access payload and ring snapshot tests remain unchanged.

Local validation on Python 3.12: all 900 unit tests passed; validate.py, integration py_compile, E2E-test syntax compilation and git diff --check passed. No Home Assistant/intercom or E2E run was attempted on the VM.

Evidence for review (criteria remain unchecked):
AC #1: tests/test_config_flow.py covers Camera-only fields, default-off saving, retention without a default, option removal and entry.options/data separation.
AC #2: options tests cover missing/0/366/non-integer retention, accepted 1/365 boundaries, retention-first error ordering and unavailable media roots.
AC #3: tests/test_event_pictures.py covers root selection, ASCII title sanitisation, local-time layout, collision suffixes, rejected kinds and symlink confinement.
AC #4: tests/test_coordinator_event_pictures.py proves counted call/button rings save the captured bytes after RAM publication; off/no-store behaviour and existing ring tests are unchanged.
AC #5: credential/result matrix tests cover the four supported event kinds, all excluded events, unchanged last-ring cache and exact baseline bus payload equality.
AC #6: replay tests assert that ring and access file paths exclude synthetic credential and user/peer identities.
AC #7: fake monotonic-clock tests cover every capture-kind pair, the 10-second boundary, simultaneous reservations, pending requests and unthrottled ring RAM captures.
AC #8: snapshot/empty-image/OSError/unavailable-media tests prove event and cache isolation, safe logs and one unavailable-folder warning per setup.
AC #9: helper retention tests cover old/new/boundary files, empty folders, sibling entries and symlinks; setup tests prove executor cleanup, immediate/daily scheduling and entry unload cancellation. The cleanup walk streams paths rather than retaining all JPEG paths in memory.
AC #10: setup tests restore the newest saved ring with UTC file time before forwarding, exercise the image entity, exclude access images and preserve an already captured ring. Off/camera-off/no-camera setups start empty without filesystem jobs.
AC #11: executor-thread/call assertions cover all file IO; translation consistency tests cover new labels/descriptions/errors in en/de/cs; README and architecture docs updated. No CHANGELOG or manifest version change.
AC #12: e2e/tests/test_40_options_flow.py adds the REST Camera retention-error check, aborts its draft and verifies unchanged options without dumping private option values. It skips camera-off/no-camera entries and retains the existing never-submit-final-step safety guard. Execution awaits e2e-pi.
AC #13: pending tester-agent verification after merge.
AC #14: pending maintainer physical-event/media/restart verification.

Task left In Progress for the orchestrator; no acceptance criteria or terminal status changed.

2026-11-21: Jan confirmed in the conversation that he checked the whole v1.6.0 on staging and the real intercom; the outstanding manual criteria are closed on that statement.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented by the headless coder. Checks green on 647101da1 after 0 fix round(s): e2e-pi=pass, validate=pass, validate=pass. PR: https://github.com/mastalir1980/ha-2N-intercom/pull/135. To Test takes effect when the PR is merged.
AC #1: tests/test_config_flow.py: test_event_picture_fields_default_off_and_retention_has_no_default (Required bool default off, Optional retention without default, NumberSelector 1..365 step 1 box 'd'), test_event_picture_fields_only_on_camera_step_and_removed_when_skipped (fields absent on device step; keys removed when camera off/no camera). Code writes only to the options flow data (entry.options). Full suite of 900 tests passes locally. (proven)
AC #2: config_flow.async_step_camera validates retention (bool/non-number/out of 1..365/non-integer -&gt; errors['event_picture_retention_days']='retention_required') before checking resolve_media_root/is_writable via executor (-&gt; 'media_dir_unavailable'); covered by the new config-flow option tests for missing/0/366/1/365 and unavailable roots; both errors present in strings.json and all translations. (proven)
AC #3: tests/test_event_pictures.py: test_root_selection, test_slug_names_are_single_ascii_components, test_paths_use_local_time_and_increment_collision_suffix, test_unknown_kinds_are_rejected, test_symlink_paths_never_escape_or_touch_targets; event_pictures.build_picture_path asserts confinement under root/2n_intercom. (proven)
AC #4: tests/test_coordinator_event_pictures.py: test_counted_ring_saves_existing_capture_after_ram_is_published, test_counted_button_ring_saves_once, test_no_store_writes_nothing_with_ring_capture_on_or_off; existing ring snapshot tests unchanged and green (only a test stub was extended in test_config_flow.py; no assertions removed). (proven)
AC #5: test_each_credential_result_saves_kind_without_changing_ring, test_api_and_every_followup_capture_nothing_even_without_throttling, test_exact_bus_payloads_match_without_store_for_all_access_types; coordinator hook limited to Card/Code/MobKey/Finger with granted not None and does not touch _ring_snapshot; bus payload code untouched. (proven)
AC #6: test_ring_and_access_paths_never_use_replayed_identity asserts written paths exclude replayed card/PIN/mobile key/user/peer values; filenames are built only from time and fixed kind. (proven)
AC #7: test_shared_ten_second_window_for_every_pair_of_capture_kinds, test_two_synchronous_access_events_reserve_before_any_request, test_ring_reserves_before_request_can_trigger_competing_access, test_throttle_uses_start_not_completion_of_pending_request, tests/test_event_pictures.py test_reservation_is_monotonic_from_start_and_shared (fake monotonic clock, allowed again at 10 s). Ring RAM capture is not gated by try_reserve. (proven)
AC #8: test_snapshot_failures_keep_ram_counters_and_events_without_private_logs, test_oserror_writes_do_not_escape_or_corrupt_ram_events_or_counters, test_unavailable_media_warns_once_and_never_breaks_event_handling; tests/test_init.py test_unavailable_media_logs_once_per_setup_and_no_timer. Log messages omit paths and exception text. (proven)
AC #9: tests/test_event_pictures.py test_retention_only_removes_old_jpegs_and_empty_date_folders, test_cleanup_and_restore_never_follow_device_symlink, test_cleanup_skips_file_errors_with_private_data_free_debug; tests/test_init.py test_cleanup_runs_at_setup_in_executor_and_daily_timer_cancels_on_unload (async_track_time_interval registered through entry.async_on_unload). (proven)
AC #10: tests/test_init.py test_setup_restores_newest_ring_and_image_file_time_before_forwarding, test_off_camera_off_and_no_camera_do_not_read_saved_images, test_restore_never_overwrites_an_already_captured_ring; tests/test_event_pictures.py test_restore_uses_newest_ring_name_and_utc_file_time_not_access (access pictures excluded by the ring-only filename regex). (proven)
AC #11: tests/test_event_pictures.py test_all_file_io_is_in_executor_and_not_event_loop_thread; all IO in event_pictures.py and config_flow goes through hass.async_add_executor_job; tests/test_translations.py test_event_picture_options_and_errors_are_translated plus existing key-parity tests green; README has option rows, 'Event picture history' section and privacy note; git diff --name-only shows no CHANGELOG.md or manifest.json change. (proven)
AC #12: e2e/tests/test_40_options_flow.py::test_options_flow_event_picture_retention_required walks Device -&gt; Camera, asserts both fields, submits save_event_pictures=True without retention, asserts the 'retention_required' field error on the camera step, aborts in finally and asserts options unchanged; never submits the final step, no ring/call/relay. Skips if the camera is off or absent. e2e-pi reported green by the orchestrator. (proven)
AC #13: Needs the tester agent on staging after merge: see the new option and retention field on the Camera options step and confirm no 2n_intercom error in the HA system log after enabling it and restarting. (manual)
AC #14: Needs Jan on the real intercom: one ring, one valid and one wrong card/code; check Media &gt; My media &gt; 2n_intercom file names and that the last-ring image shows the last ring picture after a restart. (manual)

AC #13: confirmed by Jan on 2026-11-21 (manual check of the whole v1.6.0 before the release). (manual, confirmed)
AC #14: confirmed by Jan on 2026-11-21 (manual check of the whole v1.6.0 before the release). (manual, confirmed)
<!-- SECTION:FINAL_SUMMARY:END -->
