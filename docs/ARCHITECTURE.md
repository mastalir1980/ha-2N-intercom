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
| `config_flow.py` | `ConfigFlow` (user / reauth / reconfigure) a `OptionsFlow` (chování: polling, kamera, relé). Auto-detekce protokolu/portu. |
| `coordinator.py` | `TwoNIntercomCoordinator` (rozšiřuje `DataUpdateCoordinator`). Drží cache stavů, zpracovává log-události, řídí ring/motion detekci, background long-poll task. |
| `api.py` | `TwoNIntercomAPI` – bezstavový HTTP klient. Parsování chyb 2N, kamera caps/transport, RTSP digest probe, řízení relé, snapshot. |
| `entity.py` | Sdílená základní entita (`device_info`, `available`, `has_entity_name`). |
| `camera.py` | `MjpegCamera` – live view (RTSP/MJPEG/JPEG snapshot stream). |
| `binary_sensor.py` | Zvonek (occupancy), IO vstup, relé-aktivní, pohyb. |
| `switch.py` | Door relé – dynamicky objevené z `/api/switch/caps`. |
| `cover.py` | Gate relé (garážová vrata) – jen pro relé typu `gate`. |
| `sensor.py` | Diagnostika: SIP registrace, stav hovoru. |
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
       └─ forward_entry_setups(platforms) (camera/binary_sensor/switch/cover/sensor)
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
```

Koordinátor předává entitám snímek `TwoNIntercomData` (call status, phone/switch/io
status a caps, active session id, last ring time…). Entity jsou **čistí konzumenti
cache** – při `async_update` nesahají na zařízení (proto `PARALLEL_UPDATES = 0`
u read-only platforem a `1` u switch/cover, které spouští relé).

### Rozdělení `entry.data` vs `entry.options`

- **`entry.data`** = identita připojení (host, port, protokol, username,
  password, verify_ssl, serial). Mění se jen přes **reauth / reconfigure**.
- **`entry.options`** = chování (scan_interval, kamera transport, RTSP creds,
  relé overrides, called_id). Mění se přes **options flow**.

Toto oddělení zajišťuje, že options flow nikdy nepřepíše úspěšný reauth.

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
3. `_process_log_event()` **patchuje cache na místě** (např. nastaví
   `switches[i]["active"]`) a zavolá `async_update_listeners()` → entity se
   překreslí okamžitě.
4. Při chybě/odpojení: exponenciální backoff (5 s → max 60 s) a re-subscribe.
   `DeviceState=startup` (reboot) → naplánuje full refresh.

### 3. Polling (záchranná síť)
`_async_update_data` každých `scan_interval` (default 60 s) načte
`phone/status`, `switch/caps`, `switch/status`, `io/status`, `call/status` a
obnoví baseline, kdyby nějaká push událost vypadla.

Detaily endpointů: [`API_REFERENCE.md`](API_REFERENCE.md).

---

## Detekce zvonění a hovorů

- Ring detection is **event-driven**, using `_RING_STATES` (`ringing`,
  `alerting`, `ring`). Direction and originator are from the intercom's
  point of view: `CallStateChanged` rings only with `direction=outgoing`;
  `CallSessionStateChanged` rings only with a non-empty `originator` other
  than `incoming` (for example, `button`). A missing originator is not a
  ring signal. Calls into the intercom never trigger the doorbell.
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
  direction/originator, session, sorted canonical session peers, configured
  canonical filter (`all` for All calls) and the decision
  (`rang`, `filtered by peer`, `not a ring`). Raw payloads and credential-bearing
  peer URLs are not logged.
- `ring_active` je krátký pulz (`DOORBELL_PULSE_DURATION = 1 s`) – binary
  sensor zvonku se rozsvítí na pulz, ne na celou délku vyzvánění.
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

Credentials se do `MjpegCamera` předávají **odděleně** (username/password), ne
v URL – aby neunikly do logů/diagnostiky. RTSP je výjimka (creds patří do URI).

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
