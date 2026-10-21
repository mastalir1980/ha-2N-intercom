---
id: TASK-67
title: >-
  Basic-auth fallback sends the API password to any HTTPS host when the
  certificate is not verified (verify_ssl=False)
status: To Do
assignee: []
created_date: '2026-10-21T09:44:00Z'
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

**Who can answer.** An on-path attacker on the LAN (ARP/DNS spoofing), or — much easier — any LAN host that sends one SSDP announcement with the intercom's MAC: the integration then rewrites `entry.data[host]` to the attacker and reloads (see the SSDP bug filed with this review). The MAC is public on the LAN (ARP table, the device's unauthenticated `/ssdp_server/description.xml`).

**Impact.** The HTTP API account password in cleartext (base64). That account usually has *Switch – Control*, so the attacker can open the door directly through the device API from the LAN. The RTSP probe additionally hands the attacker a Digest response of the RTSP credentials (offline brute-force). The S3 fix in 1.4.0 (docs/IMPROVEMENTS.md) only covered plaintext HTTP; it treated HTTPS as safe without distinguishing verified from unverified certificates.

**Expected behaviour.** The automatic Basic fallback is used only when the server is authenticated (`verify_ssl=True`). With an unverified certificate it needs the same explicit opt-in as plaintext HTTP (`allow_insecure`), and the user is told why the connection fails. Digest stays untouched.

**Open question for Jan (decide before assigning).** The initial user step has no `allow_insecure` checkbox, so a device that offers only Basic auth on a self-signed certificate would fail setup with a generic `cannot_connect`. Options: (a) add the `allow_insecure` checkbox to the user step (shown after the first failure), (b) a dedicated error `basic_auth_needs_opt_in` telling the user to finish setup via Reconfigure, (c) keep Basic over unverified HTTPS but log a WARNING on every fallback (not recommended: the password still leaks). Recommended: (a).

**Evidence.** `tests/test_api.py::test_basic_retry_requires_https_or_explicit_opt_in` (case https / no opt-in / Basic → retry=True) and `test_basic_auth_permitted_over_https` document the current behaviour and must be updated. Observed by code reading only; not reproduced against a device.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 With protocol https, verify_ssl False and allow_insecure False, a 401 Basic challenge is not answered with Basic credentials: the 401 is surfaced as TwoNAuthenticationError and one WARNING names the reason without any credential in the log [unit]
- [ ] #2 With protocol https and verify_ssl True the Basic fallback keeps working exactly as today [unit]
- [ ] #3 With verify_ssl False and allow_insecure True, Basic is sent (explicit opt-in), the same rule as over plaintext HTTP today [unit]
- [ ] #4 Digest authentication is unaffected in every protocol/verify_ssl/allow_insecure combination [unit]
- [ ] #5 The allow_insecure description in strings.json and en/cs/de translations says it also covers HTTPS with an unverified certificate; test_translations stays green [unit]
- [ ] #6 Initial setup against a device that offers only Basic over a self-signed certificate ends with a clear error pointing to the opt-in, not a generic cannot_connect — exact UX per the decision recorded in this task [unit]
- [ ] #7 README and INSTALLATION explain the rule: Basic auth only over verified HTTPS, or with the explicit opt-in [unit]
- [ ] #8 Full unit suite, validate.py and py_compile green; PR check e2e-pi green [e2e]
- [ ] #9 Jan verifies on the E2E intercom (HTTPS, self-signed certificate, Digest accounts) that setup and runtime work without the opt-in [jan]
<!-- AC:END -->
