---
id: TASK-43
title: >-
  Snapshot: requested resolution is rejected by the device (code 12) and falls
  back to 640x480 on every refresh
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-15 16:35'
updated_date: '2026-10-16 15:58'
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
- [ ] #6 Code-12 fallback is bounded: at most one retry at 640x480, sent without caps mapping; with caps that omit 640x480 and a device rejecting every size, exactly two HTTP requests are made and no recursion occurs (unit test)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. api.py: add a new static helper `TwoNIntercomAPI._select_snapshot_resolution(capabilities, *, width, height) -> tuple[int, int] | None`, placed next to `_select_mjpeg_resolution` (~line 559). Rules: no `jpeg_resolutions` in caps -> return None; exact match -> it; otherwise the smallest caps size (by area) with width >= wanted and height >= wanted; if none is large enough -> the largest caps size (by area, same sort key as `_select_mjpeg_resolution`). Aspect ratio is not matched (HA scales the image).
2. Do NOT change `_select_mjpeg_resolution`: it is also used by the MJPEG URL builders (~lines 1491, 1540) and `async_get_camera_transport_info` (~line 1760); changing it would alter MJPEG/transport behaviour, which is out of scope.
3. api.py: split `async_get_snapshot` (~line 1917) into two methods so caps mapping happens exactly once per public call:
   a) New private `async def _async_fetch_snapshot(self, *, width: int, height: int, source: str, allow_retry: bool) -> bytes | None`: contains the current HTTP request, content-type check, error parsing, logging and the existing `except` blocks, moved without behaviour change. It never consults camera/caps.
   b) Public `async_get_snapshot(width=None, height=None, source=None)` keeps its signature: resolve `source` and the defaults (None -> 640x480) as the *wanted* size, call `await self.async_get_camera_caps()` (cached after the first fetch; it already degrades to an empty `CameraCapabilities` on failure, so no new try/except around it), replace width/height with `_select_snapshot_resolution(...)` when it returns a size, then `return await self._async_fetch_snapshot(..., allow_retry=True)`. When the helper returns None, keep the wanted size and log once at debug level ("camera/caps has no JPEG resolutions; snapshot uses requested size with 640x480 fallback"), guarded by a new instance flag `self._snapshot_caps_fallback_logged` initialised in `__init__`.
4. Bounded code-12 fallback (replaces the old recursive retry; this is an intentional, allowed change): inside `_async_fetch_snapshot`, on device error code 12 with `allow_retry` true and `(width, height) != (640, 480)`, log at debug level as today ("Snapshot at %dx%d rejected by device (%s); retrying at 640x480") and `return await self._async_fetch_snapshot(width=640, height=480, source=source, allow_retry=False)`. The retry deliberately bypasses caps mapping: 640x480 is sent as is, even when caps do not list it. With `allow_retry` false a code-12 error is handled like any other device error (existing `log_device_error` WARNING path, return None). Result: at most two HTTP requests per public call, no recursion through `async_get_snapshot`. Keep the log levels; one bad response must never break the camera entity. Update the code comment above the retry to say it is now the last resort for sizes the caps mapping did not prevent (caps unavailable, or firmware rejecting a size it lists).
5. Do not change coordinator.py or camera.py: `coordinator.async_get_snapshot` keeps its cache keyed by the size HA requested (resolution mapping happens inside the API client), and `_capture_ring_snapshot` keeps calling `async_get_snapshot(source=...)` without a size. Keep `api.py` stateless apart from the existing caps cache and the new log-once flag.
6. tests/test_api.py: add unit tests for `_select_snapshot_resolution` next to the `_select_mjpeg_resolution` tests (~line 1393): exact match; nearest larger (e.g. caps 320x240/640x480/1280x960, wanted 436x246 -> 640x480; wanted 80x80 -> 320x240); wanted above all caps (872x491 with max 640x480 -> 640x480; 2000x2000 -> largest); empty caps -> None.
7. tests/test_api.py: add async tests next to `test_get_snapshot_non_image_with_code12_retry` (~line 1817), counting real HTTP requests on the fake session (not by monkeypatching `async_get_snapshot`): (a) with caps set, a request for 872x491 sends the chosen caps size in the request params and makes exactly one HTTP request; (b) with empty caps the requested size is sent unchanged and the debug message is logged only once across two calls; (c) regression for the recursion: caps WITHOUT 640x480 (e.g. 1280x720 and 1920x1080), device answers code 12 to every request -> exactly two HTTP requests (first at the caps size, second at 640x480), result None, no RecursionError; (d) code 12 on the 640x480 retry is not retried again.
8. Rewrite `test_get_snapshot_non_image_with_code12_retry`: it currently monkeypatches `api.async_get_snapshot` to count the recursive call, which no longer exists. Make it assert two HTTP requests with params 80x80 then 640x480 (empty caps) and the image bytes of the second response.
9. docs/API_REFERENCE.md: in the `/api/camera/snapshot` row / firmware-quirks section, note that the snapshot size is mapped to the nearest `camera/caps` JPEG resolution and that a single code-12 retry at 640x480 (sent without caps mapping) is only a fallback.
10. Validation: `python3 -m unittest discover -s tests -t tests` and `python3 validate.py` on Python 3.12+, `python3 -m py_compile custom_components/2n_intercom/*.py`, then green `bash e2e/e2e.sh wip` (headless: PR check `e2e-pi`). No relay tests. AC #5 (no 'invalid image resolution' in Jan's debug log) is verified by Jan after merge.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Plan revised 2026-10-16 after the headless coder stopped: mapping inside async_get_snapshot would also remap the recursive 640x480 retry and recurse forever when caps omit 640x480. Request logic moves to _async_fetch_snapshot; the single retry bypasses caps.
<!-- SECTION:NOTES:END -->
