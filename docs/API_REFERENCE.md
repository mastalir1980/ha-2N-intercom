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
| `/api/dir/query` | POST | `async_get_directory`, `async_get_directory_users` | peery pro filtr `called_id`, uživatelé (`uuid`, `name`) pro options grant_access a jména u přístupových událostí; vyžaduje oprávnění *System – Control* (jinak chyba 10) |
| `/api/accesspoint/grantaccess` | GET | `async_grant_access` | `id` (0 vstup / 1 výstup), `user` (uuid) → `accessGranted`, `reason`; vyžaduje oprávnění *Access Control – Control* (skupina API Access Control) |
| `/api/phone/status` | GET | `async_get_phone_status` | SIP účty, registrace |
| `/api/switch/caps` | GET | `async_get_switch_caps` | povolená relé, `switchOnDuration` |
| `/api/switch/status` | GET | `async_get_switch_status` | `active` / `held` relé |
| `/api/switch/ctrl` | GET | `async_switch_control` | `switch`, `action` (on/off/trigger), `duration` |
| `/api/io/caps` | GET | `async_get_io_caps` | physical ports; one binary sensor per input also present in io/status, including module and tamper ports |
| `/api/io/status` | GET | `async_get_io_status` | cached input/output states, patched by InputChanged/OutputChanged events |
| `/api/io/ctrl` | GET | `async_io_control` | `port`, `action=on\|off`; latching output control, requires I/O control privilege and bypasses logical-switch timing |
| `/api/camera/caps` | GET | `async_get_camera_caps` | rozlišení JPEG, zdroje (internal/external) |
| `/api/camera/snapshot` | GET | `async_get_snapshot` / MJPEG | `source`, `width`, `height`, (`fps` for MJPEG); snapshot sizes map to supported JPEG resolutions from `camera/caps` |
| `/api/log/caps` | GET | `async_get_log_caps` | `events` = seznam podporovaných událostí; průnik s přístupovými událostmi |
| `/api/log/subscribe` | GET | `async_subscribe_log` | `filter` = seznam událostí → vrací `id` |
| `/api/log/pull` | GET | `async_pull_log` | `id`, `timeout` (long-poll, server blokuje) |
| `/api/log/unsubscribe` | GET | `async_unsubscribe_log` | `id` |

The integration does not call device firmware endpoints (`/api/firmware`,
`/api/firmware/apply`, `/api/firmware/reject`, `/api/autoupdate/*`).
The read-only update entity uses the public catalog described in *Firmware update*.

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

Integrace žádá z `dir/query` pole `name` a `callPos.peer` (E2E klient jen `name`).
`uuid` vrací 2N u každého záznamu vždy, i když ho `fields` neobsahuje (ověřeno
E2E na fw 3.x), proto ho do `fields` nepřidáváme. Funkce `/api/dir/*` patří
podle dokumentace 2N do skupiny *System* a vyžadují oprávnění **System – Control**;
účet jen se *System – Monitoring* dostane chybu 10 (insufficient privileges).
Options flow porovnává uložené uuid uživatele pro grant_access bez ohledu na
velikost písmen, ale vybraná volba drží uložený řetězec beze změny. Selhání
adresáře = jeden WARNING na dotaz a přeložená chyba `directory_unavailable`,
která formulář neblokuje; neznámé uložené uuid zůstává na výběr. Volání adresáře
z koordinátoru se chovají jako dřív (best effort).

## Firmware update (aktualizace firmwaru z 2N update serveru)

Zjištěno v TASK-50 (spike) na fw 3.x: z JavaScriptu obou webových rozhraní
zařízení (nové UI `/new/`, legacy UI `/`), čtením přes HTTP API účet a voláním
veřejného 2N update serveru. **Žádný firmware se při zjišťování neinstaloval**;
kroky upload/apply níže jsou z kódu UI a z dokumentace 2N. They describe the
device web UI, not integration behavior; TASK-51 never installs firmware.

### Home Assistant update entity (TASK-51)

`update.py` creates one firmware/config update entity per entry when
`system/info` supplies `firmwarePackage`. Its only supported feature is
`RELEASE_NOTES`; there is no install or progress feature.
`installed_version` follows `swVersion`, refreshed by the local coordinator.

