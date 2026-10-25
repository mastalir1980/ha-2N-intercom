---
id: TASK-73
title: Camera and last-ring image are created on devices without a camera
status: To Do
assignee: []
created_date: '2026-10-24T08:28:00Z'
updated_date: '2026-10-24T08:28:00Z'
labels:
  - camera
  - compatibility
  - github-issue
  - needs-analysis
milestone: m-1
dependencies: []
references:
  - https://github.com/mastalir1980/ha-2N-intercom/issues/105
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
