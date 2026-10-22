---
id: TASK-67
title: >-
  Basic-auth fallback sends the API password to any HTTPS host when the
  certificate is not verified (verify_ssl=False)
status: In Progress
assignee:
  - '@copilot'
created_date: '2026-10-21T09:44:00Z'
updated_date: '2026-10-21 14:16'
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
1. Add TwoNInsecureAuthRefusedError and permit Basic only for verified HTTPS or the existing explicit allow_insecure option; preserve Digest, RTSP and retry mechanics.
2. Surface basic_auth_refused through setup, reauth and reconfigure without adding a setup opt-in.
3. Create a translated warning Repair issue on runtime refusal, retaining three-strike reauth, and remove it after recovery or unload.
4. Update en/cs/de strings and connection-security documentation; add API matrix, flow and Repair lifecycle regression coverage.
5. Run the required local Python gates, record evidence and the Security breaking-change release note for TASK-37, and commit locally without ticking criteria or finalizing status. e2e-pi and Jan verification remain external gates.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented verified-HTTPS-or-explicit-opt-in Basic policy with dedicated refusal propagation; setup/reauth/reconfigure errors; translated per-entry Repair issue creation, recovery and unload cleanup; en/cs/de texts and user security/upgrade documentation. Added full protocol/verify_ssl/allow_insecure Basic and Digest matrices, flow refusal/opt-in coverage, and Repair lifecycle/three-strike reauth coverage. Targeted suites are green. Secondary endpoint refusals must bypass cached-data degradation so they reach Repair/reauth handling; ensuring startup cache loading still defers authentication retries to first refresh.

Local gates passed on Python 3.12: full unittest discovery (719 tests), validate.py and py_compile for all integration modules. No E2E command or device interaction was run; e2e-pi must run after the orchestrator pushes. Metadata/event cache refreshes keep intentional graceful degradation but create the Repair issue on a dedicated refusal; polling propagates that refusal into the unchanged three-strike reauth path. A startup regression proves one static switch-capability refusal plus three first-refresh attempts, without aborting setup prematurely. HTTP remains insecure even if verify_ssl=True is supplied; only verified HTTPS or the explicit opt-in permits Basic. No RTSP, SSDP, version, changelog or protected-path changes.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented verified-HTTPS-only automatic Basic fallback, with the existing allow_insecure option required for both plaintext HTTP and unverified HTTPS. Dedicated config errors and translated per-entry Repair guidance explain the device-side fixes and existing-entry opt-in. Digest and the three-strike reauth policy are preserved. Task remains In Progress with all criteria unchecked for the orchestrator.

AC #1: tests/test_api.py AuthenticationRequestTests.test_basic_retry_requires_verified_https_or_explicit_opt_in proves the dedicated authentication subclass, one credential-free WARNING and no retry on insecure transports.
AC #2: The same complete matrix proves verified HTTPS still performs the Basic retry.
AC #3: The same matrix proves the explicit opt-in permits Basic on HTTP and unverified HTTPS; config-flow opt-in tests prove it stays in entry.options.
AC #4: AuthenticationRequestTests.test_digest_path_is_unaffected_for_every_transport_combination covers both success and unresolved Digest challenges for all eight combinations, with preemptive=False middleware and no Basic retry.
AC #5: ConfigFlowTests.test_user_step_remembers_basic_refusal_across_candidates proves the dedicated setup error, candidate order, resource cleanup and unchanged three-field user form. TranslationConsistencyTests verifies the device-side instructions.
AC #6: ConfigFlowTests.test_reauth_basic_refusal_is_not_invalid_credentials proves the dedicated reauth error without entry updates; translated error text points to Reconfigure > Allow insecure connection.
AC #7: Coordinator Repair lifecycle tests prove one stable warning issue per entry, not fixable, translated entry-title placeholder, recovery cleanup and unchanged three-strike reauth. Setup tests prove startup behavior, unload cleanup and retention when unload fails.
AC #8: tests/test_translations.py passes for strings.json and en/cs/de, including the new error, Repair placeholders and the description of both insecure transports.
AC #9: README Authentication, INSTALLATION Basic authentication blocked / upgrading existing installations, and docs/IMPROVEMENTS.md S3 now document the rule, device-side remedies and upgrade migration.
AC #10: Copy-ready TASK-37 release note appears below. No CHANGELOG or manifest version was changed.
AC #11: Local full suite passed (719 tests), validate.py and integration py_compile passed. PR check e2e-pi is pending; it cannot be run on this VM. Existing e2e/tests/test_00_setup.py and test_20_lifecycle.py cover staging entry loading and reload.
AC #12: Manual verification by Jan remains pending: self-signed HTTPS with Digest must work through setup, reauth and runtime without opt-in; temporarily selecting Basic must show the dedicated error and Repair issue.

## Release note for TASK-37 / v1.5.0

### Security - Breaking change

HTTP Basic authentication now requires HTTPS with certificate verification enabled. HTTPS with an unverified or factory self-signed certificate is treated as insecure, just like plaintext HTTP: Basic credentials are not sent unless Allow insecure connection is explicitly enabled in Reconfigure. Existing installations using Basic over unverified HTTPS will stop connecting until corrected. Prefer switching the device HTTP API services to Digest, or installing a certificate Home Assistant trusts and enabling certificate verification in Reconfigure. Initial setup has no insecure opt-in. Existing entries show a warning, a Repair issue and a dedicated reauthentication error; users who explicitly accept the password-exposure risk can enable Reconfigure > Allow insecure connection. Digest authentication is unchanged.
<!-- SECTION:FINAL_SUMMARY:END -->
