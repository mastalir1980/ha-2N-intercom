---
id: TASK-69
title: >-
  Diagnostics expose the device serial number, MAC and SIP identities
  (system_info, phone_status, entry serial_number, title)
status: Done
assignee:
  - '@copilot'
created_date: '2026-10-21T09:44:00Z'
updated_date: '2026-10-21 15:01'
labels:
  - security
  - bug
  - privacy
  - diagnostics
milestone: m-0
dependencies: []
references:
  - custom_components/2n_intercom/diagnostics.py
  - tests/test_diagnostics.py
  - e2e/tests/test_60_discovery.py
  - TASK-49
  - docs/SECURITY-REVIEW-v1.5.0.md
priority: medium
type: bug
ordinal: 74000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the security review before v1.5.0 (docs/SECURITY-REVIEW-v1.5.0.md, finding S-3).

**Current behaviour.** `diagnostics.py` redacts username, password, RTSP credentials, grant_access_user and `mac_address` in `entry.data` / `entry.options` (`TO_REDACT_ENTRY`, lines 185-192), but the same identifiers leave the dump unredacted elsewhere: `entry.data.serial_number` (`CONF_SERIAL_NUMBER` is not in `TO_REDACT_ENTRY`), `device.system_info` (`serialNumber`, `macAddr` exactly as `/api/system/info` reports them), `device.phone_status` (SIP account identities, e.g. `sipNumber`), `call_state.called_peer` (the SIP peer / phone number of the last call) and `entry.title` (the default name is "<variant> <serial>"). TASK-49 AC #6 redacted `mac_address` precisely because users attach diagnostics to public GitHub issues; the project rules treat serial numbers and MACs as private identifiers.

**Expected behaviour.** One redaction policy for the whole dump: serial number and MAC wherever they appear, SIP identities and call peers, and the entry title when it embeds the serial. Firmware/hardware versions, variant, capabilities, host and port stay — they are load-bearing for triage.

**Evidence.** `tests/test_diagnostics.py::test_diagnostics_redacts_entry_mac_address` proves only the entry-level MAC; the fixture's `system_info` is not asserted for redaction. Observed by code reading.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 entry.data.serial_number is redacted, and entry.title is redacted when it contains the serial number [unit]
- [x] #2 device.system_info serialNumber and macAddr are redacted; variant, swVersion, hwVersion and firmwarePackage stay readable [unit]
- [x] #3 device.phone_status SIP identities (sipNumber and any account/registrar identity field present in the payload) are redacted; registration state fields stay [unit]
- [x] #4 call_state.called_peer and caller details are redacted [unit]
- [x] #5 The diagnostics test fixture uses realistic /api/system/info and /api/phone/status payloads so redaction is proven on the real field names [unit]
- [x] #6 The E2E check that reads the deployed entry diagnostics (test_60_discovery) still passes and additionally asserts the serial number is absent from the dump [e2e]
- [x] #7 Full unit suite, validate.py and py_compile green; PR check e2e-pi green [e2e]
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Apply one recursive diagnostics key-redaction policy to entry credentials, serial/MAC identifiers, access identities and call peers; mask known device serial/MAC values in free-text fields including entry title/name without mutating cached data.
2. Redact phone/status identities recursively using an explicit allowlist of documented account indexes/types and registration-state fields so additional account/registrar identity fields cannot leak. Preserve firmware/hardware versions, variant, capabilities, host and port.
3. Replace minimal diagnostics fixtures with realistic system/info and phone/status result payloads; cover nested identities, title/name leaks, idle/empty payloads and source-data immutability.
4. Extend the read-only test_60_discovery diagnostics check to compare against the actual device serial and require its absence from the dump, retaining the MAC assertions. Update directly related README and architecture documentation.
5. Run the required local Python gates, record evidence in implementation notes without checking criteria or changing the final status, and commit TASK-69 locally. Leave live E2E to the orchestrator e2e-pi check.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented a single recursive diagnostics key-redaction policy plus case-insensitive masking of known device serial/MAC values in free text (including entry title, saved name and deviceName). Added called_id to the same peer policy so the configured filter cannot reveal the redacted call peer elsewhere. Caller details remain unexported. Phone status uses a non-identifying telemetry allowlist, preserving documented numeric account indexes, account types and registration state/time while masking unknown and nested account/registrar identity fields. Config entry data/options and coordinator caches are not mutated. Updated README and architecture documentation.

