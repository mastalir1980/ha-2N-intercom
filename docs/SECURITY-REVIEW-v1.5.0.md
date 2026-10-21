# Bezpečnostní revize před vydáním v1.5.0

| | |
|---|---|
| Datum | 2026-10-21 |
| Revidovaný stav | `main` @ `28a581c` (merge PR #96), manifest `1.4.0`, milestone v1.5.0 otevřený |
| Autor | Claude (analytik) na žádost Jana; statická revize kódu, bez změn v `custom_components/` |
| Výstup | 4 nálezy založené jako Backlog bugy s labelem `security`: **TASK-67** (High), **TASK-68** (Medium), **TASK-69** (Medium), **TASK-70** (Low) |

> Navazuje na `docs/IMPROVEMENTS.md` (S1–S5 z verze 1.4.0). Položky S1–S3 jsou ověřeně v kódu;
> tato revize je nerozporuje, ale nachází díru v S3 (Basic nad neověřeným HTTPS) a nové plochy
> přidané v 1.5.0 (SSDP discovery, diagnostika, firmware entita).

---

## 1. Shrnutí

- **Žádný nález není zneužitelný z internetu bez přihlášení.** Všechno vyžaduje přístup do lokální
  sítě, nebo jde o únik identifikátorů (diagnostika) a CI hygienu.
- **Jeden nález (S-1, TASK-67) vede k heslu HTTP API účtu interkomu**, tedy k účtu, který typicky
  smí otevírat dveře. V kombinaci se S-2 (TASK-68) ho umí získat kdokoli v LAN jedinou SSDP
  zprávou, bez ARP spoofingu. Doporučuji opravit **před vydáním 1.5.0**.
- S-3 (TASK-69) je soukromí: diagnostika, kterou uživatelé přikládají k veřejným issues, obsahuje
  sériové číslo, MAC a SIP identity. S-4 (TASK-70) je zpevnění CI, release neblokuje.
- Zbytek (sekce 5) jsou vědomě přijatá rizika a drobná doporučení bez založení chyby.

---

## 2. Rozsah a metoda

### 2.1 Co jsem četl (celé soubory, řádek po řádku)

| Oblast | Soubory |
|---|---|
| Integrace | `custom_components/2n_intercom/`: `__init__.py`, `api.py`, `config_flow.py`, `coordinator.py`, `camera.py`, `image.py`, `event.py`, `binary_sensor.py`, `sensor.py`, `switch.py`, `cover.py`, `update.py`, `firmware.py`, `web.py`, `diagnostics.py`, `entity.py`, `const.py`, `services.yaml`, `strings.json` (texty k `verify_ssl` / `allow_insecure`), `manifest.json` |
| CI a pipeline | `.github/workflows/e2e-pi.yml`, `hacs.yml`, `hassfest.yml`, `.github/CODEOWNERS`, `e2e/ci/pr-e2e.sh`, `e2e/ci/ha2n-staging`, `e2e/ci/job-started-hook.sh`, `e2e/ci/install-pi.sh`, `e2e/ci/ci_summary.py`, `e2e/scripts/deploy.sh`, `lock.sh`, `pi.sh`, `e2e/staging/docker-compose.yml`, `e2e/e2elib/twon.py`, `env.py`, `e2e/.env.example`, `e2e/.gitignore`, `.gitignore` |
| Headless kodér | `tools/coder/run-task.sh`, `sandbox.sh`, `set-token.sh`, `install-vm.sh`, `task-status.sh`, `tools/bship.zsh` |
| Ostatní | `blueprints/doorbell_notification_answer_hangup.yaml`, `hacs.json`, `docs/IMPROVEMENTS.md`, `e2e/ci/README.md`, `tools/coder/README.md`, Backlog TASK-49 (SSDP) a TASK-37 (release) |

### 2.2 Kontrolní seznam a výsledek

| # | Oblast | Co jsem hledal | Výsledek |
|---|---|---|---|
| 1 | Transport k zařízení | TLS verifikace, HTTP fallback, pořadí auto-detekce, downgrade | S1/S2 z 1.4.0 v kódu ✅; `verify_ssl=False` zůstává typický stav (přijato, viz O-1) |
| 2 | Autentizace | Digest vs. Basic, kdy se posílá heslo, RTSP Digest | **S-1**: Basic povolen nad HTTPS i bez ověření certifikátu ❌ |
| 3 | Tajemství | hesla v URL, logu, diagnostice, atributech entit, config entry | URL a logy čisté ✅; **S-3**: diagnostika vydává sériové číslo, MAC, SIP identity ❌ |
| 4 | Vstupy z LAN | SSDP discovery, přepis hosta, title placeholders | **S-2**: přepis hosta bez ověření identity ❌; placeholders bezpečné ✅ |
| 5 | Služby a entity | autorizace, validace `session_id`, `user`, `access_point`, `reason` | standardní HA autorizace, parametry jdou kódované do query ✅ |
| 6 | Data ze zařízení | parser log událostí, JSON, snapshot | tolerantní parser, tajemství z událostí (kód, UID karty, authid) se neukládají ✅ |
| 7 | Odchozí spojení mimo LAN | `update.2n.cz` | ověřené TLS přes HA session, bez redirectů, validace odpovědi ✅ (viz O-6) |
| 8 | CI/CD | `pull_request_target`, self-hosted runner, tokeny, auto-merge, sanitizace výstupu | threat model odpovídá kódu ✅; **S-4**: nepřipnuté akce a výchozí oprávnění tokenu v HACS/hassfest ⚠️ |
| 9 | Závislosti | runtime a dev závislosti | integrace bez runtime závislostí ✅; dev požadavky nepinované (přijatelné) |
| 10 | Repo hygiena | `.gitignore`, `.env.example`, soukromé údaje v tracked souborech | ✅ |

### 2.3 Spuštěné kontroly (baseline na `28a581c`)

```
python3 -m py_compile custom_components/2n_intercom/*.py   # OK
python3 validate.py                                        # All checks passed
python3 -m unittest discover -s tests -t tests             # Ran 704 tests – OK (Python 3.13)
backlog doctor                                             # OK
```

### 2.4 Co jsem **netestoval**

- Žádné dynamické testy proti reálnému interkomu ani E2E (`e2e.sh`). Nálezy S-1 a S-2 jsou
  odvozené z kódu; scénář útoku je popsaný, ale **nebyl reprodukován** na síti.
- Chování HA core (`MjpegCamera`, `stream`) posuzuji podle jeho veřejného API, ne ze zdrojáků.
- Skenování závislostí nástrojem (nemá smysl: `requirements: []`).
- Nastavení repozitáře na GitHubu (výchozí oprávnění `GITHUB_TOKEN`, rulesety) – API je ze session
  blokované; S-4 proto počítá s výchozím stavem.

---

## 3. Nálezy

### S-1 — 🔴 High — TASK-67: Basic-auth fallback nad neověřeným HTTPS vydá heslo komukoli, kdo odpoví

**Kde:** `api.py` `_basic_auth_permitted()` (507–519) a `_async_request()` (667–694).

**Co se děje.** `_basic_auth_permitted()` vrací `True` pro `protocol == https` bez ohledu na
`verify_ssl`. Při `verify_ssl=False` – což je výsledek auto-detekce u tovární self-signed
certifikace, tedy typická instalace – TLS šifruje, ale **neověřuje server**. První požadavek jde
bez přihlášení (Digest middleware, `preemptive=False`). Kdokoli na něj odpoví
`401 WWW-Authenticate: Basic`, dostane na opakovaný požadavek `Authorization: Basic base64(user:heslo)`.
Nezáleží na tom, jak má autentizaci nastavený skutečný interkom – challenge posílá ten, kdo odpovídá.

**Kdo může odpovídat.** Útočník na cestě v LAN (ARP/DNS spoofing), nebo – jednodušeji – kdokoli v
LAN, kdo pošle jednu SSDP zprávu s MAC interkomu (S-2): integrace si přepíše `host`, znovu se
načte a připojí se k útočníkovi.

**Dopad.** Heslo HTTP API účtu v otevřené podobě. Účet má obvykle *Switch – Control*, takže útočník
otevře dveře přímo přes API zařízení. RTSP probe navíc útočníkovi odevzdá Digest odpověď RTSP
účtu (offline brute-force).

**Proč to prošlo opravou S3 v 1.4.0.** S3 řešilo jen plaintext HTTP a bralo HTTPS jako bezpečné,
bez rozlišení ověřeného a neověřeného certifikátu. Testy
`test_basic_retry_requires_https_or_explicit_opt_in` a `test_basic_auth_permitted_over_https` tento
stav dokonce fixují.

**Doporučení.** Automatický Basic fallback jen při `verify_ssl=True`; při neověřeném certifikátu
stejný explicitní opt-in jako u HTTP (`allow_insecure`) a jasná chyba pro uživatele. Digest
nechat beze změny. **Otevřená otázka pro Jana** (task je proto nepřiřazený): user step nemá
`allow_insecure`, takže zařízení nabízející jen Basic na self-signed certifikátu by při setupu
skončilo na `cannot_connect`. Varianty: (a) přidat přepínač do user stepu po prvním selhání –
*doporučeno*, (b) vlastní chyba odkazující na Reconfigure, (c) nechat a jen logovat
WARNING – nedoporučeno, heslo stále uniká.

### S-2 — 🟠 Medium — TASK-68: tichý přepis hosta podle SSDP bez ověření identity zařízení

**Kde:** `config_flow.py` `async_step_ssdp()` (368–438).

**Co se děje.** Oznámení se páruje přes `serialNumber` (= MAC) s uloženou `mac_address`; při jiném
hostu se přepíše `entry.data[host]` a entry se znovu načte – **bez jediného požadavku na nový
host**. MAC je v LAN veřejná (ARP tabulka, neautentizované `/ssdp_server/description.xml` samotného
interkomu). Stačí tedy jedna SSDP NOTIFY / odpověď na M-SEARCH s výrobcem
„2N, part of Axis group“, touto MAC a vlastní presentation URL. TASK-49 přijal vzor HA core
(„trusts the local network“), ale důsledky nebyly rozebrané:

1. s `verify_ssl=False` odejde heslo API účtu na Basic challenge (S-1),
2. RTSP Digest handshake proběhne proti útočníkovi,
3. integrace přijme podvržené log události (zvonění, access-control události s libovolným jménem)
   a stav relé/IO,
4. ovládání dveří a zvonek přestanou fungovat do dalšího pravého oznámení nebo ručního Reconfigure;
   v logu zůstane jen jedna INFO řádka.

**Doporučení.** Host z SSDP převzít až po ověření, že jde o totéž zařízení: připojit se s uloženými
přihlašovacími údaji a TLS nastavením, přečíst `/api/system/info`, porovnat normalizovanou `macAddr`
s `entry.data[mac_address]` (a `serialNumber` s unique_id, pokud je sériové). Jinak oznámení
ignorovat a jednou zalogovat WARNING bez údajů. Ověřovací požadavek nesmí spadnout do Basic nad
neověřeným spojením (nezávisle na TASK-67). Přiřazeno `@copilot`.

### S-3 — 🟠 Medium — TASK-69: diagnostika vydává sériové číslo, MAC a SIP identity

**Kde:** `diagnostics.py` (`TO_REDACT_ENTRY` 185–192, `device`, `firmware`, `call_state`).

**Co se děje.** Rediguje se username, heslo, RTSP údaje, `grant_access_user` a `mac_address`
v `entry.data`/`options`, ale tytéž identifikátory odcházejí nezredigované jinde ve stejném dumpu:
`entry.data.serial_number` (`CONF_SERIAL_NUMBER` v `TO_REDACT_ENTRY` chybí), `device.system_info`
(`serialNumber`, `macAddr` přesně tak, jak je vrací `/api/system/info`), `device.phone_status`
(SIP identity účtů), `call_state.called_peer` (SIP peer / telefonní číslo posledního hovoru) a
`entry.title` (výchozí název je „<variant> <serial>“). TASK-49 AC #6 redigoval `mac_address` právě
proto, že uživatelé přikládají diagnostiku k veřejným issues.

**Doporučení.** Jedna redakční politika pro celý dump: sériové číslo a MAC všude, SIP identity a
peers, title pokud obsahuje sériové číslo. Verze firmware/hardware, varianta, capabilities, host a
port zůstávají (potřebné pro triage). Přiřazeno `@copilot`.

### S-4 — 🟡 Low — TASK-70: HACS/hassfest workflow bez `permissions:` a s akcemi na pohyblivých refech

**Kde:** `.github/workflows/hacs.yml` (`hacs/action@main`), `hassfest.yml`
(`home-assistant/actions/hassfest@master`), `e2e-pi.yml` (`actions/checkout@v4`).

**Co se děje.** Oba workflow nemají blok `permissions:`, takže při `push` na `main` běží s výchozími
právy `GITHUB_TOKEN` (zápis, pokud to nastavení repa neomezuje), a berou cizí akce z pohyblivých
větví. Kompromitovaný upstream ref by běžel s těmito právy při každém pushi na `main`. Oficiální
akce HA/HACS – nízká pravděpodobnost, levná oprava.

**Doporučení.** `permissions: contents: read` ve všech workflow, akce připnout na plný commit SHA
s verzí v komentáři, Dependabot pro `github-actions`. Změny v `.github/` reviewuje Jan
(`manual-path`, `@copilot-mac`).

---

## 4. Řetězec útoku, který mě vede k prioritě S-1 + S-2

```
útočník v LAN ── 1× SSDP NOTIFY (MAC interkomu, vlastní URL) ──▶ HA přepíše host, reload (S-2)
      │
      └─▶ HA pošle první požadavek bez auth ──▶ útočník: 401 Basic ──▶ HA: Basic base64(user:heslo) (S-1)
                                                                         │
                                                                         └─▶ /api/switch/ctrl na skutečném
                                                                             interkomu = otevřené dveře
```

Oprava **TASK-67** přeruší řetězec u hesla (útočník dostane jen Digest odpověď k offline lámání).
Oprava **TASK-68** zruší i DoS zvonku/dveří a podvržené události. Dohromady je to defense in depth.

---

## 5. Pozorování bez založení chyby

| ID | Pozorování | Hodnocení / doporučení |
|---|---|---|
| O-1 | `DEFAULT_VERIFY_SSL = False`; auto-detekce zkouší ověřené HTTPS první, ale u tovární certifikace skončí na neověřeném a uživatel se to dozví jen z reconfigure formuláře | Přijaté riziko (S1 z 1.4.0). Doporučení pro v1.6: *trust on first use* – uložit otisk certifikátu při setupu a dál ho pinovat (`aiohttp.Fingerprint`); MITM pak selže i bez vlastní CA. |
| O-2 | RTSP URL s heslem v `stream_source()` | Známé (S4). HA `stream` v logu údaje rediguje. Beze změny. |
| O-3 | RTSP Digest: `cnonce = md5(nonce)[:8]` je předvídatelný; `username`/`realm` jdou do hlavičky bez escapování | Kosmetika (MD5 vynucuje RTSP, S5). `secrets.token_hex(4)` a odmítnout uvozovky/CRLF v RTSP jménu. |
| O-4 | DEBUG logy obsahují celé payloady `/api/call/status` a seznamy peerů (SIP čísla) | Jen při zapnutém debug logu. Přijatelné. |
| O-5 | `camera.py` předává `MjpegCamera` jméno a heslo API účtu; vlastní fetch `MjpegCamera` by použil Basic bez ohledu na `allow_insecure`. Integrace ale přepisuje `async_camera_image` i `handle_async_mjpeg_stream`, takže je tato cesta mrtvá | Doporučení: údaje nepředávat vůbec (`username=None`), aby je budoucí refaktor nemohl oživit. Jednořádková změna, zvážit v rámci TASK-67. |
| O-6 | Firmware entita posílá každých 6 h `firmwarePackage` + `swVersion` na `update.2n.cz` (HA session s ověřeným TLS, `allow_redirects=False`, validace tvaru odpovědi, chybové texty bez URL) | Správně implementované. Jde o jediné spojení mimo LAN – stojí za větu v README („vypnutí = zakázat entitu update“). |
| O-7 | Služby `answer_call` / `hangup_call` / `grant_access`: standardní HA autorizace; `user` je volný řetězec, ale jde kódovaný jako query parametr, uuid se neloguje | Bez nálezu. |
| O-8 | Log kanál: jedna vadná událost nerozbije subscription; tajemství z událostí (`code`, `uid`, `authid`) se neukládají; jména uživatelů jdou do atributů entit (HA frontend escapuje) | Správně. |
| O-9 | CI/pipeline (TASK-22/23/33/46): `pull_request_target` bere workflow a `e2e/ci/*` z `main`, allowlist autora i spouštěče, brána na Pi, fork PR nikdy; patch z Copilota prochází kontrolou chráněných cest, symlinků, binárek, velikosti; tokeny oddělené (`ha2n-coder` vs. `ha2n-copilot`), reviewer output sanitizovaný; auto-merge jen opt-in | Threat model v `e2e/ci/README.md` odpovídá kódu. Zbytkové riziko (kód větve běží jako runner user, může zfalšovat check) je dokumentované a přijaté. TASK-38 (model/fw ve veřejném summary) zůstává otevřený. |
| O-10 | `e2e/e2elib/twon.py` používá `verify=False` a Basic fallback nad libovolným protokolem | Testovací nástroj v Janově LAN s read-only účtem. Přijatelné. |
| O-11 | Blueprint: `notify_service` je volný text do `service:` | Vlastní automatizace uživatele, HA validuje službu. Bez nálezu. |
| O-12 | Options flow: RTSP heslo se nikdy nepředvyplňuje; `verify_ssl` a `allow_insecure` mají srozumitelné popisy | Správně. |

---

## 6. Co je v pořádku (ať se to nezhorší)

- S1–S3 z 1.4.0 jsou v kódu: pořadí `HTTPS ověřené → HTTPS neověřené → HTTP`, WARNING při HTTP,
  Basic odmítnut nad plaintext HTTP, `allow_insecure` v reconfigure i runtime.
- Přihlašovací údaje nikdy v URL (`include_auth=True` se nikde nevolá), `MjpegCamera` je dostává
  zvlášť, `device_web_url` je bez údajů, firmware check neloguje URL.
- `grant_access` neloguje uuid uživatele; diagnostika rediguje hesla, RTSP a `grant_access_user`.
- Oddělení `entry.data` (identita) a `entry.options` (chování); reauth/reconfigure vždy vítězí.
- Životní cyklus log listeneru a idempotentní hangup.
- Repo hygiena: `e2e/.env`, `CLAUDE.local.md`, reporty v `.gitignore`; `.env.example` bez hodnot;
  `ci_summary.py` maskuje IP, MAC, hostnames, sériová čísla a hodnoty z env.

---

## 7. Doporučení k vydání 1.5.0

1. **TASK-67** – rozhodnout variantu UX (a/b), přiřadit a opravit **před vydáním**. Jediný nález,
   který končí heslem účtu s právem otevírat dveře.
2. **TASK-68** – opravit společně s TASK-67 (defense in depth; je přiřazený `@copilot`, headless
   kodér ho může vzít).
3. **TASK-69** – malá změna + testy, doporučuji do 1.5.0 (je v milestone).
4. **TASK-70** – mimo milestone, vydání neblokuje.
5. Do `CHANGELOG.md` 1.5.0 přidat sekci **Security** s popisem TASK-67/68/69 a doporučením
   uživatelům s vlastním certifikátem zapnout `verify_ssl` v Reconfigure.
6. Po uzavření TASK-67/68 přidat do `docs/IMPROVEMENTS.md` poznámku k S3 („HTTPS bez ověření
   certifikátu se počítá jako nezabezpečený transport“), ať zůstává jediný zdroj pravdy.
