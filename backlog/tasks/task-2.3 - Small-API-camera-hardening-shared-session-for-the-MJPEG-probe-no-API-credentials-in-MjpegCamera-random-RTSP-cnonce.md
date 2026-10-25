---
id: TASK-2.3
title: >-
  Small API/camera hardening: shared session for the MJPEG probe, no API
  credentials in MjpegCamera, random RTSP cnonce
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-24T08:29:00Z'
updated_date: '2026-10-24T08:29:00Z'
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
1. api.py _async_request_without_auth: reuse the API session and disable the Digest middleware for this request only (aiohttp per-request middlewares=() override, available with DigestAuthMiddleware) or reuse one lazily created no-auth session closed in async_close; pick the one that keeps the HA-shared session untouched. Verify no Authorization header is sent.
2. camera.py ~148: pass username=None, password=None to MjpegCamera; keep the overridden async_camera_image / handle_async_mjpeg_stream.
3. api.py RTSP Digest (~1720-1740): cnonce = secrets.token_hex(4); validate username and realm (no ", \r, \n) before building the header; on invalid input treat the RTSP probe as failed with a DEBUG log without values.
4. Unit tests in tests/test_api.py and tests/test_camera.py; docs/IMPROVEMENTS.md mark B3 done, docs/SECURITY-REVIEW-v1.5.0.md O-3/O-5 add "implemented in TASK-2.3".
Must not change: dual Basic/Digest auth on the normal request path, allow_insecure rules, RTSP URL handling (known exception for secrets in URL), snapshot resolution logic.
<!-- SECTION:PLAN:END -->
