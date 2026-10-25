# Changelog

## 1.5.1 - 2026-10-25

### Fixes

- Fixed log subscriptions on devices that do not support every event, such as the 2N IP Uni. Unsupported events no longer prevent the subscription from starting, restoring doorbell ring detection on affected devices ([#105](https://github.com/mastalir1980/ha-2N-intercom/issues/105)).

## 1.5.0 - 2026-10-23

### Security - Breaking change

HTTP Basic authentication now requires HTTPS with certificate verification enabled. HTTPS with an unverified or factory self-signed certificate is treated as insecure, just like plaintext HTTP: Basic credentials are not sent unless Allow insecure connection is explicitly enabled in Reconfigure. Existing installations using Basic over unverified HTTPS will stop connecting until corrected. Prefer switching the device HTTP API services to Digest, or installing a certificate Home Assistant trusts and enabling certificate verification in Reconfigure. Initial setup has no insecure opt-in. Existing entries show a warning, a Repair issue and a dedicated reauthentication error; users who explicitly accept the password-exposure risk can enable Reconfigure > Allow insecure connection. Digest authentication is unchanged.

This supersedes the 1.4.0 rule that "Basic stays enabled over HTTPS": that rule no longer applies to HTTPS without certificate verification. Saved connection settings are not changed automatically.

- Automatic IP-address updates now verify the intercom's identity at the new address before changing the saved host. Verification never sends Basic credentials over HTTP or unverified HTTPS, even with the insecure opt-in; those devices need Digest for automatic address updates, or a manual change through Reconfigure.
- Downloaded diagnostics now redact device serial numbers, MAC addresses, SIP identities, call peers and access-event user identities, including identifiers embedded in entry titles and saved device names. Review remaining connection details and custom names before sharing.

### Features

- **Doorbell event entity and HomeKit auto-linking:** `event.<intercom>_doorbell` emits one `ring` event per intercom-started ring, with called peer and caller details when available. HomeKit automatically links it to the camera on the same device; include only the camera in an Accessory-mode bridge.
- **Breaking doorbell migration:** the doorbell binary sensor and its registry entry are removed automatically, without a deprecation period. Update automations, blueprint inputs and explicit HomeKit `linked_doorbell_sensor` references to the event entity. Trigger on a new timestamp with `event_type: ring`, not an `on` state; ignore startup, restore and unavailable transitions. Recreate an existing ordinary-camera HomeKit pairing as a video doorbell if needed. See the [migration guide](README.md#doorbell-migration-in-v150-breaking-change) and [HomeKit guide](HOMEKIT_INTEGRATION.md).
- **Last-ring image:** `image.<intercom>_last_ring` keeps the JPEG captured when the doorbell rings. It is created when the camera is enabled; a failed capture keeps the previous image.
- **Audited access control:** the new `2n_intercom.grant_access` service opens entry/exit access points on behalf of a directory user, applying their access rights and recording access in the device log. Pass a user UUID or choose the default **grant-access user** in Configure's Device step. Device denials are reported as errors rather than success.
- **Access-control events:** supported card, PIN, mobile-key, fingerprint and access-result events are read from the log channel. The latest event is available in diagnostics with user identities redacted; card numbers, PINs and mobile-key IDs are never stored.
- **Extended I/O inputs:** every reported input gets a binary sensor, including extension-module and tamper ports. Inputs are enabled by default; the existing built-in input entity keeps its identity.
- **Direct I/O output switches:** physical outputs, except `led_secured`, are available as switches that are **disabled by default** and require **I/O - Control** permission. They are **latching**, not timed pulses: direct relay control bypasses logical switch timing and can leave a door **unlocked until the output is turned off**. Prefer the existing logical relay switch/cover for normal timed opening.
- **Automatic discovery:** 2N and Control4 DS2 / DS2 Mini devices advertising SSDP appear in Home Assistant's Discovered list. Existing entries follow verified IP-address changes without losing their identity.
- **Firmware availability:** a Firmware update entity shows installed/latest versions and release notes on devices reporting `firmwarePackage` (firmware 3.x). Choose **Firmware channel** in Configure: Active track (default), LTS or Beta. Checks run at setup and every six hours against the public 2N server without device credentials. Installation remains in the device web UI; there is no Install button and device AutoUpdate settings are not changed.

### Fixes

- Calls into the intercom from My2N, Control4 or a SIP phone no longer ring the doorbell. Only intercom-started calls ring, even with **All calls** selected.
- The Called ID filter now matches any peer in a parallel/group call, rather than only the last peer seen. A selected peer's `/suffix`, such as `1234567890/2`, no longer prevents a match.
- Snapshots now use a supported size from `camera/caps`: the smallest size covering both requested dimensions, or the largest available. This avoids repeated resolution errors and unnecessary retries at 640x480.
- Configure now shows directory names instead of raw UUIDs for the default grant-access user, including the selected value. Unknown saved users remain selectable; a directory failure preserves the selection and shows a warning.
- Saving options preserves saved relay names, door/gate types and pulse durations when relays are absent or cannot be detected.
- Setup and Configure use **Next** on intermediate steps and **Submit** to save the final step. The unreliable back-navigation checkbox is removed; close and restart the dialog to change an earlier step. Unsaved drafts are discarded.
- Transient authentication failures refresh the Digest session before requesting credentials again; three consecutive failed poll updates trigger reauthentication. Startup retries no longer loop indefinitely on invalid credentials, and recovery preserves Home Assistant's shared HTTP connection.
- Empty log pulls no longer cause a busy loop on firmware that returns immediately. Coordinator timestamps are now timezone-aware.

### Docs

- Expanded the [README](README.md) and [installation guide](INSTALLATION.md) for the new entities, options, services and upgrade steps, including event-based doorbell automations and HomeKit setup.
- Documented Control4 DS2 / DS2 Mini compatibility and where owners can obtain HTTP API credentials.
- Listed the HTTP API account privileges required by each feature, including **System - Control** for directory queries and **Access Control - Control** for `grant_access`.
- Clarified that relays must first be enabled in the intercom settings before Home Assistant can discover them, and that HTTP API credentials belong in **Reconfigure**, separately from camera RTSP credentials.

## 1.4.0 - 2026-10-11

### Security — secure-by-default connection
- Config-flow auto-detect now prefers a **verified TLS** connection: it tries `HTTPS:443` with certificate verification first, then unverified HTTPS (self-signed 2N cert), and only then plaintext `HTTP:80`. Users with a valid/own-CA certificate get a verified connection instead of being pinned to `verify_ssl=False` (S1).
- Plaintext **HTTP is now the last-resort** candidate and logs a `WARNING` when a connection settles on it (S2).
- The **HTTP Basic-auth fallback is refused over plaintext HTTP** so credentials are never sent in cleartext; it stays enabled over HTTPS and behind a new opt-in `allow_insecure` flag for devices that genuinely need it. Digest auth is unaffected (S3).
- New `allow_insecure` toggle exposed in the reconfigure flow (default off), stored in entry options and respected by runtime requests, reauthentication, and directory lookups; EN/CS/DE translations added for the reconfigure step.
- Existing connections are not automatically migrated. Reconfigure HTTP entries to HTTPS where possible; existing HTTP Basic users must explicitly opt in if HTTPS or Digest cannot be used.

## 1.3.1 - 2026-04-12

### Documentation sync and quality scale
- Updated README.md, INSTALLATION.md, IMPLEMENTATION_SUMMARY.md, and validate.py to reflect the event-driven subscription model (ring detection is exclusively event-driven with no polling fallback, backup polling is a low-frequency safety net at 60 s default)
- `quality_scale.yaml`: strict-typing marked `done` (mypy strict clean, pyright clean with framework-level suppressions via `pyrightconfig.json`)
- Added `pyrightconfig.json` to suppress HA-framework-level pyright false positives (`cached_property` override, stub fallback typing) that affect all HA integrations equally
- Stripped vestigial polling ring-detection code from `_async_update_data` — baseline state capture retained for event handlers
- Adopted HA `_attr_*` pattern for all static entity properties, fixing pyright `reportIncompatibleVariableOverride` errors

## 1.3.0 - 2026-04-12

### Motion detection binary sensor
- New `binary_sensor.<intercom>_motion` entity with `device_class=motion`, driven by the device's `MotionDetected` log events (`state: "in"` = motion started, `"out"` = motion ended)
- Motion detection capability is auto-detected via `/api/system/caps` — the sensor is only created when `motionDetection` is `"active,licensed"` on the device
- The log subscription (`/api/log/subscribe`) now includes `MotionDetected` events alongside `CallStateChanged` / `CallSessionStateChanged` when motion detection is available
- `last_motion` timestamp exposed as extra state attribute
- System capabilities (`/api/system/caps`) fetched once during coordinator static cache initialisation
- Diagnostics output includes `system_caps` and `motion_detection` sections
- RTSP probe skipped entirely when `/api/system/caps` reports `rtspServer` as not `"active"` — avoids a TCP+Digest handshake timeout on devices without the RTSP license
- Translations updated (EN, CS) for the new entity

## 1.2.0 - 2026-04-12

### RTSP credentials as separate configuration
- The 2N RTSP server has its own user database, independent of the HTTP API accounts. RTSP credentials are now configured separately in the camera options step (`rtsp_username`, `rtsp_password`) with no fallback to HTTP API credentials
- RTSP probe upgraded from port-reachability check to full Digest authentication handshake (unauthenticated OPTIONS → 401 challenge → authenticated OPTIONS) — the integration no longer marks RTSP as "available" when credentials are wrong
- Special characters in RTSP credentials are URL-encoded in the stream URL
- Without RTSP credentials configured, the integration skips RTSP entirely and falls back to MJPEG
- RTSP credentials are redacted in diagnostics output
- Translations updated (EN, CS) with labels and descriptions for the new fields

## 1.1.0 - 2026-04-11

### HA 2026.4+ compliance
- Imported `homeassistant.components.persistent_notification` API (`hass.components.X` accessor was removed in HA 2025.1)
- `OptionsFlow` no longer stores `config_entry`; uses `self.config_entry` from the framework
- `DataUpdateCoordinator` constructed with the `config_entry` kwarg so HA tags traces with the entry
- Manifest: `requirements: []`, `iot_class: local_push`, `integration_type: device`
- HACS metadata bumped to `homeassistant: 2026.4.0`

### Camera
- Switched from `Camera + stream_source + ffmpeg` to `homeassistant.components.mjpeg.MjpegCamera`
- Credentials are passed to `MjpegCamera` separately and **never** appear in the URL exposed to logs, diagnostics, or dashboards
- Camera transport (RTSP / MJPEG / public-MJPEG) is resolved **once** at coordinator setup; the entity reads `coordinator.camera_transport_info` instead of probing on every property access

### Event handling and call lifecycle
- Push-driven log subscription via `/api/log/subscribe` + `/api/log/pull` + `/api/log/unsubscribe` with re-subscribe and exponential backoff (capped at ~60 s)
- Polling fallback through `/api/call/status` keeps ringing detection alive when the push channel is degraded
- New `2n_intercom.answer_call` and `2n_intercom.hangup_call` services with `target.config_entry` and a `reason` selector (`normal` / `rejected` / `busy`)
- `sensor.<intercom>_call_state` exposes an `active_session_id` attribute so automations can hang up the exact session they answered
- Hangup logic: only the firmware's idempotent `code 14 + "session not found"` response is treated as success — every other rejection (including `code 14 + "Unsupported Content-Type"`) is logged as a real failure
- Centralised device-error parsing across the entire client: any non-success response surfaces as a WARNING with `code` / `description` / `param`; only the idempotent hangup case stays at DEBUG

### Diagnostics and real-state entities
- `sensor.<intercom>_sip_registration` — derived from `/api/phone/status`
- `sensor.<intercom>_call_state` — exposes `active_session_id`
- `binary_sensor.<intercom>_input_1` — real `/api/io/status` input state
- `binary_sensor.<intercom>_relay_1_active` — real cached `/api/switch/status` relay state
- Lock fallback `is_locked` prefers cached `switch/status` for relay 1 and only falls back to optimistic state when `switch/caps` confirms relay 1 doesn't exist

### Configuration flows
- Reauth flow (`async_step_reauth`) — credential rejection raises `ConfigEntryAuthFailed` instead of looping on `ConfigEntryNotReady`
- Reconfigure flow (`async_step_reconfigure`) — change host/port/protocol/credentials/SSL without removing the entry (HA 2024.10+)

### Performance / KISS
- Static caps (`switch/caps`, `io/caps`, camera transport) fetched **once** at setup, not refetched per poll — only `switch/status`, `io/status`, `phone/status`, and the `call/status` fallback poll on the 5-second interval
- Shared `TwoNIntercomEntity` base class — `device_info`, `available`, and `_attr_has_entity_name` deduplicated across every platform
- Snapshot caching collapsed into a single layer at the coordinator
- Removed dead `PLATFORMS` constant; `_get_platforms()` now returns `Platform` enum members
- Dropped legacy `BinarySensorDeviceClass.DOORBELL` `getattr` fallback
- `services.yaml` gained per-service `target.config_entry` and a `reason` selector

## 1.0.1 - 2026-02-22

- Do not expose lock entity when relays are configured
- Read relay configuration from options for switch/cover entities

## 1.0.0 - 2026-02-20

- Initial public release
- Camera platform with RTSP H.264 streaming and snapshots
- Doorbell binary sensor with ring detection
- Switch platform for door relays
- Cover platform for gate relays
- Multi-step config flow and options flow
- HomeKit bridge support
- Ringing account filter based on directory peers
- Gate/door lock type inferred from relay configuration