The integration option `firmware_channel` selects `active_track` (default,
server track `newest`), `lts` (`lts`), or `beta` (`early`). Device AutoUpdate
settings are not read or written. The public GET uses HA's shared client
session, without the device Digest middleware or Basic credentials, with
`current_ver=<swVersion>&ui_lang=en`. Checks run once at setup, on a separate
six-hour timer, and on `homeassistant.update_entity`.

A 204 response or a 200 response whose type does not match the selected track
sets the latest version to the installed version. Failed or malformed responses
preserve the last known version and notes and log one warning per failure streak.
Catalog failures never interrupt local status polling or the log subscription.
The server's ascending `changelog.md` array is reversed for full markdown release
notes and the 255-character release summary. Download URLs are not retained.
Firmware diagnostics contain only installed/latest versions and the channel.

Both `release_url` and device `configuration_url` link to the device web UI,
built from entry connection data with no credentials and no default port.
The user performs the update there; no firmware is downloaded or installed by HA.

### Kdo co dělá

Tlačítko *Check for updates* / *Update* v UI **nevolá zařízení**. Kontrolu
i stažení dělá **prohlížeč** přímo proti `https://update.2n.cz/hip` (CSP
`connect-src` stránky ho povoluje), zařízení dostane hotový soubor přes
veřejné HTTP API:

1. `GET /api/system/info` → `firmwarePackage`, `swVersion`
2. `GET https://update.2n.cz/hip/<firmwarePackage>/<track>/?current_ver=<swVersion>&ui_lang=<lang>` (bez autentizace)
3. stažení `files[].url` (typ `firmware`) – soubor `.bin`, s `checksum` (SHA-256)
4. `PUT /api/firmware` (multipart, pole `blob-fw`) → `fileId`, `version`, `downgrade`, `note`
5. `POST /api/firmware/apply?fileid=<fileId>` (dokumentace 2N povoluje GET i POST) → `{"success": true}`, zařízení se restartuje
   (případně `/api/firmware/reject?fileid=<fileId>` pro zrušení)

Integrace tedy může udělat totéž co prohlížeč: kontrolu z HA proti update
serveru a instalaci přes `PUT /api/firmware` + `apply`. Do 2N OS 3.2 žádný
příkaz „stáhni a nainstaluj sám" přes HTTP API účet neexistuje (viz níže);
od 3.3 viz „Vestavěná aktualizace" dál.

### Vestavěná aktualizace (2N OS 3.3 a novější)

- Od 2N OS 3.3 má zařízení `GET /api/autoupdate/updatefw`, který spustí
  aktualizaci firmwaru přímo v zařízení. Funguje od 3.3 a potřebuje
  oprávnění **System – Control** (potvrzeno firmware týmem 2N, 19. 10. 2026).
  Ve veřejném HTTP API manuálu 3.3 není.
- **Ověřeno 19. 10. 2026 na E2E interkomu (fw 3.x ≥ 3.3, API účet integrace,
  Digest), když update server pro všechny tři větve vracel `204`:**
  - odpověď `200`, `application/json`, `{"success": true}` za ~70 ms;
  - zařízení se nerestartovalo, `upTime` dál rostl a `swVersion` se
    během 60 s nezměnila.
  - Z toho plyne: `success: true` znamená jen „příkaz přijat", **ne** „aktualizace
    běží". Odpověď se nedá použít k rozlišení „není co instalovat" od
    „instalace začala". Úspěch pozná integrace jen podle změny `swVersion`
    po restartu (nebo podle timeoutu).
- Endpoint na stav nebo průběh není: `/api/autoupdate`, `/api/autoupdate/status`
  i `/api/autoupdate/caps` vrací `{"success": false, "error": {"code": 2,
  "description": "invalid request path"}}`. `/api/log/caps` nemá žádnou událost
  o aktualizaci, firmwaru ani restartu.
- Stále neověřeno: odkud a na jakou verzi aktualizuje, když nová verze existuje
  (nastavená větev a zdroj v `AutoUpdate.*`, nebo vždy nejnovější z update
  serveru). Ověří to skutečná aktualizace s Janovým souhlasem (TASK-66).
- **Nevolat v testech ani při zjišťování, pokud update server pro kteroukoli
  větev nabízí novější verzi** – spustí skutečnou aktualizaci a restart zařízení.
- Integrace v1.5.0 (TASK-51) firmware jen hlásí (verze z update serveru,
  release notes, odkaz na webové rozhraní) a žádný firmwarový endpoint
  zařízení nevolá.

