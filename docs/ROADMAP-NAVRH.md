# Návrh backlogu — ha-2N-intercom

Návrh všeho, co by stálo za to implementovat, z pohledu (a) možností 2N HTTP API,
které integrace zatím nevyužívá, a (b) moderních platforem a konvencí Home Assistanta.
Zatím jen návrh — nic z toho není založeno jako task v `backlog/`.

Priorita: **P1** = největší přidaná hodnota / malé riziko · **P2** = výrazné rozšíření ·
**P3** = nice-to-have / závislé na licenci či HW.

---

## Co už je hotové (pro kontext)

Kamera (JPEG/MJPEG/RTSP), event-driven doorbell + stavy přes `log/subscribe`,
relé jako switch/cover s reálným stavem, answer/hangup služby, SIP + call-state
senzory, reauth/reconfigure/options flow, HomeKit mapping, diagnostika.
Používané endpointy: `system/info|caps`, `call/*`, `camera/*`, `switch/*`, `io/*`,
`phone/status`, `log/*`, `dir/query`. Bezpečnostní položky S1–S3 z
[IMPROVEMENTS.md](IMPROVEMENTS.md) jsou implementované na větvi
`security/secure-by-default-connection`.

---

## A. Přístupový systém a události (2N API: `log/subscribe`)

Dnes se odebírá jen call/switch/IO/registration/config + `MotionDetected`.
Log kanál ale umí podstatně víc a je to největší nevyužitý potenciál integrace —
interkom je i přístupová jednotka, ne jen zvonek.

| # | Položka | Priorita | Poznámka |
|---|---|---|---|
| A1 | **Přihlásit se k access událostem**: `CardEntered`, `CodeEntered`, `MobKeyEntered` (WaveKey/BLE), `FingerEnteredData`, `UserAuthenticated`, `AccessTaken` | **P1** | Vyžaduje čtečku/klávesnici na zařízení; eventy chodí stejným kanálem, minimální změna v koordinátoru |
| A2 | **HA `event` entity** pro doorbell (device class `doorbell`) a pro access události | **P1** | Moderní HA konvence — `event` platforma místo krátkého pulzu binary sensoru; binary sensor ponechat pro zpětnou kompatibilitu |
| A3 | **Události na HA event bus** (`2n_intercom_event`) s atributy (uuid uživatele, jméno z `dir/query`, typ pověření, směr in/out, výsledek) | **P1** | Umožní automatizace typu „přišla konkrétní osoba" a napojení na HA `person` |
| A4 | **Bezpečnostní události**: `TamperSwitchActivated`, `UnauthorizedDoorOpen`, `DoorOpenTooLong`, `SilentAlarm`, `LoginBlocked` | **P1** | Binary sensory / event entity s device class `tamper`, `door`, `safety`; skvělý materiál pro alarmové automatizace |
| A5 | **`DoorStateChanged`** — skutečný stav dveří z dveřního senzoru | **P2** | Řeší known limitation „no gate position feedback" tam, kde je senzor zapojený; cover pak nemusí být optimistický |
| A6 | **Device triggers/conditions** (`device_automation`) pro zvonění, access granted/denied, tamper | **P2** | Automatizace klikatelné v UI bez znalosti entity_id |
| A7 | **`KeyPressed`/`KeyReleased`** — tlačítka a klávesnice jako eventy | **P3** | Např. „dlouhý stisk tlačítka 2 = rozsviť zahradu" |

## B. Ovládání přístupu (2N API: `accesspoint`, `dir`, `switch`)

