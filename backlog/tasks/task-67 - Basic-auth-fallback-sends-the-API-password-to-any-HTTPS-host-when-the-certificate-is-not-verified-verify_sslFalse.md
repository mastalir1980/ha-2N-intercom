---
id: TASK-67
title: >-
  Basic-auth fallback sends the API password to any HTTPS host when the
  certificate is not verified (verify_ssl=False)
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-21T09:44:00Z'
updated_date: '2026-10-21T10:49:00Z'
labels:
  - security
  - bug
  - api
  - config-flow
milestone: m-0
dependencies: []
references:
  - custom_components/2n_intercom/api.py
  - custom_components/2n_intercom/config_flow.py
  - custom_components/2n_intercom/strings.json
  - tests/test_api.py
  - docs/IMPROVEMENTS.md
  - docs/SECURITY-REVIEW-v1.5.0.md
priority: high
type: bug
ordinal: 72000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the security review before v1.5.0 (docs/SECURITY-REVIEW-v1.5.0.md, finding S-1).

**Current behaviour.** `TwoNIntercomAPI._basic_auth_permitted()` (api.py:507-519) returns True for `protocol == https` regardless of `verify_ssl`. With `verify_ssl=False` — the auto-detect result for the factory self-signed certificate, i.e. the typical installation — TLS encrypts the connection but does not authenticate the server. The first request goes out without credentials (Digest middleware, `preemptive=False`); whoever answers it with `401 WWW-Authenticate: Basic` gets `Authorization: Basic base64(user:password)` on the retry (api.py:667-694). The real device's auth configuration is irrelevant: the challenge comes from whoever answers.

**Who can answer.** An on-path attacker on the LAN (ARP/DNS spoofing), or — much easier — any LAN host that sends one SSDP announcement with the intercom's MAC (TASK-68): the integration rewrites `entry.data[host]` to the attacker and reloads. The MAC is public on the LAN (ARP table, the device's unauthenticated `/ssdp_server/description.xml`).

**Impact.** The HTTP API account password in cleartext (base64). That account usually has *Switch – Control*, so the attacker can open the door directly through the device API from the LAN. The RTSP probe additionally hands the attacker a Digest response of the RTSP credentials (offline brute-force). The S3 fix in 1.4.0 (docs/IMPROVEMENTS.md) only covered plaintext HTTP; it treated HTTPS as safe without distinguishing verified from unverified certificates.

**Expected behaviour.** HTTPS without certificate verification counts as an insecure transport, exactly like plaintext HTTP: the automatic Basic fallback is used only when `verify_ssl=True`; with `verify_ssl=False` (or HTTP) it needs the explicit `allow_insecure` opt-in, which stays where it is today (Reconfigure flow, `entry.options`). Digest is untouched.

**Decision (Jan, 2026-10-21): variant B — no opt-in during initial setup.** When the device demands Basic over an unverified connection, the user step fails with a dedicated error (not a generic `cannot_connect`) that tells the user what to do on the device: switch the HTTP API services to Digest authentication, or install a certificate Home Assistant trusts so the verified-HTTPS candidate wins. The `allow_insecure` checkbox is deliberately not added to the user step. Existing entries that relied on Basic over unverified HTTPS stop working after the upgrade; they get a clear path: a WARNING, a Repair issue and the same dedicated error in the reauth form, all pointing to Reconfigure → "Allow insecure connection" (or to fixing the device). The v1.5.0 release notes (TASK-37) carry this as a breaking change in a Security section. Rejected: (a) an opt-in checkbox in the user step (invites ticking it without understanding), (c) keep the fallback and only log a WARNING (the password still leaks).

