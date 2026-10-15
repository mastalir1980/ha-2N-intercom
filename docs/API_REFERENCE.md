# 2N HTTP/RTSP API – endpointy použité integrací

Reference toho, co `api.py` skutečně volá na zařízení 2N. Vychází z 2N HTTP API
manuálu (firmware 2.50) a chování ověřeného na 2N IP Verso `2.50.0.76.2`.

Všechny HTTP odpovědi mají tvar:

```json
{ "success": true,  "result": { ... } }
{ "success": false, "error": { "code": 14, "description": "...", "param": "..." } }
```

Autentizace: **HTTP Digest** (middleware, `preemptive=False`), s **fallbackem na
Basic**, pokud zařízení vrátí `401` s `WWW-Authenticate: Basic`.

## HTTP endpointy

| Endpoint | Metoda | Použití v kódu | Poznámka |
|---|---|---|---|
| `/api/system/info` | GET | `async_get_system_info` | model, swVersion, serial, MAC → device_info & unique_id |
| `/api/system/caps` | GET | `async_get_system_caps` | `motionDetection`, `rtspServer` stav (`active,licensed`) |
| `/api/call/status` | GET | `async_get_call_status` | aktivní sessions, stav hovoru, peer |
| `/api/call/answer` | GET | `async_answer_call` | param `session` |
| `/api/call/hangup` | GET | `async_hangup_call` | param `session` (+ volitelně `reason`) |
| `/api/dir/query` | POST | `async_get_directory`, `async_get_directory_users` | peery pro filtr `called_id`, uživatelé (`uuid`, `name`) pro options grant_access a jména u přístupových událostí |
| `/api/accesspoint/grantaccess` | GET | `async_grant_access` | `id` (0 vstup / 1 výstup), `user` (uuid) → `accessGranted`, `reason`; vyžaduje oprávnění *Access Control – Control* (skupina API Access Control) |
| `/api/phone/status` | GET | `async_get_phone_status` | SIP účty, registrace |
| `/api/switch/caps` | GET | `async_get_switch_caps` | povolená relé, `switchOnDuration` |
| `/api/switch/status` | GET | `async_get_switch_status` | `active` / `held` relé |
| `/api/switch/ctrl` | GET | `async_switch_control` | `switch`, `action` (on/off/trigger), `duration` |
| `/api/io/caps` | GET | `async_get_io_caps` | physical ports; one binary sensor per input also present in io/status, including module and tamper ports |
| `/api/io/status` | GET | `async_get_io_status` | cached input/output states, patched by InputChanged/OutputChanged events |
| `/api/io/ctrl` | GET | `async_io_control` | `port`, `action=on\|off`; latching output control, requires I/O control privilege and bypasses logical-switch timing |
| `/api/camera/caps` | GET | `async_get_camera_caps` | rozlišení JPEG, zdroje (internal/external) |
| `/api/camera/snapshot` | GET | `async_get_snapshot` / MJPEG | `source`, `width`, `height`, (`fps` pro MJPEG) |
| `/api/log/caps` | GET | `async_get_log_caps` | `events` = seznam podporovaných událostí; průnik s přístupovými událostmi |
| `/api/log/subscribe` | GET | `async_subscribe_log` | `filter` = seznam událostí → vrací `id` |
| `/api/log/pull` | GET | `async_pull_log` | `id`, `timeout` (long-poll, server blokuje) |
| `/api/log/unsubscribe` | GET | `async_unsubscribe_log` | `id` |

### IO input ports

Input discovery uses every port with `type=input` in `/api/io/caps` that is
also present in `/api/io/status`, including extension-module ports such as
`modul1.input1` and `modul1.input2`. Malformed entries and ports missing from
status are skipped. Input sensors are enabled by default and read cached
device states (`0`/`1`); `InputChanged` events accept bool or integer `0`/`1`
and polling remains a safety net.

The built-in `input1` retains unique ID `{entry_id}_input1` and translation
key `input_1`. Other inputs use `{entry_id}_io_<port>` with the port name
verbatim. Ports named `tamper` or ending in `.tamper` are the tamper sensors:
their device class is `tamper` and their state comes from `/api/io/status`.
No additional tamper entity is created from `TamperSwitchActivated` events.

### Odběr událostí (`/api/log/subscribe`)

Filtr, který integrace registruje:

```
CallStateChanged, CallSessionStateChanged, SwitchStateChanged,
InputChanged, OutputChanged, RegistrationStateChanged,
ConfigurationChanged, CapabilitiesChanged, DeviceState
[, MotionDetected]   # jen když system/caps hlásí motionDetection=active
[, CardEntered, CodeEntered, MobKeyEntered, FingerEntered,
   UserAuthenticated, UserRejected, AccessTaken, AccessBlocked,
   AccessLimited, ApiAccessRequested, DirectoryChanged]
                     # jen ty, které zařízení uvádí v /api/log/caps
```