| # | Položka | Priorita | Poznámka |
|---|---|---|---|
| B1 | **Služba `grant_access`** přes `/api/accesspoint/grantaccess` místo surového `switch/ctrl` | **P1** | Otevření se zapíše do access logu zařízení s auditní stopou (kdo/odkud), na rozdíl od přímého sepnutí relé |
| B2 | **Volitelná `lock` platforma** pro dveřní relé (vedle switche) | **P2** | Lepší sémantika v HA i HomeKit/Alexa („odemkni dveře"); dřív odstraněná lock platforma se vrátí v čisté podobě nad auto-detekcí relé |
| B3 | **Podpora `hold`/`release` režimu relé** — trvalé otevření (např. brána dokořán, režim „párty") | **P2** | `switch/ctrl` akce hold/release; v HA jako přepínač „drž otevřeno" |
| B4 | **Správa dočasných přístupových kódů** — služby `set_access_code` / `delete_access_code` nad `dir/update` | **P3** | Use-case: jednorázový PIN pro řemeslníka z HA automatizace; pozor na bezpečnostní review |
| B5 | **Security relay / secured mode** — detekce a korektní ovládání bezpečnostního relé | **P3** | Jen pokud zařízení má 2N Security Relay |

## C. Kamera a audio

| # | Položka | Priorita | Poznámka |
|---|---|---|---|
| C1 | **`image` entita „poslední zazvonění"** — snímek uložený v okamžiku ring eventu | **P1** | HA `image` platforma; notifikace i dashboard pak mají snímek z momentu zvonění, ne aktuální |
| C2 | **go2rtc / WebRTC live view** — využít nativní go2rtc v HA (2024.11+) pro nízkolatenční stream | **P2** | Výrazně lepší latence než MJPEG/HLS; go2rtc umí RTSP restream i bez licence transcodovat snapshoty |
| C3 | **Obousměrné audio** — WebRTC/SIP backchannel (go2rtc `webrtc` + SIP, případně ONVIF Profile T backchannel) | **P2** | Řeší hlavní known limitation; technicky nejnáročnější položka, chce spike/prototyp jako první krok |
| C4 | **Přepínání kamer za běhu** — `select` entita interní/externí kamera místo restartu entry | **P3** | Dnes `camera_source` jen v options |
| C5 | **Audio test** (`/api/audio/test`) — `button` entita + výsledek jako diagnostický sensor | **P3** | Pravidelný self-test reproduktoru/mikrofonu z HA automatizace |

## D. Správa zařízení (2N API: `system`, `firmware`, `config`)

| # | Položka | Priorita | Poznámka |
|---|---|---|---|
| D1 | **`update` entita pro firmware** — kontrola dostupné verze + instalace z HA | **P2** | 2N API `firmware` skupina; HA `update` platforma s release notes; velká údržbová hodnota u více zařízení |
| D2 | **`button` restart zařízení** (`/api/system/restart`) | **P2** | Triviální, hodí se při diagnostice |
| D3 | **Zálohování konfigurace** — služba `backup_config` stahující `/api/config` do HA | **P2** | Automatická týdenní záloha konfigurace interkomu; restore nechat manuální |
| D4 | **Diagnostické senzory navíc**: uptime, firmware verze jako atribut zařízení, stav log subscription | **P3** | Stav subscription pomůže ladit „doorbell not triggering" |
| D5 | **Repairs platforma** — `issue` při: firmwaru < 2.40, chybějící RTSP licenci se zvoleným `rtsp` režimem, HTTP bez šifrování, zablokovaném účtu | **P2** | Navazuje na S1–S3; uživatel dostane návod k nápravě přímo v HA UI |

## E. Discovery a onboarding

| # | Položka | Priorita | Poznámka |
|---|---|---|---|
| E1 | ~~**DHCP discovery** — `dhcp` matcher v manifestu na 2N OUI (7C:1E:B3)~~ | ~~P1~~ | **Vyřazeno** (rozhodnutí 2026-08-30 — není potřeba) |
| E2 | **mDNS/ONVIF discovery** jako doplněk | **P3** | Podle toho, co zařízení reálně inzerují na síti |
| E3 | **Zjištění licencí/capabilities při setupu** (`system/caps`) a schování nedostupných options | **P2** | Uživatel bez RTSP licence neuvidí RTSP volby; méně chybných konfigurací |

## F. Kvalita, distribuce, tech-debt

| # | Položka | Priorita | Poznámka |
|---|---|---|---|
| F1 | **Dokončit B1–B6 z [IMPROVEMENTS.md](IMPROVEMENTS.md)** (tz-aware timestampy, caps v poll cyklu, sdílená session, MJPEG režim vs. realita, deklarace min. verze HA/aiohttp, zúžení `except`) | **P1** | Už zanalyzováno, malé, bezpečné změny |
| F2 | **Merge větve `security/secure-by-default-connection`** + release 1.4.0 | **P1** | S1–S3 hotové vč. testů; nenechat je zestárnout na větvi |
| F3 | **CI na GitHub Actions**: unittest/pytest, `validate.py`, hassfest, HACS action | **P1** | `.github/` existuje, ale bez plné pipeline; podmínka pro další body |
| F4 | **Zařazení do HACS default repozitáře + home-assistant/brands** | **P2** | Instalace bez custom repository, oficiální logo/ikona v UI |
| F5 | **Přechod testů na `pytest-homeassistant-custom-component`** + coverage | **P2** | Standard ekosystému; umožní testovat platformy proti reálnému HA test harnessu |
| F6 | **Další blueprinty**: „kdo přišel" notifikace se jménem, tamper alarm, dveře dlouho otevřené, brána nechána otevřená, dočasný PIN | **P2** | Levná viditelná hodnota, staví na sekci A |
| F7 | **Dlouhodobě: kandidát na HA core integraci** | **P3** | `quality_scale: platinum` už deklarován; core přinese distribuci všem uživatelům HA, ale i závazek údržby |

## G. Mimo scope (vědomě)

- **My2N / cloud** — integrace je záměrně `local_push`; cloud neřešit.
- **Lift control, mass-notify, multi-tenant directory UX** — mimo use-case rodinného domu (viz README); případně až po poptávce z komunity.
- **Automation API (licencované)** — HTTP API pokrývá vše potřebné; duplikovalo by logiku.

---

## Doporučené pořadí (první iterace)

1. **F2 + F1** — merge security větve, doklepnout tech-debt B1–B6, release.
2. **F3** — CI, ať další práce jede na zelené.
3. **A1–A4 + B1** — access události + `event` entity + `grant_access`: největší funkční skok, jedna souvislá oblast (koordinátor + nová platforma).
4. **C1 + E1** — snímek při zazvonění a DHCP discovery: malé, viditelné.
5. **D5 + E3** — repairs a license-aware options: dotáhne UX konfigurace.
6. Pak podle chuti: **C2/C3** (go2rtc, two-way audio — nejdřív spike), **D1–D3**, **B2/B3**.

> **Stav 2026-08-30:** Všechny P1 položky kromě E1 (DHCP — vyřazeno) jsou založené
> jako tasky `task-1` až `task-9` v `backlog/tasks/` včetně acceptance kritérií
> a závislostí. Instrukce pro implementaci: `.github/copilot-instructions.md`.
