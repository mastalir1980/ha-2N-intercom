---
id: TASK-2.3
title: >-
  Small API/camera hardening: shared session for the MJPEG probe, no API
  credentials in MjpegCamera, random RTSP cnonce
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-24T08:29:00Z'
updated_date: '2026-10-25 16:09'
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
- [x] #1 The unauthenticated MJPEG probe does not create a new ClientSession per call and keeps its "no auth" semantics (no Authorization header, no Digest middleware) [unit]
- [x] #2 MjpegCamera is constructed without the HTTP API username and password; snapshot and MJPEG stream still work through the integration request path [unit]
- [x] #3 RTSP Digest uses a random cnonce (secrets) and refuses a username or realm containing a double quote, CR or LF without sending the request [unit]
- [x] #4 E2E: camera_proxy returns a JPEG and the camera entity stream works as before [e2e]
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

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented by the headless coder. Checks green on 4d96d1637 after 0 fix round(s): e2e-pi=pass, validate=pass, validate=pass. PR: https://github.com/mastalir1980/ha-2N-intercom/pull/111. Done takes effect when the PR is merged.
AC #1: api.py _async_request_without_auth now calls async_get_session() and passes middlewares=() per request, with no new ClientSession/TCPConnector. tests/test_api.py test_public_probe_reuses_injected_session_without_auth_or_retries patches ClientSession and TCPConnector and asserts neither is created. It asserts request kwargs contain only middlewares=(), params and headers (no auth, no Authorization), no Basic retry on 401 Digest/Basic challenges, shared session middlewares/headers unchanged, and the normal _async_request path unaffected. test_public_probe_creates_owned_session_only_once checks a single owned session, reused and closed by async_close. Full unit suite: 766 tests OK (re-run in review). (proven)
AC #2: camera.py passes username=None and password=None to MjpegCamera.__init__. tests/test_camera.py test_camera_entity_does_not_pass_api_credentials_to_mjpeg_camera asserts _username and _password are None. test_snapshot_and_mjpeg_stream_use_coordinator_snapshot_path asserts async_camera_image and handle_async_mjpeg_stream still go through coordinator.async_get_snapshot. The overridden methods are unchanged. (proven)
AC #3: api.py _build_rtsp_digest_auth uses secrets.token_hex(4) and rejects username/realm containing a quote, CR or LF via _RTSP_DIGEST_UNSAFE_RE. async_probe_rtsp rejects an unsafe username before opening a connection. tests/test_api.py RtspDigestTests covers: a fresh cnonce per challenge via a patched secrets.token_hex(4) with exact header and digest; the no-qop path not using secrets; unsafe username not calling open_connection; unsafe realm variants (quote, escaped quote, CR, LF, with and without qop) never sending an Authorization header and not logging values; a valid probe sending an authenticated OPTIONS with the cnonce. (proven)
AC #4: The existing camera_proxy JPEG test in e2e/tests/test_10_entities.py is retained. The diff adds test_camera_stream_contains_jpeg_frames, which requests camera_proxy_stream, checks the multipart content type and requires two complete JPEG frames. The orchestrator reports e2e-pi green on this head. (proven)
<!-- SECTION:FINAL_SUMMARY:END -->
