# Architektura integrace 2N Intercom

> Vývojářská dokumentace. Uživatelská část je v [`README.md`](../README.md) a [`INSTALLATION.md`](../INSTALLATION.md).

Tato integrace je Home Assistant *custom component* (`custom_components/2n_intercom/`)
pro 2N IP interkomy. Komunikuje s lokálním zařízením přes jeho HTTP API
(`/api/*`) a volitelně RTSP. `iot_class` je **`local_push`** – stav se přenáší
hlavně událostmi (`/api/log/subscribe`), polling slouží jen jako záchrana.

Diagramy (otevři v [excalidraw.com](https://excalidraw.com) nebo VS Code rozšíření *Excalidraw*):

- [`architecture.excalidraw`](architecture.excalidraw) – komponenty a jejich vazby
- [`event-flow.excalidraw`](event-flow.excalidraw) – tok událostí device → entita

---

## Přehled komponent

| Soubor | Role |
|---|---|
| `__init__.py` | Životní cyklus config entry (`async_setup_entry` / `async_unload_entry`), registrace služeb `answer_call` / `hangup_call`, vytvoření HA `aiohttp` session s Digest middleware, start/stop log-listeneru. |
| `config_flow.py` | `ConfigFlow` (user / reauth / reconfigure) a `OptionsFlowWithReload` (chování: polling, kamera, relé). Auto-detekce protokolu/portu. |
| `coordinator.py` | `TwoNIntercomCoordinator` (rozšiřuje `DataUpdateCoordinator`). Drží cache stavů, zpracovává log-události, řídí ring/motion detekci, background long-poll task. |
| `api.py` | `TwoNIntercomAPI` – bezstavový HTTP klient. Parsování chyb 2N, kamera caps/transport, RTSP digest probe, řízení relé, snapshot. |
| `entity.py` | Sdílená základní entita (`device_info`, `available`, `has_entity_name`). |
| `camera.py` | `MjpegCamera` – live view (RTSP/MJPEG/JPEG snapshot stream). |
| `event_pictures.py` | Opt-in local-media JPEG history: executor-only file IO, shared 10-second capture throttle, retention and last-ring restore. |
| `binary_sensor.py` | IO inputs, relay-active, motion; no doorbell binary sensor. |
| `event.py` | Doorbell events (`EventDeviceClass.DOORBELL`) for HomeKit camera auto-linking. |
| `switch.py` | Door relé – dynamicky objevené z `/api/switch/caps`. |
| `cover.py` | Gate relé (garážová vrata) – jen pro relé typu `gate`. |
| `sensor.py` | Diagnostika: SIP registrace, stav hovoru. |
| `update.py` / `firmware.py` | Informational firmware entity and public catalog checks; independent six-hour timer, no device firmware writes. |
| `web.py` | Credential-free device web UI URL shared by device info and the firmware entity. |
| `diagnostics.py` | Redigovaný dump pro bug reporty. |
| `const.py` | Konstanty, klíče konfigurace, defaulty. |

### Vrstvení

```
HA Core
  └─ __init__.async_setup_entry
       ├─ vytvoří aiohttp session (DigestAuthMiddleware, preemptive=False)
       ├─ TwoNIntercomAPI                (HTTP/RTSP klient – bez stavu HA)
       ├─ TwoNIntercomCoordinator        (cache + události + polling)
       │     └─ background log listener   (subscribe → pull → apply)
       └─ forward_entry_setups(platforms) (camera/image/binary_sensor/event/switch/cover/sensor/update)
```

`api.py` nezávisí na ničem z HA (jen `aiohttp`), takže je testovatelný samostatně
a používá se i v config flow před vytvořením entry.

---

## Datový model a runtime data

Stav se nedrží v `hass.data`, ale v typovaném objektu na `entry.runtime_data`
(HA quality-scale rule *runtime-data*):

```python
@dataclass
class TwoNIntercomRuntimeData:
    coordinator: TwoNIntercomCoordinator
    api: TwoNIntercomAPI
    loaded_platforms: list[str]
    firmware_latest_version: str | None
```

Koordinátor předává entitám snímek `TwoNIntercomData` (call status, phone/switch/io
status a caps, active session id, last ring time…). Entity jsou **čistí konzumenti
cache** – při `async_update` nesahají na zařízení (proto `PARALLEL_UPDATES = 0`
u read-only platforem a `1` u switch/cover, které spouští relé).

The informational update entity is also a cache consumer for device data, but
checks the public 2N firmware catalog through HA's shared, unauthenticated
session. It uses its own six-hour timer (removed when the entity unloads) and
also checks before its initial state is added and on `homeassistant.update_entity`.
It never uses the device session, downloads firmware, or calls device firmware
endpoints. Failures keep cached versions/notes and log once per failure streak,
without changing coordinator availability or the log listener.

Optional event picture history is separate from the in-RAM last-ring cache.
The coordinator reserves one storage capture slot every ten seconds across
rings and credential attempts; a throttled ring still refreshes the image cache.
Only ring and card/code/mobile-key/fingerprint events save JPEGs. API requests
and follow-up access events never capture a second image. The store writes,
scans, checks writability and applies retention in the executor, confined to the
entry-title folder in local media and without following symlinks. Setup restores
the newest saved ring before forwarding the image platform, then schedules
cleanup immediately and every 24 hours with entry-owned unload cancellation.

### Rozdělení `entry.data` vs `entry.options`

- **`entry.data`** = connection identity (host, port, protocol, username,
  password, verify_ssl, serial_number, mac_address). Reauth and reconfigure
  preserve the stored MAC. SSDP discovery can also update the host.
- **`entry.options`** = chování (scan_interval, kamera transport, RTSP creds,
  relé overrides, called_id, firmware_channel). Mění se přes **options flow**.

Toto oddělení zajišťuje, že options flow nikdy nepřepíše úspěšný reauth.

Config entries register no update listener. Options changes reload through
`OptionsFlowWithReload`; reauth and reconfigure use `async_update_reload_and_abort`
with the integration's success reasons. Each action requests one reload, including
reauth after an authentication-related setup failure. The setup-time MAC backfill
only updates entry data and does not request a reload.

### SSDP discovery and address updates

The manifest matches SSDP manufacturer `2N, part of Axis group`, including
Control4 DS2 units. Discovery pre-fills the host and friendly name but still
requires API credentials. The SSDP `serialNumber` is a MAC address, not the
2N serial returned by `/api/system/info`: normalized `mac_address` in entry
data is the discovery cross-reference, while the config entry's serial-based
unique ID remains unchanged. Older entries backfill `mac_address` from the
coordinator's cached `macAddr` during setup, without an extra API request.

A matching announcement on a new host first queries `/api/system/info` using
the saved credentials, protocol, port and TLS verification setting. The normalized
API MAC must match the stored MAC; serial-based unique IDs also require the API
serial to match. Only then is the host updated in place and one reload requested
through `hass.config_entries.async_schedule_reload`;
an unchanged host does neither and makes no verification request.

The temporary client permits Basic fallback only over verified HTTPS, independently
of `allow_insecure`; Digest remains available on all saved transports. Verification
failures leave the entry unchanged and produce one credential-free WARNING per
candidate host per entry lifetime. The warning cache is shared by discovery flows
in `hass.data`, not the reloadable runtime data. API error details are not logged
for these probes. One INFO line records successful moves without credentials or
the MAC. HTTPS with certificate verification is still recommended.
Diagnostics apply recursive redaction to credentials, serial/MAC fields, call
peers (including the configured `called_id`) and access-event identities.
Known device serial/MAC values are also masked inside free text such as entry
titles, saved names and `deviceName`. Phone status retains only account indexes,
account types and registration telemetry; additional account/registrar identity
fields are redacted even when nested. Caller details are not exported.
Firmware/hardware versions, variant, capabilities and connection host/port stay
readable. Redaction does not mutate config entry data or coordinator caches.

---

## Tok dat

### 1. Setup
1. `async_setup_entry` vytvoří session + API + koordinátor.
2. `async_initialize_static_caches()` jednorázově načte *statické* deskriptory:
   `system/info`, `system/caps`, `switch/caps`, `io/caps`, camera transport.
   (Refetch každých pár sekund by zbytečně generoval ~17k requestů/den.)
3. `async_config_entry_first_refresh()` načte první stav.
4. Nastartuje se log-listener jako background task pod config entry.
5. Forward platformy → entity se vytvoří z cache.

### 2. Události (hlavní cesta – `local_push`)
Background task `_async_log_listener_loop`:
1. `subscribe` na události (`CallStateChanged`, `SwitchStateChanged`,
   `InputChanged`, `OutputChanged`, `RegistrationStateChanged`,
   `ConfigurationChanged`, `CapabilitiesChanged`, `DeviceState`,
   volitelně `MotionDetected`).
2. Smyčka `pull` (server blokuje `timeout=1s`).
3. `_process_log_event()` patches the cache in place. Each accepted access event
   and each counted ring immediately fires `2n_intercom_event` on the HA bus,
   in device order, before the batch publishes coordinator state. Access payloads
   contain only parsed `AccessEvent` fields (fixed keys, unknown values `null`);
   ring metadata comes from `ring_event_attributes()`, shared with the doorbell
   entity. No credentials or raw params are forwarded. Device registry lookup is
   lazy and retries until the shared device exists. Directory name back-fill
   updates coordinator state only and never re-fires a bus event.
4. `_publish_event_state()` publishes the latest state once per pull batch and
   calls `async_update_listeners()` so entities update. Diagnostics `event_bus`
   reports the active subscription's bus types and counts since setup, without
   user data; bus firing does not depend on the doorbell entity being enabled.
5. Při chybě/odpojení: exponenciální backoff (5 s → max 60 s) a re-subscribe.
   `DeviceState=startup` (reboot) → naplánuje full refresh.

### 3. Polling (záchranná síť)
`_async_update_data` každých `scan_interval` (default 60 s) načte
`phone/status`, `switch/status`, `io/status`, `call/status` a
obnoví baseline, kdyby nějaká push událost vypadla.

`switch/caps` is cached at setup, refreshed on configuration/capability events
and after each successful log (re)subscription. Polls refresh it only when
uncached or at least 600 seconds after the last successful fetch. Failed fetches
retain the cache and are retried by subsequent polls; `io/caps` handling is unchanged.

`system/info` is reused for the first refresh and fetched again on subsequent
polls so the installed firmware version follows updates performed in the device
web UI. A failed metadata refresh retains the cached version. This local refresh
does not trigger a public firmware catalog check.

Detaily endpointů: [`API_REFERENCE.md`](API_REFERENCE.md).

---

## Detekce zvonění a hovorů

- Ring detection is **event-driven**, using `_RING_STATES` (`ringing`,
  `alerting`, `ring`). Direction and originator are from the intercom's
  point of view: `CallStateChanged` rings only with `direction=outgoing`;
  `CallSessionStateChanged` rings only with a non-empty `originator` other
  than `incoming` (for example, `button`). A missing originator is not a
  ring signal. Calls into the intercom never trigger the doorbell.
- Optional button metadata is independent of ring detection:
  `CallSessionStateChanged` with `originator=button` stores a plain numeric
  `info` string (1-3 digits after trimming, value 1..150) in
  `_session_buttons`, keyed by the explicit session ID. Missing or invalid
  values are ignored. When a new ring is counted, `last_ring_button` is set
  from that same session, or to `None` if unknown. An earlier `initialized`
  event therefore supplies the button even if `CallStateChanged` rings first.
  A terminal session state removes the stored button, including when the
  terminal event resolves to the last observed session; an individual call
  ending does not remove it. Each new ring replaces the previous ring's
  button, so unknown metadata never inherits an earlier press's number.
  Only button 1 has been verified on real hardware (fw 3.x); other buttons
  and the presence of this metadata on older firmware remain unverified.
- The opt-in `ring_on_keypress` option (off by default, in `entry.options`)
  subscribes to `KeyPressed` only when `/api/log/caps` lists it. Call-button
  keys `%1` through `%54` use the same ring counter and optional snapshot
  as call events, so the doorbell event fires without a poll even if no
  call follows. Keypad digits, `*` and `#` never ring; no key values are logged.
  A press supplies `last_ring_button` from `%n`, has no peer, bypasses
  `called_id`, and clears the previous `called_peer`.
  If it arrives first, the event can have no `called_peer`
  even when the press starts a call. The shared ring guard prevents a second
  ring/snapshot in either event order and keeps the button of the counted
  ring unchanged, including intervening
  `initialized`/`connecting` events. A press-only guard clears after
  `KEYPRESS_RING_HOLD = 3 s`; a call that takes over is cleared by call state.
  Unloading cancels the pending timer.
- The optional `called_id` filter matches **any peer called in the same
  session**, not just the last peer reported. Both call event types accumulate
  canonical peers from `peer`/`address`, including the `connecting` event
  (later `ringing` events may carry no peer). Sessionless events use the most
  recently observed session. Polling merges all calls in each current session
  without discarding peers already seen in events, and never triggers a ring.
  Session termination or removal from `call/status` clears that session's peers;
  an individual parallel call ending does not clear the session.
  Canonicalization is shared by the stored option and event/status values:
  lower-case, remove `sip:`/`sips:`, keep the user before `@`, and remove
  `;params` and `:port` (also excluding any SIP password). Directory choices and
  `called_id` in `entry.options` are not rewritten.
  The part after `/` in Called ID is ignored when matching peers, so
  `1234567890/2` matches `1234567890`.
- Every call event is logged at DEBUG with the event name, state,
  direction/originator, session, optional stored button number, sorted canonical
  session peers, configured
  canonical filter (`all` for All calls) and the decision
  (`rang`, `filtered by peer`, `not a ring`). Raw payloads and credential-bearing
  peer URLs are not logged.
- `ring_active` remains an internal short coordinator pulse
  (`DOORBELL_PULSE_DURATION = 1 s`); it no longer backs a binary sensor.
- `ring_count` increases only when a new allowed ring starts, using the same
  guard that deduplicates ring snapshots for the two call event types.
  `event.<intercom>_doorbell` watches this counter and emits `ring` with the
  existing called-peer and caller name/number metadata and the integer
  `button` attribute only when `last_ring_button` is known. It baselines the
  counter when added, so startup/restore and polling do not create rings.
  The event shares the camera's device for HomeKit's automatic doorbell link
  and is the only doorbell entity. Its unique ID remains
  `<entry_id>_doorbell_event`; ring detection, filtering, `last_ring_time`
  and the last-ring snapshot are unchanged.
- On setup, `__init__.py` removes only the legacy registry entry for
  domain `binary_sensor`, integration `2n_intercom`, unique ID
  `<entry_id>_doorbell`, even when the doorbell option is off. This v1.5.0
  breaking change has no deprecation period. Automations/blueprints and explicit
  HomeKit links must use the event entity instead. The notification blueprint
  discovers the active call-state sensor and camera on the triggering device,
  independent of entity names, and pins services to that config entry/session.
- `active_session_id` se drží jako zdroj pro `answer_call` / `hangup_call`,
  ale služby si pro jistotu dotáhnou *živý* `call/status` ze zařízení.

---

## Kamera a transport

`async_get_camera_transport_info()` jednorázově vyřeší nejlepší způsob živého
náhledu podle `live_view_mode` (auto/rtsp/mjpeg/jpeg_only) a schopností zařízení:

- **RTSP** – jen když jsou nastavené samostatné RTSP creds (RTSP server má
  vlastní databázi uživatelů) a digest probe projde; advertuje `STREAM`.
- **MJPEG** – nativně přes `MjpegCamera`, bez ffmpeg. Kvůli reverse proxy
  (Caddy/nginx buffering `multipart/x-mixed-replace`) integrace skládá MJPEG
  z opakovaných JPEG snapshotů (`handle_async_still_stream`).
- **JPEG snapshot** – vždy dostupný fallback, cache 1 s v koordinátoru.

HTTP API credentials stay in the integration's authenticated request path;
`MjpegCamera` receives neither a username nor a password. Snapshot and MJPEG
playback use the coordinator's snapshot cache, preserving Digest/Basic fallback
and `allow_insecure` rules without credentials in HTTP URLs. The public MJPEG
probe reuses the API session with a per-request `middlewares=()` override, so
it sends no credentials and does not alter the session's normal auth path.
RTSP remains the exception (credentials belong in the URI); its Digest probe
uses a random client nonce and rejects quotes, CR and LF in usernames or realms.

---

## Dynamické entity (relé)

`switch.py` nemá pevný počet relé. `_async_check_relays()` (callback na update
koordinátoru) porovná `switch/caps` (`enabled` relé) s registrem a:
- přidá entity pro nově povolená relé,
- odebere entity pro relé, která zmizela (přes `entity_registry`).

Relé označené uživatelem jako `gate` se přeskočí ve switch a místo toho vznikne
`cover`.

---

## Životní cyklus a úklid

- Log-listener je registrovaný jako **background task config entry**, takže ho HA
  zruší při unloadu. Navíc `EVENT_HOMEASSISTANT_STOP` listener volá
  `async_stop_log_listener()` před fází *final writes*, aby long-poll request
  stihl skončit (jinak HA hlásí "still running after final writes").
- `async_unload_entry` odpojí přesně ty platformy, které byly nahrané
  (`runtime_data.loaded_platforms`), zastaví listener, zavře API session
  (jen pokud ji integrace vlastní) a vynuluje `runtime_data`.

---

## Zpracování chyb

- `api.py` mapuje 2N chybové payloady (`{"success": false, "error": {...}}`)
  na `TwoNDeviceError` a loguje jednotně. Kód **14** je přetížený (firmware
  2.50): `"session not found"` = idempotentní úspěch hangupu, `"Unsupported
  Content-Type"` = skutečné selhání → rozlišuje se podle `description`.
- Call-control používá **GET** (ne POST), protože firmware 2.50.0.76.2 odmítá
  aiohttp POST bez těla.
- Koordinátor: `TwoNAuthenticationError` → `ConfigEntryAuthFailed` (spustí
  reauth flow); spojení → retry/backoff přes `update_interval`, po `MAX_RETRIES`
  `ConfigEntryNotReady`.
