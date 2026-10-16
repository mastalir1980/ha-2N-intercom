---
id: TASK-43
title: >-
  Snapshot: requested resolution is rejected by the device (code 12) and falls
  back to 640x480 on every refresh
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-15 16:35'
updated_date: '2026-10-16 15:06'
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