### Update server

| `track` | Větev v UI | `AutoUpdate.UpdateServer.UpgradeMode` |
|---|---|---|
| `newest` | Active track | `1` |
| `lts` | Long-term support (LTS) | `2` |
| `early` | Beta program | `3` |

- `ui_lang` = jazyk changelogu (`en`, …). Nové UI přidává `&_=<random>` proti cache.
- **`204 No Content`** = pro danou větev není novější verze než `current_ver`
  (zařízení je aktuální). Ověřeno pro všechny tři větve s aktuální verzí.
- **`200`** = je dostupná novější verze (příklad zkrácený, hodnoty smyšlené):

```json
{
  "files": [
    { "type": "firmware",
      "url": "https://update.2n.cz/api/downloads/<uuid>",
      "checksum": "<sha256 hex>" }
  ],
  "package_lang": "en",
  "version": "3.y.z.b.i",
  "changelog.md": [
    { "version": "3.y.0.b.i", "language": "EN", "text": "### **2N OS version 3.y …** (markdown)" }
  ],
  "type": { "stable": true, "intermediate": false, "bugfix": false, "lts": false },
  "updatedAt": "2026-…Z",
  "releaseDate": "2026-…+0000",
  "customer": "generic"
}
```

- `changelog.md` je **pole** všech verzí mezi `current_ver` a cílovou verzí
  (vzestupně), každá položka je markdown. UI je řadí od nejnovější.
- `type.stable=false` = beta, `type.lts=true` = LTS. UI hlásí „nová verze" jen
  když typ odpovídá zvolené větvi (Active track ↔ `stable`, LTS ↔ `lts`,
  Beta ↔ `stable=false`); jinak jako „žádná nová verze".
- Stažení: `GET` (UI používá `POST`, server přijme obojí) → `application/octet-stream`,
  `Content-Disposition: attachment;filename=<interní název>_<version>.bin`,
  bez `Content-Length` (chunked). Před uploadem ověřit SHA-256 proti `checksum`.
- Spojení občas timeoutuje (pozorováno u `lts`) → chyba kontroly, ne „žádná verze".
- `AutoUpdate.UpdateServer.UpdateCheckAddress` může nahradit základní URL
  (vlastní update server); prázdné = `https://update.2n.cz/hip`.

### `PUT /api/firmware` a `apply` (veřejné HTTP API, skupina *System*, oprávnění **System – Control**)

- Upload: multipart `blob-fw`. Odpověď `result`: `fileId` (8 hex), `version`,
  `downgrade` (bool), `note` (escapovaný text s upozorněním / release notes
  po verzích; nové UI ho parsuje na položky `{version, language, text}`).
- Chyby uploadu: **12** (`blob-fw`, neplatný soubor / jiné zařízení),
  **19** (verze nižší než povolené minimum), **18** (jiná aktualizace už běží –
  podle kódu UI; nahraný a neaplikovaný soubor se po 5 minutách sám zahodí,
  jinak nejdřív `reject`). Chybějící oprávnění → kódy 7–10 jako u ostatních
  *System – Control* funkcí.
- `downgrade: true` → UI vyžaduje potvrzení (u některých zařízení s factory
  resetem). Integrace downgrade nemá nikdy aplikovat – udělat `reject`.