AC #1: test_diagnostics_redacts_serial_in_entry_and_free_text covers entry serial, title/data/options names, serial available from either entry or cached system_info, and custom titles without identifiers.
AC #2: test_diagnostics_redacts_system_identifiers_without_mutating_cache asserts real serialNumber/macAddr fields and nested entry aliases are redacted while variant, swVersion, hwVersion, firmwarePackage, buildType and capabilities remain readable. Existing credentials test preserves host/port.
AC #3: test_diagnostics_redacts_phone_identities_preserving_registration and test_diagnostics_redacts_textual_account_and_registrar_identities cover real sipNumber, additional/nested account and registrar identities, registration telemetry and numeric indexes.
AC #4: test_diagnostics_redacts_call_peers_and_omits_caller_details covers called_peer, configured called_id and absence of caller names/numbers; idle peers remain None.
AC #5: FakeCoordinator now supplies realistic system/info result fields and phone/status accounts with documented account/accountType/enabled/sipNumber/registrationEnabled/registered/registerTime fields, including local accounts with serial-bearing SIP identities.
AC #6: test_60_discovery retains its existing MAC checks and now requires the deployed entry serial to be redacted and the real API serial to be absent from the complete diagnostics JSON (case-insensitive). Offline unit checks exercise success, serial leaks in title/device data, an exposed entry serial and missing API serial, with identifier-free failure messages. Live proof remains pending e2e-pi; no HA/intercom access was attempted.
AC #7: On Python 3.12.15, python3 -m unittest discover -s tests -t tests passed all 723 tests; python3 validate.py, python3 -m py_compile custom_components/2n_intercom/*.py and git diff --check passed. The suite still emits warnings from existing API failure-path test doubles; these do not fail the suite. PR e2e-pi remains pending the orchestrator push.

Headless handoff: keep In Progress and all acceptance criteria unchecked for the independent review/orchestrator. No protected paths changed; no push or live E2E run.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented by the headless coder. Checks green on 10c3b2732 after 0 fix round(s): e2e-pi=pass, validate=pass, validate=pass. PR: https://github.com/mastalir1980/ha-2N-intercom/pull/101. Done takes effect when the PR is merged.
AC #1: tests/test_diagnostics.py::test_diagnostics_redacts_serial_in_entry_and_free_text (subtests entry/system_info/both/neither) asserts entry.data.serial_number is redacted and the title containing the serial is masked, while a custom title stays. diagnostics.py adds CONF_SERIAL_NUMBER to TO_REDACT_ENTRY and regex masking of free text. Test run: 13 diagnostics tests OK. (proven)
AC #2: test_diagnostics_redacts_system_identifiers_without_mutating_cache asserts system_info serialNumber/macAddr are redacted while variant, swVersion, hwVersion, firmwarePackage, buildType stay equal to the originals; the cache is not mutated. (proven)
AC #3: test_diagnostics_redacts_phone_identities_preserving_registration and test_diagnostics_redacts_textual_account_and_registrar_identities: sipNumber plus extra username/accountName/registrar/additionalIdentities fields are redacted via the _redact_phone_status allowlist; account, accountType, enabled, registered, registerTime, registrationState and state stay. (proven)
AC #4: test_diagnostics_redacts_call_peers_and_omits_caller_details asserts call_state.called_peer is redacted, the peer string is absent from the whole dump, and caller details are not present anywhere in it; the caller keys are also in TO_REDACT. (proven)
AC #5: FakeCoordinator in tests/test_diagnostics.py now uses realistic /api/system/info fields (variant, serialNumber, macAddr, swVersion, hwVersion, firmwarePackage, buildType, deviceName) and /api/phone/status accounts (account, accountType, enabled, sipNumber, registrationEnabled, registered, registerTime). The async_redact_data stub became recursive like HA's helper; no assertion was weakened (the old system_info equality assertion became a variant check because the fixture changed). (proven)
AC #6: e2e/tests/test_60_discovery.py::test_entry_diagnostics_contains_redacted_mac keeps the MAC assertions and now also asserts entry.data.serial_number is redacted and the real twon.system_info serialNumber is absent (case-insensitive) from the whole diagnostics JSON; it fails if the device serial is empty. Offline tests/test_e2e_discovery.py::DiagnosticsPrivacyCheckTests exercise pass/fail paths. The orchestrator reports e2e-pi green on this head. (proven)
AC #7: The orchestrator confirmed the full unit suite, validate.py, py_compile and the PR checks including e2e-pi green on this head. The diagnostics unit tests were rerun in the review: 13 OK. (proven)
<!-- SECTION:FINAL_SUMMARY:END -->
