---
id: TASK-73
title: Camera and last-ring image are created on devices without a camera
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-24T08:28:00Z'
updated_date: '2026-11-13 19:34'
labels:
  - camera
  - compatibility
  - github-issue
milestone: m-3
dependencies: []
references:
  - 'https://github.com/mastalir1980/ha-2N-intercom/issues/105'
  - custom_components/2n_intercom/__init__.py
  - custom_components/2n_intercom/api.py
  - custom_components/2n_intercom/config_flow.py
priority: medium
type: bug
ordinal: 78000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: issue #105 (2N IP Uni, fw 2.50): the camera entity is created although the Uni has no camera; /api/camera/snapshot answers code 1 (not supported). Users get a dead camera and a last-ring image entity that never fills.

Current behaviour (fact): _get_platforms() (__init__.py:77-86) adds camera and image whenever the option enable_camera is on; DEFAULT_ENABLE_CAMERA = True (const.py:60). async_get_camera_caps() (api.py:1490) swallows every failure into empty CameraCapabilities, so "device has no camera" and "request failed" look the same.

Expected behaviour: on a device that reports no camera, no camera and no image entity are created and the setup/options flow does not offer camera settings; on a transient failure nothing changes for existing entries.

Open before ready (analysis): which signal reliably means "no camera" on fw 2.x and 3.x (camera/caps code 1, /api/system/caps, hardware info) without reacting to a transient error; whether an existing entry with enable_camera on loses its camera entities (registry cleanup) or keeps them disabled.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A device that reports no camera gets no camera and no image entity, at setup and after restart [unit]
- [ ] #2 A transient camera/caps failure (timeout, 5xx, auth) never removes or hides existing camera entities [unit]
- [ ] #3 The setup and options flow do not offer camera settings on a device without a camera [unit]
- [ ] #4 E2E: the E2E intercom (has a camera) still gets its camera and image entity and camera_proxy returns a JPEG [e2e]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Decisions (analysis 2026-11-13):
- Signal for 'no camera': a definitive device answer from GET /api/camera/caps only. Either a 2N error body with code 1 (function not supported), or success with no JPEG resolutions and no sources. Timeouts, HTTP errors, auth errors and any other 2N code mean 'unknown' and change nothing. The camera/caps answer of a camera-less device is not captured yet (issue #105 only shows camera/snapshot code 1), so the code-1 branch is a hypothesis to confirm with the reporter.
- The result is not persisted: it is re-detected on every setup (camera/caps is already fetched once by the static transport cache). enable_camera stays untouched, so a camera module added later appears after a reload.
- Existing entries: when the device definitively has no camera, the camera and last-ring image registry entries are removed (they can never work).

Steps:
1. api.py: TwoNIntercomAPI.camera_present (bool | None), set in async_get_camera_caps from the parsed answer.
2. coordinator.py: camera_present property; no ring snapshot capture when it is False.
3. __init__.py: _get_platforms(entry, camera_present) skips camera+image when False; setup removes the two registry entries in that case.
4. config_flow.py: setup device step and options device step omit enable_camera and skip the camera step when the device has no camera; unknown keeps today's forms.
5. Unit tests in tests/test_api.py, test_init.py, test_config_flow.py. E2E: assert camera + image entities and a JPEG from camera_proxy on the E2E intercom.
Must not change: dual auth, entry.data/options split, behaviour when detection is unknown.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-13 (Claude): implemented in worktree branch task-73-no-camera-entities-without-camera (not committed yet). api.py: camera_present + _camera_present_from_caps; coordinator.py: camera_present property, no ring snapshot when False; __init__.py: _get_platforms(entry, camera_present) and registry cleanup of <entry>_camera / <entry>_last_ring; config_flow.py: _async_camera_present for the setup form, options flow reads the coordinator. Unit tests: test_api (camera_present_*, camera_absent_*, camera_presence_*), test_init (test_get_platforms_skips_camera_only_when_device_has_none, test_device_without_camera_gets_no_camera_or_image_entity, test_unknown_camera_presence_keeps_camera_entities), test_config_flow (test_device_step_offers_camera_unless_device_has_none, test_device_without_camera_gets_no_camera_settings, test_camera_settings_stay_when_presence_is_unknown), test_coordinator (test_ring_on_device_without_camera_captures_no_snapshot). E2E: test_camera_entities_follow_device_camera in e2e/tests/test_10_entities.py (+ TwoN.camera_caps). Local run: 833 unit tests green except test_blueprint (jinja2 missing in the local Python, unrelated), validate.py green. E2E not run yet. Open: confirm with the issue #105 reporter what camera/caps answers on a camera-less device.
<!-- SECTION:NOTES:END -->