- `apply`: chyby **12** (neplatné `fileid`), **14** („new firmware not found").
  Po úspěchu se zařízení restartuje. UI pak zastaví log pull, čeká 10 s
  a každé 2 s volá `/api/system/info`, dokud zařízení neodpoví.
- **Stavy:** stahování a upload mají průběh jen na straně klienta (bajty);
  instalace a restart průběh nehlásí. **Úspěch** = po restartu
  `/api/system/info` vrací `swVersion == version` z uploadu. **Selhání** =
  chyba uploadu/apply, nebo po timeoutu stále stará `swVersion`.
- HTTP API účet integrace (Digest) má na E2E zařízení *System – Control*
  ověřeno: `GET /api/config` (stejné oprávnění) vrací `200`.

### Větev a plánovaná automatická aktualizace v zařízení

Zařízení má vlastní plánovač aktualizací. Konfigurace (cesty z UI a ze zálohy
`GET /api/config`):

| Cesta | Význam |
|---|---|
| `AutoUpdate.UpdateSource` | `0` spravováno externě, `1` update server, `2` auto-provisioning (`AutoUpdate.Firmware.*`) |
| `AutoUpdate.UpdateServer.UpgradeMode` | větev, viz tabulka výše |
| `AutoUpdate.UpdateServer.AutoUpdateEnabled` | `0/1` zařízení se aktualizuje samo podle plánu |
| `AutoUpdate.UpdateServer.Period` | `0` hodinově, `1` denně, `2` týdně, `3` měsíčně |
| `AutoUpdate.UpdateServer.DayOfWeek` / `WeekOfMonth` / `UpdateTime` | den (`0` = neděle), týden v měsíci, čas `HH:MM` |
| `AutoUpdate.UpdateServer.CheckAtBootTime` | `0/1` kontrola po startu |
| `AutoUpdate.UpdateServer.LastResult` | výsledek posledního běhu (v XML zálohy) |

- **Čtení přes HTTP API účet:** jen celou zálohou `GET /api/config`
  (XML, stovky kB, obsahuje tajné údaje a licenci) – pro integraci nevhodné.
  `POST /api/system/db/values` (multipart `blob-json` se seznamem cest; tak
  čte UI) vrací s Digest i Basic `{"success": false, "error": {"code": 9,
  "description": "authorization required"}}` – funguje jen s webovou session.
- **Zápis:** jen webová session (`PUT /api/system/db/values`, nebo `/ajax`
  `db.set`), případně nahráním celé konfigurace. Pro integraci ne.
- `/ajax` (příkazy `db.get`, `autoupdate.updatefirmware`,
  `system.applynewfirmware`, …) je interní API UI se session (`sid`);
  s Digest vrací `400`. `autoupdate.updatefirmware` spouští aktualizaci
  ze zdroje auto-provisioning, ne z 2N update serveru. Integrace ho nepoužívá.
- Závěr: větev pro HA je **vlastní volba integrace** (`entry.options`),
  nastavení zařízení se nečte ani nemění.

### fw 2.50 vs. fw 3.x

- `PUT /api/firmware` / `apply` / `reject` jsou v HTTP API manuálu i pro 2.x.
- Legacy UI (na fw 3.x stále na `/`) má stejný modul `hip.autoupdate`
  s `https://update.2n.cz/hip/` a stejnými větvemi `newest`/`lts`/`early`
  a nahrává přes `PUT /api/firmware`; `firmwarePackage` čte z
  `State.Product.FirmwarePackage`. Na fw 2.50 neověřeno na zařízení –
  hypotéza: stejný mechanismus. `firmwarePackage` v `/api/system/info`
  ověřen jen na fw 3.x. When missing, no update entity is created; a debug
  message explains why.
- Na update serveru `lts` pro starou `current_ver` 2.50 vrací `204`
  (LTS větev 3.x z 2.x nenabízí).

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
- **Snapshot resolution** is mapped to `camera/caps` JPEG resolutions: exact
  match, otherwise the smallest size covering both requested dimensions, or
  the largest supported size when none covers the request. Aspect ratio is
  not matched; HA scales the image. Without JPEG capabilities, the requested
  size is retained and this fallback is logged once at debug level. A device
  `code 12` rejection permits one retry at `640x480`, sent without caps mapping,
  only when the first size differs from `640x480`. This is a last resort for
  unavailable caps or firmware rejecting a size it lists; a rejected retry is
  logged as a warning and returns no image.
- **Kód 14** je přetížený – disambiguace podle `description`, ne podle kódu.
- **`log/pull` nemusí blokovat.** Některý firmware vrátí prázdný `log/pull`
  okamžitě i s `timeout=1`; listener proto po prázdném pullu čeká
  `LOG_LISTENER_IDLE_DELAY` (1 s), po pullu s událostmi jen předá řízení
  (`sleep(0)`), jinak by vznikl busy-loop.
- **grantaccess `success: true` neznamená otevření** – rozhoduje `accessGranted`;
  `false` + `reason` (`invalidAp`, `invalidCredential`, `accessBlocked`).
  Kód 18 = požadavek odmítnut (např. vypnutý přístupový bod), kódy 7–10 =
  chybějící oprávnění, 1/2/4 = funkce nepodporovaná.
- **Směr hovoru je z pohledu interkomu** (ověřeno na fw 3.x,
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
