# ha-2N-intercom

Home Assistant custom integration for 2N IP Intercom systems with camera, doorbell, relay, call control, and HomeKit support.

## Supported Devices

| Device | Firmware | Status | Notes |
|---|---|---|---|
| **2N IP Verso** | 2.50.0.76.2 | **Verified** | Tested with and without RTSP license. Primary development target. |
| **2N IP Verso 2.0** | 2.50.x | **Expected to work** | Same API as Verso; untested in this fork |
| **2N IP Solo** | 2.50.x | **Expected to work** | Single-button variant; same HTTP API family |
| **2N IP Base** | 2.50.x | **Expected to work** | Same HTTP API family |
| **2N IP Style** | 2.50.x | **Expected to work** | Same HTTP API family |
| **2N IP Force** | 2.50.x | **Expected to work** | Same HTTP API family |
| **2N IP Safety** | 2.50.x | **Untested** | Same API but may lack camera |
| **2N IP Audio** | 2.50.x | **Untested** | No camera module |
| **Control4 DS2 Door Station** | — | **Community-reported** | Rebranded 2N IP Verso. Credentials are set by the Control4 installer, see [Control4 DS2 / DS2 Mini](#control4-ds2--ds2-mini-door-stations) |
| **Control4 DS2 Mini Door Station** | — | **Community-reported** | Rebranded 2N IP Solo. Same as the DS2 |
| Older 2N devices | < 2.40 | **Not supported** | Different API surface |
| Non-2N intercoms | — | **Not supported** | 2N HTTP API only |

"Expected to work" means the device uses the same `/api/` HTTP API family as the verified target and should function correctly, but has not been tested by the maintainers. If you run one of these devices and can confirm or deny, please open an issue.

## Features

### Camera
- **JPEG snapshot** via `/api/camera/snapshot`
- **Native MJPEG live view** via `/api/camera/snapshot?...&fps=<n>` — served through Home Assistant's `MjpegCamera`, no ffmpeg/HLS round-trip
- **RTSP stream source** when the device exposes it — requires separate RTSP credentials configured in the options flow (the 2N RTSP server has its own user database independent of the HTTP API accounts)
- **Credentials are passed to `MjpegCamera` separately** — they never appear in the URL exposed to logs, diagnostics, or dashboards
- **Last-ring image** (`image.<intercom>_last_ring`) — a JPEG captured from the configured camera source the moment the doorbell rings, so you can see who rang even after they left. A failed capture keeps the previous image. Created only when the camera is enabled
- HomeKit-compatible video doorbell

### Doorbell and call lifecycle
- **Event-driven ring detection** via `/api/log/subscribe` + `/api/log/pull` background loop with automatic re-subscribe and exponential backoff
- Only calls started by the intercom trigger the doorbell (for example, a visitor button press); calls into the intercom from My2N, Control4, or a SIP phone do not
- **Event-driven state updates** for switches, IO, SIP registration, and device config changes via the same subscription channel
- Binary sensor with caller name/number/button attributes
- **`2n_intercom.answer_call`** and **`2n_intercom.hangup_call`** services that target a config entry and (optionally) a specific session id, with `reason` selector (`normal`/`rejected`/`busy`)
- Diagnostic sensors: SIP registration status, call state with `active_session_id` attribute

### Access control
- **`2n_intercom.grant_access`** service — opens an access point through the device's access control on behalf of a directory user (see [Services](#services))
- **Access-control events** (card, PIN code, mobile key, fingerprint, authenticated/rejected user, access taken/blocked/limited, API access) are subscribed via the log channel — only those the device lists in `/api/log/caps`. The latest event (type, credential, access point, granted/denied, user name resolved from the directory) is kept by the coordinator and shown in diagnostics. Card numbers, PIN codes and mobile-key ids are never stored

### Door / Gate / Relay control
- **Switch** entities for door relays (momentary)
- **Cover** entities for gate relays (garage-door style)
- Relays auto-discovered from `/api/switch/caps` — configurable pulse duration and per-relay name via options flow
- Relay/input states are read from the device (`switch/status`, `io/status`), not optimistic
- HomeKit accessory mapping per relay type

### Configuration
- UI-driven two-step setup (connection → device). Auto-detection tries verified HTTPS:443, then unverified HTTPS for self-signed certificates, and finally HTTP:80 with a warning
- **Reauth flow** — when credentials are rejected the integration raises `ConfigEntryAuthFailed`, so HA opens a notification asking the user to re-enter credentials instead of looping on `ConfigEntryNotReady`
- **Reconfigure flow** — change host/port/protocol/credentials/SSL without removing the entry (HA 2024.10+)
- **Options flow** — device features, polling interval, camera transport, and per-relay overrides (name, type, pulse duration). Relays are auto-detected from the device
- Optional "Ringing account (peer)" filter for multi-button setups: matches any peer called in the current session, including parallel/group calls (`All calls` matches every button). Peer comparison ignores case, SIP/SIPS scheme, host, port and SIP parameters

## Capability Matrix

| Category | Status | Notes |
|---|---|---|
| **Done** | JPEG snapshot, native MJPEG live view, RTSP stream source (when licensed), event-driven ring/switch/IO/phone/config state, backup polling safety net, relay switch/cover control with real device state, SIP/call diagnostic sensors, answer/hangup/grant_access services, access-control events, last-ring image, reauth and reconfigure flows, HomeKit bridge mapping | All verified against 2N IP Verso 2.50.0.76.2 |
| **Out of fork scope** | Two-way audio, multi-tenant directory UX, keypad workflow, lift control, mass-notify | Not needed for a single-family-house deployment |
| **License-dependent** | Automation API, Audio Test, NFC, Noise Detection, SMTP, FTP, SNMP, TR069, Lift Control | Only available when the device license exposes them; not planned in this fork |

### Camera Support Baseline

Verified on a 2N IP Verso with firmware `2.50.0.76.2`:

- RTSP server license: `NO`
- JPEG snapshot works without `fps`
- MJPEG works via `/api/camera/snapshot?...&fps=<n>` over both HTTP and HTTPS
- Valid `fps` values are **`1..15`** (`fps >= 16` returns API error code `12`)
- Resolutions are taken from `camera/caps`. Observed values include
  `176x144`, `320x240`, `352x288`, `640x480`, `800x600`, `1280x960`, `160x120`, `352x272`, `480x272`, `1024x600`, `1280x720`, `640x360`

Helper: [`api.validate_mjpeg_fps`](custom_components/2n_intercom/api.py).

### Authentication

The 2N HTTP API exposes a **per-service-group** authentication setting in the device web UI under **Services → HTTP API**. Each service group (Camera, Switch, I/O, Phone, Call, Log, …) can be set to **None / Basic / Digest** independently, so a single account can end up answering some endpoint families with Basic and others with Digest depending on how the operator has configured the device.

The integration handles every combination transparently:

- The HTTP client uses `aiohttp`'s `DigestAuthMiddleware` (with `preemptive=False`) so it answers Digest challenges automatically.
- When the device answers a request with `401 + WWW-Authenticate: Basic`, the client retries with Basic auth over HTTPS. Basic over plaintext HTTP is refused unless **Allow insecure connection** (`allow_insecure`, default off) is enabled in **Reconfigure**. Digest authentication remains supported over both transports.

Prefer HTTPS with certificate verification. Factory self-signed certificates use encrypted HTTPS without identity verification; install a trusted certificate for protection against impersonation. The insecure opt-in permits sending recoverable credentials over plaintext HTTP and should be used only when HTTPS or Digest is unavailable.

Upgrading does not change saved connection settings. Reconfigure existing HTTP entries to HTTPS where possible. HTTP Basic users must either switch to HTTPS/Digest or explicitly enable the insecure opt-in.

An isolated authentication failure refreshes the Digest session without immediately
asking for credentials again. Three consecutive failed poll updates trigger reauth;
a successful update resets the counter. During startup, authentication retries
happen within the same setup attempt so an invalid stored password still triggers
reauth instead of leaving the integration in an endless setup-retry loop.
Session recovery preserves Home Assistant's shared HTTP connector.

The same username and password must work for every service group the integration touches. **Don't try to "simplify" `_async_request`** by hard-coding one scheme — the dual-auth path exists exactly because the device exposes the choice per service group.

#### Control4 DS2 / DS2 Mini door stations

The Control4 **DS2 Door Station** (rebranded 2N IP Verso) and **DS2 Mini Door Station** (rebranded IP Solo) use the same `/api/` HTTP API and the same 2N web UI. The difference is that the Control4 installer sets up the accounts (web UI admin and HTTP API user) during installation, and owners usually know neither password.

To get the HTTP API credentials:

- Ask your Control4 dealer for the door station's HTTP API username and password, or
- If you have access to **Composer Pro**: select the door station's driver, open its **Properties** tab and expand **Advanced**. The HTTP API username and password are shown there.

Once you can log in to the 2N web UI, the account is visible and manageable there like on any 2N device (**Services → HTTP API → Account**). Use those credentials, together with the door station's IP address, in the setup flow.

On Control4 installs some physical I/O (call button, relay outputs) may be wired into Control4's own hardware instead of being driven by the 2N board. See [Known Limitations](#known-limitations).

#### RTSP authentication

The 2N RTSP server has its **own user database**, completely independent of the HTTP API accounts. RTSP credentials are configured on the device under **Services → Streaming → RTSP Server → User Database**. There is no fallback from HTTP API credentials to RTSP credentials — they are separate systems.

The integration provides optional **RTSP username** and **RTSP password** fields in the camera options step (distinct from the HTTP API credentials, which live in setup / ⋮ → Reconfigure). The password field is masked and the stored password is never shown when the dialog is reopened — leave it empty to keep the stored password, or clear the username to remove the RTSP credential pair completely. When configured:

- The RTSP probe performs a full Digest authentication handshake (unauthenticated OPTIONS → 401 challenge → authenticated OPTIONS) to validate that the credentials actually work before marking RTSP as available.
- RTSP URLs embed the credentials for the HA stream worker (`rtsp://user:pass@host:554/h264_stream`). Special characters in credentials are URL-encoded.
- Without RTSP credentials, the integration will not attempt RTSP even if the device has a valid RTSP license — it falls back to MJPEG.

## Architecture

- **DataUpdateCoordinator** centralises polling, caching, and the background log listener
- **MJPEG-first camera** built on `homeassistant.components.mjpeg.MjpegCamera`
- **Event-driven + backup polling** — real-time state via log subscriptions; low-frequency polling (default 60 s) as a safety net
- **`TwoNIntercomEntity`** base class shared by all platforms — single source for `device_info`, `available`, and `_attr_has_entity_name`
- Platform-based: `camera`, `binary_sensor`, `switch`, `cover`, `sensor`

## Manual

- Install and setup: [INSTALLATION.md](INSTALLATION.md)
- HomeKit details: [HOMEKIT_INTEGRATION.md](HOMEKIT_INTEGRATION.md)
- Implementation overview: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
- Release notes: [CHANGELOG.md](CHANGELOG.md)

## Installation

### HACS (recommended)

1. Open HACS → Integrations
2. Three-dot menu → Custom repositories
3. Add `https://github.com/savek-cc/ha-2N-intercom` as an integration
4. Install **2N Intercom**
5. Restart Home Assistant

### Manual installation

1. Copy `custom_components/2n_intercom` into your HA `config/custom_components/`
2. Restart Home Assistant
3. Settings → Devices & Services → **+ Add Integration** → 2N Intercom

### Removing the integration

1. Settings → Devices & Services → 2N Intercom
2. Click the three-dot menu (⋮) on the integration card → **Delete**
3. Confirm the removal

All entities, devices, and automation references created by this integration are removed immediately. No restart is required. If you installed via HACS, you can also uninstall the repository entry from HACS → Integrations afterwards to stop receiving update notifications.

### Reconfiguring or re-authenticating

- **Reconfigure**: Settings → Devices & Services → 2N Intercom → ⋮ → **Reconfigure**. Lets you change host/port/protocol/credentials without removing the entry.
- **Reauth**: triggered automatically when the device starts rejecting credentials. HA shows a notification — click it to re-enter the password.

## Configuration

### Initial setup

The setup wizard has two steps:

1. **Connection** — host, username, password. Protocol (HTTPS/HTTP) and port (443/80) are auto-detected
2. **Device** — display name, enable camera, enable doorbell, optional ringing account (peer)

The wizard only moves forward. To change values from an earlier step, close the dialog and start again. Nothing is saved until you submit the Device step.

Relays are **not** configured during initial setup. The integration auto-discovers enabled relays from the device's `/api/switch/caps` endpoint and creates switch entities automatically. To override relay names, types (door/gate), or pulse durations, open the **Options** flow after setup.

### Initial setup parameters

| Step | Parameter | Type | Default | Description |
|---|---|---|---|---|
| Connection | `host` | string | *(required)* | IP address or hostname of the intercom |
| Connection | `username` | string | *(required)* | Device API username |
| Connection | `password` | string | *(required)* | Device API password |
| Device | `name` | string | *(auto-detected)* | Display name in Home Assistant |
| Device | `enable_camera` | bool | `true` | Create the camera entity |
| Device | `enable_doorbell` | bool | `true` | Create the doorbell binary sensor |
| Device | `called_id` | string | `All calls` | Ringing account / peer filter |

### Options flow parameters

After initial setup, open the integration's **Options** (Settings → Devices & Services → 2N Intercom → **Configure**) to change behavioral settings without removing the entry. The IP address, port and HTTP API credentials are **not** part of Configure — change them via **⋮ → Reconfigure** on the integration card (or the reauth prompt when credentials stop working).

The options flow has up to three steps:

1. **Device** — name, feature toggles, backup polling interval, ringing account, default grant-access user
2. **Camera** *(only when camera is enabled)* — live view mode, RTSP credentials, MJPEG resolution/fps, camera source
3. **Relay** *(one per auto-detected relay)* — name, device type (door/gate), pulse duration

Intermediate steps show **Next**; the last step shows **Submit**. The flow only moves forward: to change values from an earlier step, close the dialog and start again. Values entered in this session — camera settings and each relay's override — stay in the draft and are saved only when you submit the last step. Closing the dialog discards the draft.

| Step | Parameter | Type | Default | Description |
|---|---|---|---|---|
| Device | `name` | string | *(from setup)* | Display name |
| Device | `enable_camera` | bool | `true` | Toggle camera entity |
| Device | `enable_doorbell` | bool | `true` | Toggle doorbell entity |
| Device | `scan_interval` | 2-600 (s) | 60 | Backup polling interval. Events deliver real-time updates; polling only runs as a safety net |
| Device | `called_id` | string | `All calls` | Ringing account / peer filter |
| Device | `grant_access_user` | directory user (UUID) | *(empty)* | Default user for `2n_intercom.grant_access` when the call does not pass `user`. Picked from the device directory; a UUID can also be typed in |
| Camera | `live_view_mode` | `auto` \| `rtsp` \| `mjpeg` \| `jpeg_only` | `auto` | Camera live view transport. `auto` picks RTSP if licensed and RTSP credentials are set, then MJPEG, then snapshots |
| Camera | `rtsp_username` | string | *(empty)* | Optional. RTSP server username — created on the intercom under Services → Streaming → RTSP Server → User Database; the HTTP API account does **not** work here. Empty = RTSP is never tried, MJPEG is used |
| Camera | `rtsp_password` | string | *(empty)* | Optional. RTSP server password (masked field, never shown when the dialog is reopened — leave empty to keep the stored password; clear the username to remove the credential pair) |
| Camera | `camera_source` | `internal` \| `external` | `internal` | Which camera sensor to stream (external = secondary module) |
| Camera | `mjpeg_width` | 160-2592 (px) | 1280 | MJPEG stream width |
| Camera | `mjpeg_height` | 160-2592 (px) | 960 | MJPEG stream height |
| Camera | `mjpeg_fps` | 1-15 | 10 | MJPEG frame rate. Lower values reduce bandwidth |
| Relay | `relay_name` | string | `Relay N` | Display name for this relay |
| Relay | `relay_device_type` | `door` \| `gate` | `door` | Door → switch entity, Gate → cover entity |
| Relay | `relay_pulse_duration` | int (ms) | *(from device)* | How long the relay stays triggered. Default is the device's switchOnDuration |

For Called ID (`called_id`), the part after `/` is ignored when matching peers, so `1234567890/2` matches `1234567890`.

### Example: single-family house (door + gate)

```
Initial setup:
  Host: 192.0.2.20
  Username: homeassistant
  Password: ****
  → auto-detects HTTPS:443

  Name: Home Intercom
  Camera: yes
  Doorbell: yes

Options flow (after setup):
  Relay 1 → Front Door, door, 2000 ms
  Relay 2 → Driveway Gate, gate, 15000 ms
```

Resulting entities:

- `camera.home_intercom_camera`
- `image.home_intercom_last_ring` *(snapshot taken at the last ring)*
- `binary_sensor.home_intercom_doorbell`
- `binary_sensor.home_intercom_input_1` *(built-in input, existing entity preserved)*
- `binary_sensor.home_intercom_input_modul1_input1`, `binary_sensor.home_intercom_input_modul1_input2` *(one per additional input port; actual ports depend on the device and extension modules)*
- `binary_sensor.home_intercom_tamper_modul1_tamper` *(tamper input, when reported by the device)*
- `binary_sensor.home_intercom_relay_1_active` *(real cached relay state)*
- `sensor.home_intercom_sip_registration`
- `sensor.home_intercom_call_state` *(attribute: `active_session_id`)*
- `switch.home_intercom_front_door`
- `switch.home_intercom_output_relay1`, `switch.home_intercom_output_output1` *(physical outputs, disabled by default; actual ports depend on the device and extension modules)*
- `cover.home_intercom_driveway_gate`

### IO input sensors

Every port with type `input` in `/api/io/caps` and present in `/api/io/status`
gets a binary sensor, including extension-module inputs such as `modul1.input1`
and `modul1.input2`. Inputs are **enabled by default**. Their states come from
`InputChanged` events, with polling as a safety net. The existing `input1`
sensor keeps its identity and name on upgrade.

A port named `tamper` or ending in `.tamper` is exposed with the tamper device
class and the name "Tamper {port}". Its state comes directly from that IO port;
there is no separate tamper sensor driven by `TamperSwitchActivated` log events.

### Direct IO output switches

Each physical port with type `output` in `/api/io/caps` and present in
`/api/io/status` gets a switch, including module ports such as `modul1.relay1`.
The intercom's status LED (`led_secured`) is excluded. These switches are
**disabled by default**; enable only the outputs you need in the entity settings.
Their states come from `OutputChanged` events, with polling as a safety net.
They are **latching**, not pulses: turning an output on leaves it on until you
turn it off. There is no automatic turn-off timer.

**Warning: direct relay control bypasses the logical switch timing.** Turning
on a physical door relay such as `relay1` can leave the door **unlocked until
someone turns the output off**, even if the logical relay switch is configured
for a short pulse. A direct output switch is exposed even when a logical switch
or gate cover already controls that same relay. Prefer the existing logical
switch/cover for normal timed door or gate opening.

The API account must have the **I/O control privilege** in the intercom's
HTTP API settings. Without it, output control raises an error in Home Assistant;
the device rejection is also logged with its code and description.

## Services

| Service | Purpose |
|---|---|
| `2n_intercom.answer_call` | Answer the active call session (or a specific `session_id`) |
| `2n_intercom.hangup_call` | Hang up the active call session (or a specific `session_id`) with optional `reason` (`normal` / `rejected` / `busy`) |
| `2n_intercom.grant_access` | Open an access point (`access_point`: `0` = entry, default; `1` = exit) on behalf of a directory `user` (UUID) |

All services target a config entry. From the UI use the **Target → Integration** picker; from YAML use `data.config_entry_id`. Pair `hangup_call` with `sensor.<intercom>_call_state`'s `active_session_id` attribute to terminate the exact session that triggered an automation.

Example actionable-notification snippet:

```yaml
- service: 2n_intercom.hangup_call
  data:
    session_id: "{{ state_attr('sensor.home_intercom_call_state', 'active_session_id') }}"
    reason: normal
```

### Grant access vs. switch entities

`grant_access` calls `/api/accesspoint/grantaccess`. Unlike the relay switch/cover entities (which drive `/api/switch/ctrl` directly), the device treats it as a real access attempt: **the user's access rights apply** (time profiles, blocked access points) and **the access is recorded in the device's access log** under that user (`ApiAccessRequested`). Use it when you need an audit trail of who opened the door from Home Assistant.

Requirements:

- **User** — every call needs a directory user UUID: pass `user` in the call or set the default **grant-access user** in the options flow (Device step). Without either the service fails with a clear error.
- **Device privilege** — the HTTP API account needs the **Access Control - Control** privilege of the **API Access Control** service group (Services → HTTP API). This is separate from the Switch privilege used by the relay entities; without it the service reports that the account may not grant access.
- The access point must be enabled on the device.

The service never reports success when the door did not open: a denial (`accessGranted: false`, e.g. `invalidCredential`, `accessBlocked`, `invalidAp`) raises an error including the device's reason.

```yaml
- service: 2n_intercom.grant_access
  data:
    access_point: 0
    user: "01234567-89AB-CDEF-0123-456789ABCDEF"
```

## Automation Examples

### Blueprint: Doorbell notification with answer/hangup

A ready-to-use blueprint is included at [`blueprints/doorbell_notification_answer_hangup.yaml`](blueprints/doorbell_notification_answer_hangup.yaml). It sends a mobile notification with a camera snapshot and action buttons to answer or hang up the call when the doorbell rings.

To import:

1. Copy the YAML file into your `config/blueprints/automation/2n_intercom/` directory
2. Reload automations
3. Create a new automation from the blueprint and fill in your entities

### Quick YAML example: open door on doorbell

```yaml
automation:
  - alias: "Auto-open door on ring"
    trigger:
      - platform: state
        entity_id: binary_sensor.home_intercom_doorbell
        to: "on"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.home_intercom_relay_1
```

## 2N API Endpoints Used

The integration negotiates Basic vs Digest per request — see the **Authentication** section above.

| Endpoint | Purpose |
|---|---|
| `/api/system/info` | Device identity |
| `/api/call/status` | Baseline call state (safety-net poll) |
| `/api/call/answer`, `/api/call/hangup` | Service backends |
| `/api/log/caps` | Which log events the device supports (access-control subscription) |
| `/api/log/subscribe`, `/api/log/pull`, `/api/log/unsubscribe` | Push-driven event stream |
| `/api/dir/query` | Ringing-account peers, grant-access users, user names for access events |
| `/api/accesspoint/grantaccess` | `grant_access` service backend |
| `/api/switch/caps`, `/api/switch/status`, `/api/switch/ctrl` | Relay control + cached state |
| `/api/io/caps`, `/api/io/status` | Physical input/output discovery + cached state |
| `/api/io/ctrl` | Direct latching output control (requires I/O control privilege) |
| `/api/phone/status` | SIP registration sensor |
| `/api/camera/caps` | Discover MJPEG capability + resolutions |
| `/api/camera/snapshot` (with/without `fps`) | JPEG snapshot + MJPEG live view |
| RTSP stream | Optional, only when the device licence exposes it |

## Data Updates

The integration uses two data channels:

- **Event subscriptions (primary)** — `/api/log/subscribe` + `/api/log/pull` long-poll loop. Subscribes to `CallStateChanged`, `CallSessionStateChanged`, `SwitchStateChanged`, `InputChanged`, `OutputChanged`, `RegistrationStateChanged`, `ConfigurationChanged`, `CapabilitiesChanged`, `DeviceState`, (when available) `MotionDetected`, and the access-control events plus `DirectoryChanged` that the device lists in `/api/log/caps`. State changes arrive within ~1 second. The listener auto-resubscribes with exponential backoff on failures and forces a full baseline refresh after each reconnect
- **Backup polling (safety net)** — the coordinator polls status endpoints (`switch/status`, `io/status`, `phone/status`, `call/status`, `switch/caps`) at the configured interval (default 60 seconds). This catches any events missed during subscription gaps but does not perform ring detection — ring detection is exclusively event-driven
- **Static caps** — `switch/caps`, `io/caps`, and camera transport info are fetched once at setup and cached. Switch caps are also refreshed on `ConfigurationChanged` / `CapabilitiesChanged` events and on every poll cycle as a safety net

## Use Cases

- **Video doorbell** — camera snapshot + event-driven ring notification via mobile app
- **Door opening** — trigger relay via switch entity from automations, dashboards, or HomeKit
- **Gate control** — garage-door-style open/close via cover entity
- **Call management** — answer or reject incoming calls from automations using the `answer_call` / `hangup_call` services
- **Audited door opening** — open the door as a specific directory user with `grant_access`, so the access shows up in the device's access log
- **Multi-button setups** — filter doorbell events by ringing account (peer) to distinguish front door from side entrance
- **HomeKit bridge** — expose camera as video doorbell, relays as switches/garage doors in Apple Home

## Known Limitations

- **No two-way audio** — the HA camera platform does not support bi-directional audio; the doorbell ring triggers notifications but audio is device-side only
- **RTSP requires a separate license** — the 2N RTSP server is a paid feature; without it, only MJPEG streaming is available
- **RTSP credentials are independent** — the RTSP server has its own user database; HTTP API credentials do not work for RTSP
- **No gate position feedback** — the IP Verso has no gate-position sensor; cover entities use optimistic state transitions
- **Single camera source** — only one camera source (internal or external) can be active per config entry
- **Firmware < 2.40 unsupported** — older firmware versions use a different API surface
- **Control4 DS2 / DS2 Mini: relays may not switch** — on some Control4 installs a relay command succeeds at the API level (the station even shows the door-open icon) but nothing switches, because the lock or gate is wired to Control4 hardware rather than to the 2N relay. The 2N HTTP API cannot see or control that wiring ([#10](https://github.com/mastalir1980/ha-2N-intercom/issues/10))

## Troubleshooting

### Cannot Connect during setup
- Verify IP/port/credentials and protocol; firewall; SSL trust if HTTPS
- The same username and password must be valid for **both** Basic and Digest auth on the device — if the device rejects one of the schemes, every endpoint that uses it will fail. Configure the account under **Services → HTTP API → Account** on the 2N web UI

### Camera entity has no live view
- Confirm `camera/caps` returns `mjpeg.fps_min`/`fps_max` (the integration's transport probe runs once at setup; reload the entry after changing camera caps on the device)
- Open the entity attributes — `live_view_selected_mode` should be `mjpeg`, `mjpeg_available` should be `true`

### RTSP stream not working
- Make sure the RTSP server licence is enabled on the device
- Configure RTSP credentials in the integration's options flow (Settings → Devices & Services → 2N Intercom → Configure → Camera step). The RTSP server has its own user database — HTTP API credentials do **not** work for RTSP
- Create an RTSP user on the device: **Services → Streaming → RTSP Server → User Database**
- The entity attributes should show `rtsp_available: true` and `live_view_selected_mode: rtsp` when RTSP is working
- If RTSP credentials are wrong, the integration logs a warning and falls back to MJPEG

### Doorbell not triggering
- Ring detection is exclusively event-driven via the log subscription — there is no polling fallback for ring events
- Open the integration's diagnostics; the log subscription id should be set
- Press the button and watch HA logs — the event path should flip the binary sensor within ~1 s
- If a specific Called ID does not ring, enable debug logging for `custom_components.2n_intercom`. Every call event records its state, direction/originator, session, canonical peers, configured canonical filter (`all` for All calls) and decision (`rang`, `filtered by peer` or `not a ring`). Only intercom-started calls ring, even with `All calls`
- If the subscription is down, the listener retries with exponential backoff (up to ~60 s). Ring events during a subscription gap are lost

### Reauth notification keeps appearing
- Credentials really are wrong, or the device locked the account. Check the 2N web UI under **Services → HTTP API → Account** and re-enter the password through the reauth flow

## Development

### Project Structure

```
custom_components/2n_intercom/
├── __init__.py              # Integration setup, services, listener lifecycle
├── api.py                   # 2N API client (Basic + Digest auth)
├── coordinator.py           # DataUpdateCoordinator + push log loop
├── config_flow.py           # User / reauth / reconfigure / options flows
├── const.py                 # Constants
├── entity.py                # Shared TwoNIntercomEntity base
├── camera.py                # MjpegCamera-based camera platform
├── image.py                 # Last-ring snapshot image
├── binary_sensor.py         # Doorbell + input + relay-active sensors
├── sensor.py                # SIP registration + call state diagnostic sensors
├── switch.py                # Door relay platform
├── cover.py                 # Gate relay platform
├── manifest.json
├── services.yaml
├── strings.json
├── icons.json
└── translations/
    ├── en.json
    ├── de.json
    └── cs.json
```

### Tests

```bash
python3 -m unittest discover -s tests -t tests   # 442/442
python3 validate.py                               # manifest + HACS compliance
python3 -m py_compile custom_components/2n_intercom/*.py
```

## Version History

See [CHANGELOG.md](CHANGELOG.md) for the full release notes.

## License

See [LICENSE](LICENSE).

## Credits

Originally created by [mastalir1980](https://github.com/mastalir1980/ha-2N-intercom) for the Home Assistant community. The HA 2026.4+ remediation, MJPEG-first camera, push-driven event handling, real-state status entities, answer/hangup services, and dual-auth client live in this [savek-cc](https://github.com/savek-cc/ha-2N-intercom) fork.

## Support

Open an issue on the [savek-cc fork](https://github.com/savek-cc/ha-2N-intercom/issues).
