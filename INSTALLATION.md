# Installation and Usage Guide

## Quick Start

### 1. Installation

Copy the integration into your Home Assistant `config/custom_components/`:

```bash
cd /config
mkdir -p custom_components
cp -r /path/to/ha-2N-intercom/custom_components/2n_intercom custom_components/
```

(Or install via HACS — see [README.md](README.md#installation).)

### 2. Restart Home Assistant

Restart HA to pick up the new integration.

### 3. Add the integration

1. **Settings → Devices & Services → + Add Integration**
2. Search for **2N Intercom**
3. Run the multi-step wizard

Intercoms announcing themselves over SSDP, including Control4 DS2 / DS2 Mini
units, also appear under **Settings > Devices & Services > Discovered**. Start
there to prefill the host and friendly name, then enter the HTTP API credentials.
Configured entries automatically follow IP address changes from announcements
matching the device's MAC address; manual setup remains available when discovery
cannot reach Home Assistant. This trusts the local network: prefer HTTPS with
certificate verification and keep untrusted devices off the intercom's network.

### 4. Configure

The wizard has two steps:

- **Connection** — host, username, password. Protocol (HTTPS/HTTP) and port (443/80) are auto-detected
- **Device** — display name, enable camera, enable doorbell, optional ringing account (peer)

**Control4 DS2 / DS2 Mini door stations:** the accounts are set up by the Control4 installer and owners usually don't know the passwords. Ask your dealer, or look them up in Control4 **Composer Pro** → the door station's driver → **Properties** → **Advanced**. See [README → Control4 DS2 / DS2 Mini door stations](README.md#control4-ds2--ds2-mini-door-stations).

Relays are auto-discovered from the device and configured later via the **Options** flow (Settings → Devices & Services → 2N Intercom → **Configure**).

Example:

```
Connection
  Host: 192.0.2.20
  Username: homeassistant
  Password: ****
  → auto-detects HTTPS:443

Device
  Name: Front Door
  Camera: yes
  Doorbell: yes
  Ringing account: All calls
```

### 5. Verify in Home Assistant

After setup you should see:

- `camera.<name>_camera` — JPEG snapshots and a native MJPEG live view (no ffmpeg)
- `image.<name>_last_ring` — JPEG captured at the last ring, when the camera is enabled; a failed capture keeps the previous image
- `event.<name>_doorbell` — one `ring` event per intercom-started ring
- `binary_sensor.<name>_input_1` — real device input state; existing identity is preserved on upgrade
- `binary_sensor.<name>_input_modul1_input1` — one sensor per additional input, including extension modules; actual ports depend on the device
- `binary_sensor.<name>_tamper_modul1_tamper` — tamper-class sensor for a reported tamper input port
- `binary_sensor.<name>_relay_1_active` — real cached relay state
- `sensor.<name>_sip_registration` — SIP registration diagnostic
- `sensor.<name>_call_state` — call state with `active_session_id` attribute
- `update.<name>_firmware` — installed/latest firmware and release notes, only when the device reports `firmwarePackage` (firmware 3.x)
- `switch.<name>_<relay_name>` for door-type relays (auto-discovered)
- `switch.<name>_output_relay1` — direct physical output switches, including extension modules, disabled by default; the status LED (`led_secured`) is excluded
- `cover.<name>_<relay_name>` for gate-type relays (after options flow override)

Input and output states come from device events with backup polling. Tamper
state comes from its IO input port, not a separate log-event sensor.

Relay entities appear only for relays enabled in the **intercom settings**; the integration cannot enable them, so if none appear, enable them there and reload the integration (see [No relay entities appear](#no-relay-entities-appear)).

**Direct IO output switches are latching, not timed pulses.** Enable only the
outputs you need in the entity settings. Turning on a physical relay bypasses
logical relay pulse timing and can leave a door **unlocked until explicitly
turned off**. Prefer logical relay switch/cover entities for timed door or gate
opening, even when both entities control the same hardware.

### 6. HomeKit (optional)

If you run the HA HomeKit Bridge, include only the camera in **Accessory** mode. HomeKit automatically links the doorbell event entity on the same device for video-doorbell behaviour and HomePod chimes. See [HOMEKIT_INTEGRATION.md](HOMEKIT_INTEGRATION.md) for UI setup and the optional explicit YAML link.

### 7. Using the entities

- **Camera** — open the camera card; the MJPEG live view starts directly without ffmpeg / HLS
- **Last-ring image** — use the image entity on dashboards or in notifications to show the visitor at ring time rather than the current camera view
- **Doorbell** — automate on a new timestamp of `event.<name>_doorbell` with `event_type: ring`, ignoring startup/restore and unavailable transitions (see [README automation examples](README.md#automation-examples)). The `sensor.<name>_call_state` entity carries the `active_session_id` attribute you'll need to terminate the same session
- **Door relay** — call `switch.turn_on` (the relay self-resets after the configured pulse duration)
- **Gate relay** — call `cover.open_cover` / `cover.close_cover`

Upgrading to v1.5.0 removes the old doorbell binary sensor and its registry entry
automatically, without a deprecation period. Update existing automations,
blueprint inputs and explicit HomeKit `linked_doorbell_sensor` links to the
doorbell event entity.

Only calls started by the intercom trigger the doorbell; calls into it from
My2N, Control4 or SIP phones do not. The optional **Ringing account (peer)**
(`called_id`) matches any peer called in the session, including parallel/group
calls. Matching ignores SIP formatting and the suffix after `/`, so
`1234567890/2` matches `1234567890`; **All calls** accepts every button.

## Reconfiguring or Re-authenticating

The integration supports the modern HA flows:

- **Reconfigure** (HA 2024.10+) — Settings → Devices & Services → 2N Intercom → ⋮ → **Reconfigure**. Update host, port, protocol, credentials, TLS verification, or the insecure HTTP Basic opt-in without removing the entry. Automations stay attached.
- **Reauth** — when the device starts rejecting credentials the integration raises `ConfigEntryAuthFailed`, and HA shows a notification asking the user to re-enter the password. Click it to walk through the reauth flow.

For per-relay or device-feature changes, use the regular **Configure** (Options) button on the integration card.

Both the setup wizard and **Configure** only move forward. Intermediate steps show **Next**; the last step shows **Submit** and saves the draft. To change values from an earlier step, close the dialog and start again; closing discards unsaved changes. HTTP API credentials are changed only in **⋮ → Reconfigure**; the RTSP username/password in the camera options belong to a separate streaming account.

### New Device options in v1.5.0

| Option | Default | Purpose |
|---|---|---|
| **Firmware channel** (`firmware_channel`) | Active track (`active_track`) | Choose Active track, LTS (`lts`) or Beta (`beta`) for firmware availability checks; does not change the device's AutoUpdate settings |
| **Default user for grant access** (`grant_access_user`) | Empty | Directory user used by `2n_intercom.grant_access` when a call omits `user`; clear the selection to require a user in each call |

The default grant-access user is shown by directory name rather than UUID.
If the directory cannot be loaded, Configure shows a warning and preserves the
saved selection. Saved relay overrides (name, door/gate type and pulse duration)
also survive when relays are not detected or the integration is not loaded.

### Firmware availability

The firmware entity checks the public 2N update server at setup and every
**six hours**, separately from local status polling. Call
`homeassistant.update_entity` on `update.<name>_firmware` for an immediate check.
It sends only the firmware package, installed version and release-note language
(`en`), never device credentials. A failed check keeps the last known result.

Open the entity's release link or the device's configuration link to install
firmware in the **device web UI**. There is no Install button in Home Assistant:
the integration never downloads, uploads, applies or triggers device firmware.

## Services

| Service | Purpose |
|---|---|
| `2n_intercom.answer_call` | Answer the active call session (or a specific `session_id`) |
| `2n_intercom.hangup_call` | Hang up the active call session (or a specific `session_id`) with optional `reason` (`normal` / `rejected` / `busy`) |
| `2n_intercom.grant_access` | Open an access point (`access_point`: `0` = entry, default; `1` = exit) on behalf of a directory `user` (UUID) |

All services act on a loaded config entry. With one intercom loaded, it is
selected automatically; with multiple intercoms, supply `config_entry_id` in
the service data or the matching UI field.

Recommended pattern: pair `hangup_call` with the call-state sensor's `active_session_id` attribute so an automation only ends the session it actually answered.

```yaml
- service: 2n_intercom.hangup_call
  data:
    config_entry_id: <entry_id>
    session_id: "{{ state_attr('sensor.front_door_call_state', 'active_session_id') }}"
    reason: normal
```

### Grant access and access-control events

Unlike direct relay control, `2n_intercom.grant_access` applies the directory
user's access rights and records the attempt in the device access log
(`ApiAccessRequested`). Pass `user` as a UUID or select the default
`grant_access_user` in Configure. Missing users, missing permissions, disabled
access points and denied access raise an error, including the device's denial
reason when available.

```yaml
- service: 2n_intercom.grant_access
  data:
    config_entry_id: <entry_id>
    access_point: 0
    user: "01234567-89AB-CDEF-0123-456789ABCDEF"
```

The HTTP API account needs **Access Control - Control** in the API Access
Control service group, separate from relay permissions. Directory lookups need
**System - Control**, which also permits broader system configuration changes;
grant it only if you accept that permission. Direct IO outputs require
**I/O - Control**. See the [HTTP API account privilege table](README.md#http-api-account-privileges)
for the complete list.

Supported access-control events (card, PIN, mobile key, fingerprint and access
decisions) are subscribed via the device log channel. The latest event, with
access point, granted/denied result and directory-resolved user name when known,
appears in integration diagnostics; card numbers, PIN codes and mobile-key IDs
are never stored. Unsupported events do not break the subscription.

## Troubleshooting

### Integration not appearing
- Files must live in `config/custom_components/2n_intercom/`
- Restart HA, check logs for import errors

### Setup fails with "Cannot Connect"
- Verify host/port and enable HTTPS on the device. Setup tries verified HTTPS first, unverified HTTPS for self-signed certificates second, and plaintext HTTP last. Existing entries keep their saved protocol until reconfigured.
- The 2N HTTP API exposes a **per-service-group** auth setting in the device web UI under **Services → HTTP API**. Each service group (Camera, Switch, I/O, Phone, Call, Log) can be set to None, Basic, or Digest independently. The integration handles whatever combination the operator has chosen, but the configured username/password must be valid for **every** group it talks to

### Reauth notification keeps reappearing
- Credentials really are wrong, or the account is locked on the device. Clear it via the 2N web UI, then complete the reauth flow
- If a service requires Basic auth over HTTP, switch to HTTPS or configure Digest on the device. Only if neither is possible, enable **Allow insecure connection** in **Reconfigure** to permit sending credentials over plaintext HTTP.

### Camera entity exists but has no live view
- Open the entity attributes — `live_view_selected_mode` should be `mjpeg` (or `rtsp`), and `mjpeg_available` should be `true`
- If the device's RTSP licence isn't enabled, MJPEG is the only path. The integration prefers MJPEG automatically when RTSP is unreachable
- Reload the integration after changing camera caps on the device

### Doorbell event not firing
- Ring detection is exclusively event-driven via `/api/log/subscribe` — there is no polling fallback for ring events. Subscription failures are retried with exponential backoff; ring events during a gap are lost
- Check the integration log; a `Log subscription … established` debug line confirms the event channel is up

### No relay entities appear

Only relays enabled in the **intercom settings** are reported by `/api/switch/caps` and get entities in Home Assistant. Enable the relay (switch) in the intercom settings using the intercom's web interface, then reload the integration from **Settings → Devices & Services → 2N Intercom → ⋮ → Reload**. The integration cannot enable relays itself.

### Relay not actuating
- Verify the relay number matches the physical hardware (1-4)
- Test the same `switch/ctrl` call from `curl` against the device
- The relay-active binary sensor reflects real device state — if it doesn't toggle, the device itself isn't switching
- On Control4 DS2 / DS2 Mini units the lock or gate may be wired to Control4 hardware instead of the 2N relay; then the 2N relay can switch while nothing physical happens. See [README → Known Limitations](README.md#known-limitations)

## Multiple instances

Add the integration multiple times to drive several intercoms — each entry has its own coordinator, services target, and entities.

## Development Status

Implemented:

- Connection / device config flow + reauth + reconfigure + options flow
- Native MJPEG live view (no ffmpeg) and RTSP fallback
- SSDP discovery and automatic host updates after IP address changes
- Event-driven state updates (ring, switch, IO, phone, config) with backup polling safety net
- Doorbell event entity, last-ring image and access-control event diagnostics
- Diagnostic sensors (SIP registration, call state)
- Real cached relay/input/output state, including extension-module and tamper inputs
- `answer_call` / `hangup_call` / `grant_access` services
- Auto-discovered switch / cover entities for relays
- Disabled-by-default latching switches for direct IO outputs
- Firmware availability and release notes with selectable update channel
- HomeKit bridge mapping
- Full HA 2026.4+ compliance

Downstream HA automations (mobile actionable notifications, KNX door opening, etc.) consume the entities and services above; they're not part of the fork itself.

## Support

Open an issue on the GitHub repository.
