# HomeKit Integration

## Overview

This integration exposes HomeKit-friendly entities for camera, doorbell, and door/gate control. The doorbell tile lives **on the camera accessory** in HomeKit. Home Assistant automatically links `event.<intercom>_doorbell` to the camera on the same device, so the recommended setup uses only the UI.

- **Camera path** — the camera is `MjpegCamera`-based, so HomeKit gets a clean MJPEG live view without ffmpeg or HLS
- **Relay-based path** — door relays are exposed as switches and gate relays as covers
- **Legacy no-relay path** — the fallback lock entity still uses door/gate semantics for HomeKit mapping
- **Doorbell path** — a doorbell event entity provides automatic camera linking and HomePod chimes

## Recommended: UI-only video doorbell setup

1. Enable **Camera** and **Doorbell** in the 2N Intercom integration. The device page should show the camera and `event.<intercom>_doorbell`.
2. Open **Settings > Devices & services > Add integration > HomeKit Bridge**.
3. Select **Accessory** mode and include **only the camera entity** (`camera.<intercom>_camera`).
4. Pair the accessory with Apple Home using the pairing code shown by Home Assistant.
5. In the Home app, enable doorbell notifications and select the HomePods that should chime in the accessory's settings.

HomeKit finds the `EventDeviceClass.DOORBELL` event entity on the camera's device automatically; do not include the event as a separate accessory. Each intercom-started ring produces one `ring` event, even though the intercom reports it through two call log events. Incoming calls and peers excluded by the Called ID filter do not ring.

Do not expose the same camera through another HomeKit bridge or accessory. If it was previously paired as an ordinary camera or with a separate occupancy accessory, remove that old pairing and recreate the camera accessory with this setup so Apple Home discovers it as a video doorbell.

## Explicit YAML fallback

For an explicit link, set `linked_doorbell_sensor` to the doorbell event in YAML:

```yaml
homekit:
  - name: 2N Intercom Doorbell
    mode: accessory
    port: 21065
    filter:
      include_entities:
        - camera.2n_intercom_camera
    entity_config:
      camera.2n_intercom_camera:
        linked_doorbell_sensor: event.2n_intercom_doorbell
```

Include only the camera in this accessory's filter, not the doorbell event. Do not expose the camera in another bridge. After changing YAML, restart Home Assistant; if Apple Home still shows the old accessory type, remove its pairing and pair it again.

## How it works

### 1. Configuration flow

When setting up the integration, users go through the multi-step flow:

- **Connection** — host, port, protocol, username, password, SSL verification
- **Device** — name, camera, doorbell, relay count, optional ringing peer
- **Relay** — per-relay door/gate type, relay number, pulse duration

The integration also supports **reauth** (auto-triggered on credential failure) and **reconfigure** (HA 2024.10+) flows for changing connection details without removing the entry.

### 2. Relay type and legacy lock mapping

Relay-based installs store door/gate behaviour per configured relay — door relays surface as switches, gate relays as covers. When no relays are configured the integration falls back to a single legacy lock entity whose `device_class` is set from the same door/gate option, so existing pre-1.0 setups still get a correctly-typed HomeKit accessory.

### 3. HomeKit entity mapping

Home Assistant's HomeKit bridge uses the entity's class to pick an accessory type:

| HA entity | HomeKit accessory |
|---|---|
| `camera.<intercom>_camera` (auto-linked to the doorbell event on the same device) | **Video Doorbell** — the doorbell tile lives here, not on a separate sensor |
| `event.<intercom>_doorbell` (`device_class: doorbell`) | Ring trigger for the camera accessory, automatically discovered without adding it to the HomeKit filter |
| `switch.<intercom>_<door_relay>` | Switch (or Lock, depending on bridge filter) |
| `cover.<intercom>_<gate_relay>` | **Garage Door Opener** — open/close states |
| `lock.<intercom>_lock` (legacy fallback) | Lock when `device_class=None`; Garage Door Opener when `device_class="gate"` |

The event is the only doorbell entity. In v1.5.0 the old doorbell binary sensor
and its registry entry are removed without a deprecation period. Update old
explicit YAML links and automation/blueprint inputs to the event entity.
UI-only camera auto-linking needs no change.

### 4. Real cached state for status entities

`binary_sensor.<intercom>_input_1` and `binary_sensor.<intercom>_relay_1_active` are derived from the device's `io/status` and `switch/status` endpoints. They reflect real device state, not optimistic switching, which keeps HomeKit and HA in sync after manual relay activations from the 2N keypad or web UI.

## User experience

### Setup flow

1. User adds the **2N Intercom** integration
2. Enters connection settings — credentials are validated against `system/info`
3. Configures device options: camera, doorbell, relay count, optional ringing peer
4. Configures relay type and pulse duration per relay
5. Integration creates camera, doorbell, status sensors, relay entities, or the legacy lock entity when no relays are configured

### Changing settings later

- **Connection / credentials** → Reconfigure flow (host, port, protocol, credentials, SSL)
- **Device features or relay settings** → Options flow ("Configure" button on the integration card)
- **Credential rejection** → Reauth flow auto-triggered with a notification

### HomeKit integration

Once the integration is set up and the HomeKit bridge is configured in HA:

1. The camera is included in a UI-configured HomeKit accessory and automatically linked to the doorbell event
2. The relevant relay entities (or the legacy lock entity) can be included in a separate HomeKit bridge
3. The device appears in the Home app with the correct accessory type
4. iOS/macOS users can control the door / gate
5. Siri commands work (e.g. "Hey Siri, open the front door")

## Technical details

### HomeKit declaration

`manifest.json`:

```json
{
  "domain": "2n_intercom",
  "homekit": {}
}
```

This tells HA the integration is HomeKit-compatible.

### Doorbell device class

`event.<intercom>_doorbell` uses `EventDeviceClass.DOORBELL` and supports the event type `ring`. It shares the camera's device, which lets HomeKit discover and link it automatically. Its attributes include `called_peer` and caller name/number when known. It does not generate a new ring on startup or restore.

For HA automations, react to timestamp changes with `event_type: ring`, not an
`on` state. Ignore startup/restore and unavailable transitions; the notification
blueprint and [README example](README.md#automation-examples) include these guards.

### Camera transport

The camera is built on `homeassistant.components.mjpeg.MjpegCamera`. Credentials are passed via the `username` and `password` constructor kwargs and **never** appear in the URL. `stream_source()` only returns an RTSP URL when the device has the RTSP licence — for the typical IP Verso baseline, MJPEG is served natively to HomeKit and HA dashboards alike, with no ffmpeg in the loop.

### Services available to automations

| Service | Use case |
|---|---|
| `2n_intercom.answer_call` | Answer the active call |
| `2n_intercom.hangup_call` | Hang up the active or a specific session, with optional reason |

These pair naturally with HomeKit / mobile actionable notifications: tap "Open door" → fire the relay → call `2n_intercom.hangup_call` with the `active_session_id` to end the call cleanly.

## Translations

The legacy door/gate terminology is translated in both English and Czech.

| EN | CS |
|---|---|
| Door | Dveře |
| Gate | Vrata |
| Door (momentary switch) | Dveře (momentální spínač) |
| Gate (garage door opener) | Vrata (garážová vrata) |

## Example relay configurations

### Door relay → switch in HomeKit

```yaml
relay_name: "Front Door"
relay_device_type: "door"
relay_pulse_duration: 2000
```

### Gate relay → garage door opener in HomeKit

```yaml
relay_name: "Driveway Gate"
relay_device_type: "gate"
relay_pulse_duration: 15000
```