**Evidence.** `tests/test_api.py::test_basic_retry_requires_https_or_explicit_opt_in` (case https / no opt-in / Basic → retry=True) and `test_basic_auth_permitted_over_https` document the current behaviour and must be updated. Observed by code reading only; not reproduced against a device.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 With protocol https, verify_ssl False and allow_insecure False, a 401 Basic challenge is not answered with Basic credentials: _async_request raises a dedicated TwoNInsecureAuthRefusedError (subclass of TwoNAuthenticationError) and logs one WARNING naming the reason, with no credential in the log [unit]
- [ ] #2 With protocol https and verify_ssl True the Basic fallback keeps working exactly as today [unit]
- [ ] #3 With verify_ssl False (or protocol http) and allow_insecure True, Basic is sent: one explicit opt-in rule for both insecure transports [unit]
- [ ] #4 Digest authentication is unaffected in every protocol/verify_ssl/allow_insecure combination [unit]
- [ ] #5 Initial setup (user step) against a device that demands Basic over an unverified connection ends with the dedicated error basic_auth_refused, not cannot_connect; its text tells the user to switch the device HTTP API services to Digest or to install a trusted certificate; no allow_insecure field is added to the user step [unit]
- [ ] #6 Reauth against such a device shows the same dedicated error (not invalid_auth) and its text also points existing entries to Reconfigure > Allow insecure connection [unit]
- [ ] #7 At runtime a refused Basic fallback creates one Repair issue (issue_registry, severity warning, not fixable, translated, placeholder = entry title) pointing to Reconfigure > Allow insecure connection or to fixing the device; the issue is removed when a request succeeds again or the entry is unloaded [unit]
- [ ] #8 strings.json and en/cs/de translations contain the new config error, the Repair issue texts and an allow_insecure description that covers both plaintext HTTP and HTTPS with an unverified certificate; test_translations stays green [unit]
- [ ] #9 README and INSTALLATION explain the rule (Basic only over verified HTTPS, otherwise the opt-in in Reconfigure), the device-side fix (Digest or trusted certificate) and the upgrade step for existing installations; docs/IMPROVEMENTS.md S3 gets a note that unverified HTTPS counts as insecure [unit]
- [ ] #10 The final summary contains the user-facing release note (Security, breaking change) for TASK-37 to copy into CHANGELOG 1.5.0 [unit]
- [ ] #11 Full unit suite, validate.py and py_compile green; PR check e2e-pi green [e2e]
- [ ] #12 Jan verifies on the E2E intercom (HTTPS, self-signed certificate, Digest accounts) that setup, reauth and runtime work without the opt-in, and that a device temporarily switched to Basic shows the new error and the Repair issue [jan]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. api.py: add `TwoNInsecureAuthRefusedError(TwoNAuthenticationError)`. `_basic_auth_permitted()` returns True only for `verify_ssl is True` or `allow_insecure`; the protocol alone no longer matters. In `_async_request`, when the challenge is Basic and the fallback is not permitted, log the WARNING (protocol, verify_ssl, host; never credentials) and raise the new error instead of yielding the 401. `async_test_connection` must let the new error propagate (or return a tri-state) so the config flow can tell it apart from "unreachable". Do not touch the Digest middleware (`preemptive=False`) or the Basic retry mechanics themselves (architecture rule: dual auth is intentional).
2. config_flow.py: `_async_try_connect` catches `TwoNInsecureAuthRefusedError` and remembers it; after the candidate loop, when nothing connected and a refusal was seen, set `errors["base"] = "basic_auth_refused"` instead of `cannot_connect`. Same in `async_step_reauth_confirm` (instead of `invalid_auth`) and in `_async_reconfigure_user_step` (there the user can tick allow_insecure directly). Keep the auto-detect order (verified HTTPS → unverified HTTPS → HTTP) and add no field to the user step.
3. coordinator.py / __init__.py: on `TwoNInsecureAuthRefusedError` create the Repair issue `basic_auth_refused_<entry_id>` via `homeassistant.helpers.issue_registry` (lazy import with a stub fallback, pattern: `ConfigEntryAuthFailed` in coordinator.py); delete it on the next successful `_async_update_data` and in `async_unload_entry`. Keep the existing 3-strike reauth behaviour.
4. strings.json + translations/{en,cs,de}.json: `config.error.basic_auth_refused`, `issues.basic_auth_refused.{title,description}`, updated `allow_insecure` data_description.
5. Tests: update `test_basic_retry_requires_https_or_explicit_opt_in` and `test_basic_auth_permitted_over_https` (now needs verify_ssl=True), add the verify_ssl matrix; config-flow tests for the user/reauth/reconfigure errors; coordinator test for the Repair issue lifecycle; translations test.
6. Docs: README (connection security section), INSTALLATION, docs/IMPROVEMENTS.md S3 note; put the release-note text into the final summary.
Must not change: `entry.data` / `entry.options` split (allow_insecure stays in options), the RTSP path, the SSDP flow (TASK-68 is separate).
<!-- SECTION:PLAN:END -->
