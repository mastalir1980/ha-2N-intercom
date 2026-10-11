# E2E pipeline — ha-2n-intercom

Automatické ověření integrace na **skutečném HA a skutečném interkomu**. Běží na Macu,
nasazuje na **staging HA** na Rob's Berry (Pi) a chyby zakládá jako bugy v Backlog.md.

```
Mac (e2e/e2e.sh run / launchd 03:30)
 ├─ 1. unit testy + validate.py            (lokálně)
 ├─ 2. deploy git ref ──ssh──▶ Pi: ~/ha-staging  (HA kontejner ha-staging, port 8124)
 │                                   └─ 2N integrace ──HTTPS─▶ IP Force 2.0 (domácí, fw 3.3)
 ├─ 3. pytest e2e/tests: stav v HA  ⇄  přímé dotazy na 2N API (ground truth)
 └─ 4. při chybě: claude -p (agent/triage.md) ─▶ backlog task create/edit  (type bug, label e2e)
```

Produkční HA na Pi (`~/homeassistant`, port 8123) pipeline **nikdy nemění**.

## Bezpečnost

| Běh | Co dělá s interkomem |
|---|---|
| `e2e/e2e.sh run`, `e2e/e2e.sh wip`, noční běh | jen čte (stav relé, IO, SIP, snapshot, reload entry) |
| `e2e/e2e.sh relays` | **fyzicky spíná** relé z `E2E_RELAY_NUMBERS`, s potvrzením |

Agent smí jen číst soubory a volat `backlog` + read-only `git`. Kód neupravuje.

## Jednorázové nastavení

1. `e2e/e2e.sh setup` — venv, Backlog.md CLI, vytvoří `e2e/.env`.
2. Vyplň `e2e/.env`: `PI_SSH` (funkční `ssh` bez hesla, klíč), IP a účet interkomu, čísla relé
   pro ruční test. Na interkomu použij **vlastní HTTP API účet** (např. `e2e`, *Services → HTTP API →
   Accounts*), ne admin účet webu. Potřebná práva:
   - **čtení (monitoring):** System, Switch, I/O, Phone/Call, Camera, Logging (události);
   - **ovládání (control):** Switch, I/O, Phone/Call — bez Switch control nejde ruční test relé.
   Konfiguraci interkomu pipeline nemění. Pokud má interkom vypnuté HTTP (jen HTTPS), nech
   `INTERCOM_PROTOCOL=https`. Chybějící právo se v testech projeví jako `401` / `PermissionError`.
   Po změně účtu spusť `e2e/e2e.sh reset-entry`, aby si staging HA vzal nové údaje.
3. `e2e/e2e.sh bootstrap` — na Pi založí `~/ha-staging`, spustí staging HA, provede onboarding
   (uživatel `e2e`), uloží long-lived token do `.env` a přes config flow přidá interkom.
4. `e2e/e2e.sh run` — první běh.
5. `e2e/e2e.sh schedule` — noční běh v 03:30 (jen když se změnil `origin/main`,
   firmware interkomu nebo vyšla nová verze HA).

## Denní použití

| Příkaz | Kdy |
|---|---|
| `e2e/e2e.sh wip` | otestovat rozpracovanou změnu (working tree) |
| `e2e/e2e.sh run` | otestovat HEAD |
| `e2e/run.sh --ref main` | konkrétní větev/commit |
| `e2e/e2e.sh relays` | před releasem, ručně, u dveří |
| `e2e/e2e.sh report` | poslední výsledek + co agent založil |
| `/e2e` v Claude Code (jednou: `e2e/e2e.sh install-slash-command`) | totéž interaktivně, agent rovnou hlásí task id |

Reporty: `e2e/reports/<čas>/` (`summary.json`, `context.json` s verzemi HA a firmwaru,
`junit.xml`, logy, `triage.md`). `e2e/reports/latest` ukazuje na poslední běh.

## Přidání testu k nové funkci

Každá nová funkce = test v `e2e/tests/` ve stylu „HA říká X ⇄ 2N API říká X“.
Čtecí testy jsou default; cokoli, co fyzicky něco spíná, označ `@pytest.mark.relay`.
Klient na 2N (`e2elib/twon.py`) je schválně nezávislý na `api.py` integrace.

## Řešení potíží

- **deploy visí na ssh** — `ssh $PI_SSH true` musí projít bez hesla (BatchMode).
- **staging HA po resetu nechce token** — smaž `HA_TOKEN` v `.env` a spusť `e2e/e2e.sh bootstrap`.
- **úplně čistý staging** — na Pi `cd ~/ha-staging && docker compose down && rm -rf config/.storage`,
  pak smaž `HA_TOKEN` a `HA_E2E_PASSWORD` v `.env` a znovu bootstrap.
