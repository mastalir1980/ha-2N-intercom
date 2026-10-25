---
id: TASK-2.3
title: >-
  Small API/camera hardening: shared session for the MJPEG probe, no API
  credentials in MjpegCamera, random RTSP cnonce
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-24T08:29:00Z'
updated_date: '2026-10-25 16:05'
labels:
  - tech-debt
  - security
  - api
  - camera
milestone: m-1
dependencies: []
references:
  - docs/IMPROVEMENTS.md
  - docs/SECURITY-REVIEW-v1.5.0.md
  - custom_components/2n_intercom/api.py
  - custom_components/2n_intercom/camera.py
  - tests/test_api.py
  - tests/test_camera.py
parent_task_id: TASK-2
priority: low
type: enhancement
ordinal: 80000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: three small findings with no user-visible behaviour change, bundled because each is a few lines in api.py/camera.py.
- B3 (docs/IMPROVEMENTS.md): _async_request_without_auth (api.py:700-721) builds a new aiohttp.ClientSession + TCPConnector per call (used by the public MJPEG probe, api.py ~1597) instead of reusing the integration session.
- O-5 (docs/SECURITY-REVIEW-v1.5.0.md): camera.py:148-149 passes the HTTP API username/password to MjpegCamera. The integration overrides async_camera_image and handle_async_mjpeg_stream, so MjpegCamera never uses them today, but its own fetch would send Basic regardless of allow_insecure if a refactor revived that path.
- O-3 (same review): the RTSP Digest cnonce is md5(nonce)[:8] (api.py:1732), predictable; RTSP username/realm go into the header without rejecting quotes/CR/LF.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The unauthenticated MJPEG probe does not create a new ClientSession per call and keeps its "no auth" semantics (no Authorization header, no Digest middleware) [unit]
- [ ] #2 MjpegCamera is constructed without the HTTP API username and password; snapshot and MJPEG stream still work through the integration request path [unit]
- [ ] #3 RTSP Digest uses a random cnonce (secrets) and refuses a username or realm containing a double quote, CR or LF without sending the request [unit]
- [ ] #4 E2E: camera_proxy returns a JPEG and the camera entity stream works as before [e2e]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Reuse the integration API session for the public MJPEG probe with per-request middlewares=(), preserving unauthenticated semantics and leaving shared session configuration untouched. If session defaults prevent this, use the task-approved reusable no-auth session closed by async_close.
2. Construct MjpegCamera with username=None and password=None, preserving the overridden snapshot and MJPEG integration request paths.
3. Generate RTSP Digest cnonce with secrets.token_hex(4), reject quotes/CR/LF in username or realm before sending the authenticated request, and log failures at DEBUG without values.
4. Extend API and camera unit coverage plus camera E2E coverage for JPEG proxy and streaming; mark B3 and O-3/O-5 implemented in the referenced docs.
5. Run all prescribed local Python gates, record implementation notes, and commit locally without ticking criteria, finalizing status, pushing, or running device E2E.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented the task-approved per-request middleware override: the public MJPEG probe reuses async_get_session() with middlewares=(), never mutates shared session configuration, and does not invoke the normal Basic fallback path. Unit coverage exercises repeated public probes, Basic/Digest 401 challenges without retry, injected-session reuse, owned-session reuse/cleanup, and the unaffected normal request path.
MjpegCamera now receives username=None and password=None. Camera regressions cover credentials-free URLs, coordinator-backed snapshots with requested dimensions, and MJPEG delegation through the same snapshot path.
RTSP Digest uses secrets.token_hex(4). Unsafe usernames fail before opening a connection; unsafe realms (including escaped or malformed quotes, CR and LF) fail before authenticated OPTIONS. Regression tests cover fresh cnonce generation and digest calculation, legacy no-qop support, successful authenticated OPTIONS, connection cleanup, and DEBUG messages without credentials or invalid values.
Updated README, architecture notes, B3 completion, and O-3/O-5 implementation references. The existing JPEG camera_proxy E2E regression is retained; test_camera_stream_contains_jpeg_frames adds a bounded multipart stream check requiring two complete JPEG frames.
Local validation on Python 3.12.15: all 766 unit tests passed; python3 validate.py passed; integration and changed E2E test Python compilation passed; git diff --check passed. Existing unrelated exception-path test doubles emit unawaited-coroutine RuntimeWarnings and were left unchanged.
E2E was not run on the VM, as required; AC #4 awaits the Pi e2e-pi check. All acceptance checkboxes remain unchanged, and the task remains In Progress for the orchestrator review/finalization.
<!-- SECTION:NOTES:END -->
