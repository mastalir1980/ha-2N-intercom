# Návrh vylepšení – bezpečnost a možné chyby

Výsledek průchodu kódem (`custom_components/2n_intercom/`). Položky jsou seřazené
podle závažnosti. Jde o **návrhy** – nic z toho zatím není v kódu změněno.

Legenda závažnosti: 🔴 vysoká · 🟠 střední · 🟡 nízká / kosmetické.

> **Stav:** S1, S2 a S3 byly **implementovány** na větvi
> `security/secure-by-default-connection` (viz sekce „Bezpečnost" níže –
> každá položka má poznámku *Implementováno*). Položky B1–B6 zůstávají jako
> návrh.

---

## Bezpečnost

### 🔴 S1 — TLS verifikace je vypnutá a nelze ji zapnout při setupu
`const.py:46` `DEFAULT_VERIFY_SSL = False` a config flow ji při auto-detekci
**natvrdo** nastaví na `False`:

```python
# config_flow.py:213-220
api, ok = await self._async_try_connect(host, username, password, protocol, port,
                                         verify_ssl=False)
...
user_input[CONF_VERIFY_SSL] = False
```

Důsledek: i uživatel s platným certifikátem (vlastní CA / nahraný cert na 2N)
běží trvale bez ověření certifikátu serveru → integrace je náchylná na
**MITM**. To je u zařízení, které **otevírá dveře a vrací heslo**, podstatné.

