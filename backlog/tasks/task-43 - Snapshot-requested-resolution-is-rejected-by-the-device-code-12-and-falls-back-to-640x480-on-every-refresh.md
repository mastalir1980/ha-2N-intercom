---
id: TASK-43
title: >-
  Snapshot: requested resolution is rejected by the device (code 12) and falls
  back to 640x480 on every refresh
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-15 16:35'
updated_date: '2026-10-16 16:04'
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
1. Add _select_snapshot_resolution beside the unchanged MJPEG selector: exact match, smallest supported size covering both wanted dimensions by (area, width, height), otherwise largest; return None without JPEG resolutions.
2. Initialize the log-once fallback flag. Resolve snapshot defaults/source and camera caps once in async_get_snapshot, then delegate HTTP/error handling to _async_fetch_snapshot. Preserve requested size without caps and log that fallback once at debug level.
3. Keep code-12 recovery bounded to one direct _async_fetch_snapshot retry at 640x480 with allow_retry=False, bypassing caps mapping; preserve existing error handling, coordinator caching, camera entities and MJPEG behaviour.
4. Add selector tests and fake-session request-count/parameter tests for mapped resolutions, unavailable caps, successful fallback and repeated rejection when caps omit 640x480. Update the existing recursive-retry test.
5. Update docs/API_REFERENCE.md snapshot endpoint and firmware notes. Run Python 3.12+ unit tests, validate.py and py_compile; leave device E2E to e2e-pi and manual AC #5 to Jan. Record implementation notes and commit locally on the current task branch without checking criteria or setting Done.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Plan revised 2026-10-16 after the headless coder stopped: mapping inside async_get_snapshot would also remap the recursive 640x480 retry and recurse forever when caps omit 640x480. Request logic moves to _async_fetch_snapshot; the single retry bypasses caps.

Implemented _select_snapshot_resolution without changing _select_mjpeg_resolution: exact match, smallest supported size covering both dimensions by (area, width, height), otherwise largest, or None without JPEG resolutions. async_get_snapshot resolves defaults/source and capabilities once, logs the missing-JPEG fallback once at DEBUG, and delegates to _async_fetch_snapshot. The HTTP helper preserves existing response/error handling and permits only one code-12 retry at 640x480 with allow_retry=False, bypassing caps mapping. coordinator.py and camera.py are unchanged.

Added six selector tests and seven async snapshot tests; rewrote the old recursive-retry test to count requests made through an injected fake HTTP session and assert returned image bytes. Coverage includes all reported HA sizes, both-dimension checks, area/tie ordering, caps fetch/cache reuse, log-once fallback, defaults/source normalization, and exactly two requests plus a final WARNING when caps omit 640x480 and every size is rejected. Updated docs/API_REFERENCE.md endpoint and firmware notes.

Local gates passed on Python 3.12.15: python3 -m unittest discover -s tests -t tests (624 tests), python3 validate.py, and python3 -m py_compile custom_components/2n_intercom/*.py. Focused test_api.py discovery also passed (194 tests). No device E2E or relay tests were run on the VM. The e2e-pi PR check and Jan manual verification of AC #5 remain pending; acceptance criteria stay unchecked and task status stays In Progress.

Follow-up outside this task: existing API test doubles emit unawaited-coroutine warnings, and the existing non-image/no-device-error snapshot test double lacks response.url. These pre-existing test-harness issues were left unchanged.
<!-- SECTION:NOTES:END -->
