---
id: TASK-69
title: >-
  Diagnostics expose the device serial number, MAC and SIP identities
  (system_info, phone_status, entry serial_number, title)
status: To Do
assignee:
  - '@copilot'
created_date: '2026-10-21T09:44:00Z'
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
- [ ] #1 entry.data.serial_number is redacted, and entry.title is redacted when it contains the serial number [unit]
- [ ] #2 device.system_info serialNumber and macAddr are redacted; variant, swVersion, hwVersion and firmwarePackage stay readable [unit]
- [ ] #3 device.phone_status SIP identities (sipNumber and any account/registrar identity field present in the payload) are redacted; registration state fields stay [unit]
- [ ] #4 call_state.called_peer and caller details are redacted [unit]
- [ ] #5 The diagnostics test fixture uses realistic /api/system/info and /api/phone/status payloads so redaction is proven on the real field names [unit]
- [ ] #6 The E2E check that reads the deployed entry diagnostics (test_60_discovery) still passes and additionally asserts the serial number is absent from the dump [e2e]
- [ ] #7 Full unit suite, validate.py and py_compile green; PR check e2e-pi green [e2e]
<!-- AC:END -->