`log/caps` se čte při každém (re)subscribe a po `ConfigurationChanged` /
`CapabilitiesChanged`; když se seznam změní, listener se přihlásí znovu. Když
`log/caps` selže, přístupové události se neodebírají (základní odběr jede dál).

Mapování událost → akce koordinátoru:

| Událost | Akce |
|---|---|
| `CallStateChanged` / `CallSessionStateChanged` | ring detekce, `active_session_id`, peer |
| `SwitchStateChanged` | patch `switch_status[i].active` |
| `InputChanged` / `OutputChanged` | patch `io_status` portu |
| `RegistrationStateChanged` | patch SIP účtu v `phone_status` |
| `ConfigurationChanged` / `CapabilitiesChanged` | refresh switch/io caps (přidá/odebere relé) |
| `DeviceState=startup` | full refresh (zařízení se rebootlo) |
| `MotionDetected` (`state=in/out`) | binary sensor pohybu |
| `CardEntered` / `CodeEntered` / `MobKeyEntered` / `FingerEntered` | `last_access_event` (typ credentialu, `valid` → granted); `uid`, `code`, `authid` se **nikdy neukládají** |
| `UserAuthenticated` / `UserRejected` / `AccessTaken` | `last_access_event`; typ credentialu se dědí z předchozí události stejné `session` a `ap` |
| `AccessBlocked` / `AccessLimited` (`state=in/out`) | `last_access_event` (`in` = odepřeno) |
| `ApiAccessRequested` | `last_access_event` (credential `api`, výsledek grant_access) |
| `DirectoryChanged` | zahodí cache jmen z `dir/query` |
| `CallStateChanged` ringing (první) | snímek `camera/snapshot` → entita `image.*_last_ring` (jen se zapnutou kamerou) |

Jména uživatelů: z parametru `name` události, jinak z cache `dir/query` (klíč =
uuid malými písmeny; dir/query vrací uuid velkými, log události malými). Neznámé
uuid spustí refresh adresáře, nejvýš jednou za 60 s.

## RTSP

- URL: `rtsp://<user>:<pass>@<host>:<rtsp_port>/h264_stream`
- `rtsp_port` = `554`, pokud HTTP port je 80/443, jinak stejný jako HTTP port.
- RTSP server má **vlastní databázi uživatelů** – RTSP creds se konfigurují
  zvlášť v options flow, nepoužívají se HTTP API účty.
- Probe: nešifrovaný `OPTIONS`, podle `401` se sestaví **Digest** hlavička
  (`_build_rtsp_digest_auth`, MD5 dle RFC 2069/2617) a ověří se `200 OK`.

## Zvláštnosti firmwaru (zachytit při údržbě)

- **Call-control = GET, ne POST.** POST bez `Content-Type` → `code 14
  "Unsupported Content-Type"`, hovor dál vyzvání.
- **`reason` u hangupu** je u outgoing-ringing session tiše ignorován (firmware
  vrátí `success: true`), proto se posílá jen na explicitní žádost.
- **Snapshot rozlišení** musí být z `camera/caps jepgResolution`; HA preview
  zkouší 80×80 → `code 12` → integrace retryuje na `640×480`.
- **Kód 14** je přetížený – disambiguace podle `description`, ne podle kódu.
- **`log/pull` nemusí blokovat.** Některý firmware vrátí prázdný `log/pull`
  okamžitě i s `timeout=1`; listener proto po prázdném pullu čeká
  `LOG_LISTENER_IDLE_DELAY` (1 s), po pullu s událostmi jen předá řízení
  (`sleep(0)`), jinak by vznikl busy-loop.
- **grantaccess `success: true` neznamená otevření** – rozhoduje `accessGranted`;
  `false` + `reason` (`invalidAp`, `invalidCredential`, `accessBlocked`).
  Kód 18 = požadavek odmítnut (např. vypnutý přístupový bod), kódy 7–10 =
  chybějící oprávnění, 1/2/4 = funkce nepodporovaná.
- **Směr hovoru je z pohledu interkomu** (ověřeno na IP Force 2.0 fw 3.3.x,
  2026-10-13, TASK-29). Stisk tlačítka návštěvníkem = `CallStateChanged`
  `direction=outgoing`; hovor *na* interkom (My2N aplikace, Control4 panel) =
  `direction=incoming`. `CallSessionStateChanged` klíč `direction` vůbec nemá,
  místo něj nese `originator` (`button` u stisku tlačítka, `incoming` u hovoru
  na interkom) a `info` (číslo tlačítka, jen u `originator=button`). Pořadí u
  stisku: session `initialized` → call `connecting` → session `connecting` →
  call `ringing` → session `ringing` → … → `terminated` (call i session).
  Příchozí hovor může být auto-answered ve stejné sekundě (`ringing` →
  `connected`). Další hodnoty `originator` (klávesnice, displej, API) zatím
  nepozorovány; zda je posílá fw 2.50, neověřeno.
