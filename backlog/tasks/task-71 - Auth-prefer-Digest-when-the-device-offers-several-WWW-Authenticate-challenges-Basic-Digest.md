---
id: TASK-71
title: >-
  Auth: prefer Digest when the device offers several WWW-Authenticate challenges
  (Basic + Digest)
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-21T19:30:00Z'
updated_date: '2026-10-21T19:31:00Z'
labels:
  - bug
  - security
  - api
milestone: m-0
dependencies:
  - TASK-67
references:
  - custom_components/2n_intercom/api.py
  - custom_components/2n_intercom/__init__.py
  - tests/test_api.py
  - docs/API_REFERENCE.md
  - docs/SECURITY-REVIEW-v1.5.0.md
priority: high
type: bug
ordinal: 76000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
**Why.** 2N configures the auth scheme per HTTP API service group, and a service can offer **Basic and Digest at the same time**. The E2E intercom was configured exactly like that until 2026-10-21; it now offers Digest only on every endpoint, which hid this bug but did not fix it. After TASK-67 (Basic refused over unverified HTTPS without `allow_insecure`) users with a Basic+Digest device will stop connecting in v1.5.0: setup/reauth fail with `basic_auth_refused` and a Repair issue tells them to "switch the device to Digest", although the device already offers Digest. This is our bug, not a breaking change we can document, so it blocks the v1.5.0 release (TASK-37).

**Current behaviour (code reading).** The integration never picks Digest from a multi-challenge 401 when Basic comes first:
- aiohttp `DigestAuthMiddleware._authenticate` reads only the first header: `response.headers.get("www-authenticate", "")`, then `partition(" ")` and returns False when that scheme is not `digest` (aiohttp 3.12.x, `client_middleware_digest_auth.py`, ~line 399-410). A second `WWW-Authenticate: Digest ...` header is ignored.
- `TwoNIntercomAPI._requires_basic_auth` (api.py ~503-507) also uses `headers.get("WWW-Authenticate")` and only checks for the substring `basic`.
- Result in `_async_request` (api.py ~649-700): device answers 401 with `Basic` first and `Digest` second → middleware does nothing → integration falls back to Basic. Before TASK-67 that sent Basic over unverified HTTPS (works, but leaks the password, S-1); with TASK-67 it is refused → the user cannot connect at all.

**Expected behaviour.** On a 401 the integration evaluates **all** challenges (multiple `WWW-Authenticate` headers via `getall`, and several challenges combined in one header). If any challenge is Digest, it authenticates with Digest, independent of header order. Basic is considered only when no Digest challenge is offered, and then the TASK-67 rule (`verify_ssl` or `allow_insecure`) applies unchanged. The TASK-67 error/Repair is raised only when Basic is the only scheme offered.

**Decision (Jan, 2026-10-21): own challenge selection in `_async_request`.** The integration selects the challenge itself; the shared `DigestAuthMiddleware(preemptive=False)` session setup stays as is. Rejected: subclassing `DigestAuthMiddleware` and overriding its private `_authenticate` (depends on aiohttp internals that HA upgrades can change).

**Evidence.** E2E after the device was switched to Digest-only: green (PR #99 run) — proves TASK-67 works with Digest, not this case. The Basic+Digest case cannot be reproduced in CI because the device configuration cannot be changed there; hence the `[jan]` check.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A 401 with two headers `WWW-Authenticate: Basic realm=...` then `WWW-Authenticate: Digest realm=...,nonce=...,qop="auth"` is answered with a valid Digest `Authorization` header and no Basic credentials are ever sent [unit]
- [ ] #2 The same holds for the reverse header order and for both challenges combined in one header (`Basic realm="x", Digest realm="x", nonce="..."`) [unit]
- [ ] #3 With protocol https, verify_ssl False, allow_insecure False and a Basic+Digest 401, no TwoNInsecureAuthRefusedError is raised, no WARNING about refused Basic is logged and no Repair issue is created [unit]
- [ ] #4 A 401 offering only Basic keeps the TASK-67 behaviour unchanged (refused without verify_ssl/allow_insecure, retried with Basic when permitted) [unit]
- [ ] #5 A 401 offering only Digest is handled exactly as today; wrong credentials still end in TwoNAuthenticationError / reauth, with no endless retry loop [unit]
- [ ] #6 No credential, nonce-derived response or Authorization header value appears in any log line [unit]
- [ ] #7 docs/API_REFERENCE.md documents that a 2N service can offer Basic and Digest at once and that the integration prefers Digest; README auth section mentions it if it explains the Basic rule [unit]
- [ ] #8 Full unit suite, validate.py and py_compile green; PR check e2e-pi green (device is Digest-only) [e2e]
- [ ] #9 Jan temporarily switches the E2E intercom HTTP API services to Basic + Digest: setup, reload and diagnostics work over HTTPS with the self-signed certificate without allow_insecure, no Repair issue appears; then he switches it back to Digest-only [jan]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. api.py: add a small pure helper (e.g. `_parse_auth_challenges(headers) -> list[tuple[scheme, params]]`) that reads `headers.getall("WWW-Authenticate", [])` and splits comma-combined challenges (quoted strings may contain commas). Use it in `_requires_basic_auth` / `_async_request` instead of `headers.get(...)`.
2. `_async_request`: when the 401 offers a Digest challenge that the middleware did not answer (Basic came first), answer that Digest challenge with one retry request carrying a Digest `Authorization` header (RFC 7616: MD5 / SHA-256, qop=auth, nc, cnonce; same algorithms the aiohttp middleware supports). Only when no Digest challenge exists, go to the existing Basic path with the unchanged TASK-67 permission check. One retry at most; a second 401 is returned to the caller as today (-> TwoNAuthenticationError).
3. Do not touch the session setup (`DigestAuthMiddleware(preemptive=False)` in api.py and __init__.py), the Basic retry mechanics, `_basic_auth_permitted`, the RTSP path, entry.data/options split. Do not subclass the middleware or call its private methods (rejected variant).
4. Tests (tests/test_api.py): fake 401 responses with multi-header and combined-header challenges in both orders; Basic-only and Digest-only regressions; assert no Basic Authorization sent and no refusal WARNING/Repair for Basic+Digest; assert logs carry no credentials. Unit-test the parser on quoted commas.
5. Docs: docs/API_REFERENCE.md (2N quirk: Basic+Digest per service), README auth note if present.
<!-- SECTION:PLAN:END -->
