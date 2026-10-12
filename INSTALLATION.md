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

### 4. Configure

The wizard has two steps:

- **Connection** — host, username, password. Protocol (HTTPS/HTTP) and port (443/80) are auto-detected
- **Device** — display name, enable camera, enable doorbell, optional ringing account (peer)

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
- `binary_sensor.<name>_doorbell` — event-driven ring detection
- `binary_sensor.<name>_input_1` — real device input state
- `binary_sensor.<name>_relay_1_active` — real cached relay state
- `sensor.<name>_sip_registration` — SIP registration diagnostic
- `sensor.<name>_call_state` — call state with `active_session_id` attribute
- `switch.<name>_<relay_name>` for door-type relays (auto-discovered)
- `cover.<name>_<relay_name>` for gate-type relays (after options flow override)

### 6. HomeKit (optional)

If you run the HA HomeKit Bridge, the camera entity exposes a HomeKit-compatible MJPEG stream and the doorbell binary sensor can be linked to it for video-doorbell behaviour. See [HOMEKIT_INTEGRATION.md](HOMEKIT_INTEGRATION.md) for the YAML link snippet.

### 7. Using the entities

- **Camera** — open the camera card; the MJPEG live view starts directly without ffmpeg / HLS
- **Doorbell** — automate on `binary_sensor.<name>_doorbell` turning `on`. The `sensor.<name>_call_state` entity carries the `active_session_id` attribute you'll need to terminate the same session
- **Door relay** — call `switch.turn_on` (the relay self-resets after the configured pulse duration)
- **Gate relay** — call `cover.open_cover` / `cover.close_cover`

## Reconfiguring or Re-authenticating

The integration supports the modern HA flows:

- **Reconfigure** (HA 2024.10+) — Settings → Devices & Services → 2N Intercom → ⋮ → **Reconfigure**. Update host, port, protocol, credentials, TLS verification, or the insecure HTTP Basic opt-in without removing the entry. Automations stay attached.
- **Reauth** — when the device starts rejecting credentials the integration raises `ConfigEntryAuthFailed`, and HA shows a notification asking the user to re-enter the password. Click it to walk through the reauth flow.

For per-relay or device-feature changes, use the regular **Configure** (Options) button on the integration card.

Both the setup wizard and **Configure** are step-by-step. To go back, tick **Back to the previous step** and submit the form; entered values stay in the draft and nothing is saved until you finish the last step without that option. HTTP API credentials are changed only in **⋮ → Reconfigure**; the RTSP username/password in the camera options belong to a separate streaming account.

## Services

| Service | Purpose |
|---|---|
| `2n_intercom.answer_call` | Answer the active call session (or a specific `session_id`) |
| `2n_intercom.hangup_call` | Hang up the active call session (or a specific `session_id`) with optional `reason` (`normal` / `rejected` / `busy`) |

Both services target a config entry — pick **2N Intercom** as the integration target in the UI, or pass `data.config_entry_id` from YAML.

Recommended pattern: pair `hangup_call` with the call-state sensor's `active_session_id` attribute so an automation only ends the session it actually answered.

```yaml
- service: 2n_intercom.hangup_call
  target:
    config_entry: <entry_id>
  data:
    session_id: "{{ state_attr('sensor.front_door_call_state', 'active_session_id') }}"
    reason: normal
```

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

### Doorbell binary sensor not flipping
- Ring detection is exclusively event-driven via `/api/log/subscribe` — there is no polling fallback for ring events. Subscription failures are retried with exponential backoff; ring events during a gap are lost
- Check the integration log; a `Log subscription … established` debug line confirms the event channel is up

### Relay not actuating
- Verify the relay number matches the physical hardware (1-4)
- Test the same `switch/ctrl` call from `curl` against the device
- The relay-active binary sensor reflects real device state — if it doesn't toggle, the device itself isn't switching

## Multiple instances

Add the integration multiple times to drive several intercoms — each entry has its own coordinator, services target, and entities.

## Development Status

Implemented:

- Connection / device config flow + reauth + reconfigure + options flow
- Native MJPEG live view (no ffmpeg) and RTSP fallback
- Event-driven state updates (ring, switch, IO, phone, config) with backup polling safety net
- Diagnostic sensors (SIP registration, call state)
- Real cached relay/input state
- `answer_call` / `hangup_call` services
- Auto-discovered switch / cover entities for relays
- HomeKit bridge mapping
- Full HA 2026.4+ compliance

Downstream HA automations (mobile actionable notifications, KNX door opening, etc.) consume the entities and services above; they're not part of the fork itself.

## Support

Open an issue on the GitHub repository.
