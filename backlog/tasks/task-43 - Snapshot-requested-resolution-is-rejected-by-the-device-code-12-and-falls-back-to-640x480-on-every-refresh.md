---
id: TASK-43
title: >-
  Snapshot: requested resolution is rejected by the device (code 12) and falls
  back to 640x480 on every refresh
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-15 16:35'
updated_date: '2026-10-16 15:25'
labels:
  - camera
  - snapshot
milestone: m-0
dependencies:
  - TASK-41
references:
  - custom_components/2n_intercom/api.py
  - custom_components/2n_intercom/camera.py
  - docs/API_REFERENCE.md
priority: medium
type: bug
ordinal: 50000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: the debug log from the production HA (2026-10-15, 16:52-17:23) shows the device rejecting snapshot requests with code=12 description='invalid image resolution' param='width or height' for sizes 872x491, 436x246, 436x236 and 80x80. Each time the integration retries at 640x480 and succeeds. Roughly every 10 s this means two snapshot requests instead of one, and the image is always 640x480 regardless of what the camera entity asked for. Current behaviour: the snapshot request uses a size that is not in the device's camera/caps list; the error is handled by a retry at a fixed 640x480 (api.py snapshot path, camera.py). Expected behaviour: the requested size is chosen from the jpeg resolutions reported by /api/camera/caps (nearest supported size at or above the wanted size, else the largest supported one), so the device does not reject normal snapshot requests. The fixed 640x480 retry is only a last resort when camera/caps is unavailable. Evidence: production debug log lines 'Snapshot at WxH rejected by device (code=12 ...) retrying at 640x480' with the timestamps above.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Snapshot requests use a resolution listed in camera/caps whenever camera/caps is available; no code-12 rejection occurs for the sizes HA asks for in normal operation
- [ ] #2 When camera/caps is unavailable the fixed 640x480 fallback is kept and logged once at debug level
- [ ] #3 Unit tests cover: exact match in caps, nearest larger size, largest size when the wanted one is above all caps, and caps unavailable
- [ ] #4 Existing snapshot tests in tests/test_camera*.py or tests/test_api.py updated and green; full unit suite and validate.py green on Python 3.12+
- [ ] #5 Manual check by Jan on the production device: debug log shows no 'invalid image resolution' lines after a snapshot refresh
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. api.py: add a new static helper `TwoNIntercomAPI._select_snapshot_resolution(capabilities, *, width, height) -> tuple[int, int] | None`, placed next to `_select_mjpeg_resolution` (~line 559). Rules: no `jpeg_resolutions` in caps -> return None; exact match -> it; otherwise the smallest caps size (by area) with width >= wanted and height >= wanted; if none is large enough -> the largest caps size (by area, same sort key as `_select_mjpeg_resolution`). Aspect ratio is not matched (HA scales the image).
2. Do NOT change `_select_mjpeg_resolution`: it is also used by the MJPEG URL builders (~lines 1491, 1540) and `async_get_camera_transport_info` (~line 1760); changing it would alter MJPEG/transport behaviour, which is out of scope.
3. api.py `async_get_snapshot` (~line 1917): keep the current defaults (None -> 640x480) as the *wanted* size, then call `await self.async_get_camera_caps()` (cached after the first fetch; it already degrades to an empty `CameraCapabilities` on failure, so no new try/except) and replace width/height with `_select_snapshot_resolution(...)` when it returns a size. When it returns None, keep the wanted size and log once at debug level ("camera/caps has no JPEG resolutions; snapshot uses requested size with 640x480 fallback"), guarded by a new instance flag `self._snapshot_caps_fallback_logged` initialised in `__init__`.
4. Keep the existing code-12 retry at 640x480 unchanged as the last-resort safety net (it still covers the caps-unavailable case and the coordinator's ring snapshot). Do not remove it and do not raise its log level; one bad response must never break the camera entity.
5. Do not change coordinator.py or camera.py: `coordinator.async_get_snapshot` keeps its cache keyed by the size HA requested (resolution mapping happens inside the API client), and `_capture_ring_snapshot` keeps calling `async_get_snapshot(source=...)` without a size. Keep `api.py` stateless apart from the existing caps cache and the new log-once flag.
6. tests/test_api.py: add unit tests for `_select_snapshot_resolution` next to the `_select_mjpeg_resolution` tests (~line 1393): exact match; nearest larger (e.g. caps 320x240/640x480/1280x960, wanted 436x246 -> 640x480; wanted 80x80 -> 320x240); wanted above all caps (872x491 with max 640x480 -> 640x480; 2000x2000 -> largest); empty caps -> None.
7. tests/test_api.py: add async tests next to `test_get_snapshot_non_image_with_code12_retry` (~line 1817): (a) with caps set, a request for 872x491 sends the chosen caps size in the request params and makes exactly one HTTP request (no retry); (b) with empty caps the requested size is sent unchanged and the debug message is logged only once across two calls. Update the existing code-12 retry test only if it needs explicit empty caps to keep testing the fallback path.
8. docs/API_REFERENCE.md: in the `/api/camera/snapshot` row / firmware-quirks section, note that the snapshot size is mapped to the nearest `camera/caps` JPEG resolution and that the 640x480 code-12 retry is only a fallback.
9. Validation: `python3 -m unittest discover -s tests -t tests` and `python3 validate.py` on Python 3.12+, `python3 -m py_compile custom_components/2n_intercom/*.py`, then green `bash e2e/e2e.sh wip` (headless: PR check `e2e-pi`). No relay tests. AC #5 (no 'invalid image resolution' in Jan's debug log) is verified by Jan after merge.
<!-- SECTION:PLAN:END -->
