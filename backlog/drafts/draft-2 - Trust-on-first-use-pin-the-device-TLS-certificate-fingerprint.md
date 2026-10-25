---
id: DRAFT-2
title: 'Trust on first use: pin the device TLS certificate fingerprint'
status: Draft
assignee: []
created_date: '2026-10-24T08:29:00Z'
labels:
  - security
  - api
  - config-flow
  - needs-design
dependencies: []
references:
  - docs/SECURITY-REVIEW-v1.5.0.md
  - custom_components/2n_intercom/api.py
  - custom_components/2n_intercom/config_flow.py
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Why: security review before 1.5.0, observation O-1. Auto-detection settles on unverified HTTPS for the factory 2N certificate, which is the usual install, so the connection is encrypted but the server is not authenticated (MITM possible in the LAN). Since 1.5.0 (TASK-67) Basic auth is refused over unverified HTTPS, which broke Basic-only installs unless they opt in to allow_insecure. Pinning the certificate SHA-256 fingerprint at setup (aiohttp.Fingerprint) would authenticate the device without a custom CA, and could count as verified for the Basic rule.

Decided with Jan 2026-10-24: not in v1.6.0; target the version after it, after the design questions are answered.

Open design questions:
- Certificate change (firmware update, manual regeneration, factory reset): Repair issue with "accept the new fingerprint" flow? How does the user tell a legitimate change from an attack?
- Interaction with SSDP host update (TASK-68): pin follows the device identity, not the host.
- Migration of existing entries: pin on next successful connection, or only on Reconfigure?
- Does a pinned connection allow Basic without allow_insecure?
- RTSP (separate TLS? RTSP is plaintext on 2N) and the public MJPEG probe.
<!-- SECTION:DESCRIPTION:END -->
