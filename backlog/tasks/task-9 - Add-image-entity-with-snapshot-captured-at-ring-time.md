---
id: TASK-9
title: Add image entity with snapshot captured at ring time
status: Done
assignee:
  - '@copilot'
created_date: '2026-08-30 09:27'
updated_date: '2026-10-15 12:12'
labels:
  - camera
  - ha-platform
milestone: m-0
dependencies:
  - TASK-1
priority: high
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add an image platform (image.py) with a 'Last ring' image entity. When the ring event fires in the coordinator, capture a JPEG snapshot via the existing /api/camera/snapshot client path and store it (bytes + timestamp) in coordinator data; the image entity serves that stored frame, so notifications and dashboards show the moment of the ring, not the current view. Handle camera-disabled entries (do not create the entity), snapshot failures (keep previous image, log warning) and expose the capture timestamp as the entity image_last_updated. Register platform, strings/translations, icons and unit tests.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 image entity shows the snapshot taken at the last ring with correct last-updated timestamp
- [x] #2 Snapshot failure during ring keeps the previous image and logs a warning (covered by test)
- [x] #3 Entity not created when camera is disabled in options
- [x] #4 strings.json, translations (en/de/cs), icons.json updated; unit tests added
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. coordinator: ring_snapshot_enabled flag (camera option); on a new ring schedule a snapshot capture task; on success store bytes + tz-aware time in TwoNIntercomData and notify; on failure keep previous image and log warning.
2. image.py: TwoNIntercomRingImage(TwoNIntercomEntity, ImageEntity), translation_key last_ring, serves stored bytes, image_last_updated = capture time.
3. __init__._get_platforms adds image only when camera enabled.
4. strings/translations/icons; tests/test_image.py + coordinator tests; E2E entity check.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Validation: python3 -m unittest discover -s tests -t tests (530 OK), python3 validate.py OK, py_compile OK. E2E 'bash e2e/e2e.sh wip' on staging (2N IP Force fw 3.3.1.82.4, HA 2026.10.1): 13 passed, 3 skipped, 1 failed — the failure is the pre-existing, unrelated TASK-18 options-flow test. test_50_access_control.py::test_last_ring_image_follows_camera passed on staging.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
New image platform (image.py) with a last_ring entity showing the snapshot captured by the coordinator on each ring event; image_last_updated follows the capture time, a failed capture keeps the previous image and logs a warning. Platform is only loaded when the camera is enabled. Translations/icons updated; verified by tests/test_image.py, test_coordinator_access.py, test_init PlatformSelectionTests and the E2E image test.
<!-- SECTION:FINAL_SUMMARY:END -->