**Návrh:**
- Při auto-detekci zkusit `verify_ssl=True` jako první, a teprve při selhání
  spadnout na `False` (a v UI to označit jako „nezabezpečeno").
- Default ponechat `False` kvůli self-signed certům 2N, ale dát do options/reconfigure
  jasný přepínač + varování v `strings.json`.
- Reconfigure flow přepínač `verify_ssl` už má (`config_flow.py:506`) – stačí
  ho zpřístupnit i v iniciálním flow.

> ✅ **Implementováno:** auto-detekce v `async_step_user` teď zkouší kandidáty
> v pořadí `HTTPS:443 verify=True → HTTPS:443 verify=False → HTTP:80` a uloží
> `verify_ssl` podle vítěze. Uživatel s platným certifikátem dostane ověřené
> spojení. Pokryto testy `test_user_step_*` v `tests/test_config_flow.py`.

### 🔴 S2 — Fallback na HTTP (port 80) posílá přihlašovací údaje v plaintextu
`config_flow.py:209-212` zkouší `HTTPS:443`, pak `HTTP:80`. Pokud HTTPS selže
(např. zařízení má HTTPS dočasně nedostupné), setup tiše použije **HTTP** a
Digest/Basic autentizace poteče po nešifrovaném spojení.

**Návrh:** HTTP fallback povolit jen jako vědomou volbu (zaškrtávátko
„allow insecure HTTP"), ne automaticky. Minimálně logovat `WARNING`, když se
připojení ustálí na HTTP.

> ✅ **Implementováno:** HTTP je až poslední kandidát auto-detekce a když
> zvítězí, integrace loguje `WARNING` o nešifrovaném přenosu. Plaintextový
> únik hesla je navíc uťat na úrovni autentizace (viz S3). Pokryto testem
> `test_user_step_http_is_last_resort`.

### 🟠 S3 — Basic-auth fallback odhalí heslo
`api.py:425-433, 558-568` – při `401` s `Basic` challenge se pošle
`Authorization: Basic base64(user:pass)`, což je vratné. V kombinaci s S1/S2
(neověřené TLS nebo HTTP) to znamená reálný únik hesla.

**Návrh:** Basic fallback nechat povolený jen když `verify_ssl=True` nebo
`protocol=https`; jinak logovat varování. 2N s firmwarem ≥ 2.x podporuje
Digest, takže Basic by měl být skutečně jen nouzový.

> ✅ **Implementováno:** `TwoNIntercomAPI._basic_auth_permitted()` povolí Basic
> fallback nad HTTPS, ale nad plaintextovým HTTP ho **odmítne** (vrátí 401 →
> `TwoNAuthenticationError`) a zaloguje `WARNING`. Vědomé povolení přes nový
> přepínač `allow_insecure` (default vypnuto, dostupný v reconfigure flow).
> Digest cesta zůstává netknutá. Pokryto testy `test_basic_auth_*`.

> **TASK-67 correction:** unverified HTTPS (`verify_ssl=False`) also counts as
> insecure: encryption alone does not authenticate the server. Basic fallback
> now requires verified HTTPS or the existing explicit `allow_insecure` opt-in
> in Reconfigure. Refusal raises `TwoNInsecureAuthRefusedError`, with a warning,
> a dedicated setup/reauth/reconfigure error and a runtime Repair issue.
> Initial setup has no opt-in; use Digest or a trusted certificate instead.
> Existing Basic installations using unverified HTTPS must fix the device or
> explicitly accept the risk in Reconfigure. Digest is unchanged.

### 🟡 S4 — RTSP creds v URL předané ffmpegu
`api.py:1773-1788` `get_rtsp_url_with_credentials()` vrací URL včetně hesla,
které jde do `stream_source()` → ffmpeg. Heslo se může objevit v ffmpeg debug
logu. U protokolu RTSP je to běžné a těžko se tomu vyhne; jen evidovat jako
známé riziko (HTTP cesta to už řeší oddělením creds, RTSP ne).

### 🟡 S5 — MD5 v RTSP digestu
`api.py:1464-1481` používá `hashlib.md5` pro RTSP Digest. To je dané RTSP/RFC 2617
a nelze změnit jednostranně; jen poznámka, že je to očekávané, ne nález.

---

## Možné chyby a robustnost

### 🟠 B1 — Naivní `datetime.now()` bez časové zóny
`coordinator.py` (`_last_ring_time`, `_last_motion_time`, snapshot cache) i
`api.py:8` používají `datetime.now()`. Hodnoty se exportují přes `.isoformat()`
do atributů entit (`binary_sensor.py:125`, `:242`) **bez offsetu** → v jiné TZ
nebo přes DST můžou být matoucí a HA konvence je `homeassistant.util.dt.utcnow()`.

**Návrh:** přejít na `dt_util.utcnow()` (resp. `dt_util.now()`), aby timestampy
nesly tz a srovnání byla konzistentní s HA.

### 🟠 B2 — Polling fetchuje i „statická" caps každý cyklus
`coordinator.py:799-803` – `switch_caps` se přes komentář „safety net" načítá
**každý poll**, ačkoliv `async_initialize_static_caches` je deklaruje jako
statická a navíc je obnovuje `ConfigurationChanged` event. Při `scan_interval=2 s`
(`SCAN_INTERVAL_MIN`) to znamená zbytečné requesty na zařízení.

**Návrh:** `switch_caps` v poll cyklu vynechat (spoléhat na event +
jednorázové načtení), nebo refetchovat jen jednou za N cyklů. Pro `io_caps` už
je to správně (`if self._io_caps is None`).

### 🟡 B3 — `_async_request_without_auth` zakládá session na každé volání
`api.py:592-596` vytváří nový `ClientSession` + `TCPConnector` pro každý
veřejný MJPEG probe. Volá se sice jen při setupu, ale je to anti-pattern oproti
sdílené HA session.

**Návrh:** použít sdílenou session (probe bez auth lze udělat i přes existující
session s `auth=None`), nebo aspoň jasně omezit na jediné volání.

### 🟡 B4 — `MjpegCamera` „mjpeg" režim ve skutečnosti streamuje snapshoty
`camera.py:208-221` přepisuje `handle_async_mjpeg_stream` tak, že **vždy**
skládá stream z opakovaných JPEG snapshotů (kvůli reverse-proxy bufferingu),
i když je vybrán nativní MJPEG transport. Funkčně OK, ale `mjpeg_available` /
advertovaný režim neodpovídá realitě přenosu.

**Návrh:** v dokumentaci/atributech odlišit „selected_mode=mjpeg" od skutečného
„snapshot-stream" fallbacku, ať uživatel ví, co běží.

### 🟡 B5 — Závislost na nové `aiohttp.DigestAuthMiddleware` bez deklarace verze
`__init__.py:356` a `api.py:415` používají `aiohttp.DigestAuthMiddleware`
(novější aiohttp). `manifest.json` má `requirements: []` a žádný
`min_ha_version`. Na starší HA/aiohttp integrace spadne při importu.

**Návrh:** doplnit do README/manifest minimální podporovanou verzi HA, případně
graceful fallback, pokud middleware není dostupný.

### 🟡 B6 — Tiché potlačení chyb širokým `except Exception`
Napříč `api.py`/`coordinator.py` je mnoho `except Exception ... return {}/None/False`.
Je to záměrné (degradace místo pádu) a logované, ale maskuje to např. chyby
parsování. Není to bug, jen doporučení zúžit typy tam, kde to jde.

---

## Co je naopak v pořádku (a nedělat horší)

- Oddělení `entry.data` (identita) vs `entry.options` (chování) je čisté.
- HTTP cesta **nedává creds do URL** a předává je `MjpegCamera` zvlášť – správně.
- Diagnostika **rediguje** username/password i RTSP creds (`diagnostics.py:23`).
- Idempotentní hangup a disambiguace 2N kódu 14 jsou dobře ošetřené.
- Životní cyklus log-listeneru (background task + STOP listener) je korektní.
- Dynamické přidávání/odebírání relé přes entity registry je správně.

---

## Doporučené pořadí prací

1. ~~**S1 + S2 + S3** (TLS/HTTP/Basic)~~ – ✅ **hotovo** (větev
   `security/secure-by-default-connection`, testy v `tests/`).
2. **B1** (tz-aware timestampy) – malá změna, zlepší korektnost atributů.
3. **B2** (polling caps) – úspora requestů na zařízení.
4. Zbytek (B3–B6) dle kapacity.

> Můžu kteroukoli zbývající položku (B1–B6) rovnou implementovat – stačí říct
> kterou.
