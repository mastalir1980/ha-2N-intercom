# E2E na Pi pro každý PR (self-hosted runner)

První stavební kámen autonomní pipeline (TASK-22). Agent, který kóduje mimo domácí síť
(virtuál), pushne větev a otevře PR. Pi, které vidí na interkom, větev otestuje a výsledek
pověsí k PR jako check `e2e-pi`. **Mezi virtuálem a domovem není potřeba žádná VPN.** Pi se jen
samo připojuje ven na GitHub.

```
VM (agent)  ──push / PR──▶  GitHub  ◀──runner se ptá ven──  Pi (robsberry)
                                     ──job──▶  pr-e2e.sh
                                                 ├─ sudo -u <staging-user> ha2n-staging lock/deploy/logs
                                                 ├─ pytest z PR větve (read-only 2N účet)
                                                 └─ očištěný souhrn → check u PR; plné logy zůstanou na Pi
```

## Bezpečnostní model

Repo je veřejné a každý, kdo má právo pushovat, může napsat workflow, které se na self-hosted
runneru spustí. Proto bereme **uživatele runneru (`ha2n-ci`) jako nedůvěryhodného** a ochranu
stavíme jinde:

| Vrstva | Co chrání | Jak |
|---|---|---|
| 2N účet jen pro čtení | dveře a bránu | E2E i staging integrace používají HTTP API účet, který má u všech služeb jen *Monitoring*, žádný *Control*. Kód z větve tak relé nesepne, ani kdyby chtěl. |
| Žádný docker pro `ha2n-ci` | produkční HA na stejném Pi | Uživatel runneru není ve skupině `docker`. Na staging se dostane jen přes `/usr/local/sbin/ha2n-staging`. |
| Pevný helper | staging, prod, zámek | `ha2n-staging` je ve vlastnictví root a běží přes sudoers jako staging uživatel. Odmítne nehex SHA, commity mimo větve repa (forky), deploy bez zámku a cokoli mimo `ha-staging`. Změna helperu se projeví až po ručním `install-pi.sh`. |
| Compose a deploy mimo dosah větve | produkční HA a hostitel | Helper používá vlastní compose `/etc/ha2n-ci/staging-compose.yml` (root, kontrolovaný při instalaci), ne `~/ha-staging/docker-compose.yml`. Před deployem staging zastaví a soubory maže a rozbaluje v jednorázovém kontejneru, který vidí jen `config/`. Symlink, který tam nechal kód z předchozí větve, tak nedosáhne na hostitele. |
| Brána na Pi (job hook) | proti cizím workflow | Runner před každým jobem spustí `/usr/local/lib/ha2n-ci/job-started.sh` (root). Povolí jen `e2e-pi.yml` z `main`, událost `pull_request_target` nebo `workflow_dispatch`, PR z tohoto repa do `main` a autora i spouštěče ze seznamu `/etc/ha2n-ci/allowed-actors`. Workflow přidané ve forku nebo na jiné větvi Pi odmítne, i když na GitHubu někdo klikne na *Approve and run*. |
| Workflow z `main` | integritu checku | `pull_request_target` bere workflow a `e2e/ci/*` vždy z `main`. Spustí se jen pro PR z větví tohoto repa a jen pro lidi v `E2E_PI_ACTORS`. |
| Očištěný výstup | data z domácí sítě | Do veřejného logu jde jen stav, verze a názvy padlých testů. IP, MAC, hostname, sériová čísla a hodnoty z `e2e.env` se maskují. |
| Sdílený zámek | staging | Mac, noční běh (Hermes) i CI používají jeden zámek `~/ha-staging/.e2e.lock`, takže dva deploye se nikdy nepřekryjí. |

**Zbytková rizika (vědomě přijatá pro fázi 1):**
- Kód z větve běží pod stejným uživatelem jako runner. Vidí domácí síť, staging HA token
  a read-only 2N účet (včetně kamery a logů). Může poškodit instalaci runneru a **zfalšovat
  výsledek checku** (přepsat skript, který právě běží).
- **Zelený `e2e-pi` proto nikdy není sám o sobě důvodem k auto-merge.** Merge vyžaduje i nezávislé
  review a GitHub-hosted CI.
- Další zpevnění (fáze 2): testy pod samostatným uživatelem bez zápisu do runneru, ephemeral
  runner a nftables egress pro `ha2n-ci` (jen GitHub, `127.0.0.1:8124` a interkom).

**Pravidlo:** změny v `.github/` a `e2e/ci/` vždy reviewuje člověk (nikdy auto-merge).

## Instalace (jednorázově)

### 0. Dostat to na `main`
`pull_request_target` se spouští jen z workflow, který už leží na výchozí větvi. Commitni tyhle
soubory a zamerguj je do `main`.

### 1. Read-only účet na interkomu
Ve webu interkomu: **Services → HTTP API → Account**. Založ nový účet, třeba `ha-e2e-ro`, a zapni
mu *Monitoring* u služeb System, Switch, I/O, Phone/Call, Camera a Logging. *Control* nech všude
vypnutý.

Pak na staging integraci přepni na tento účet. Na Macu dej do `e2e/.env` do `INTERCOM_USER` /
`INTERCOM_PASSWORD` read-only účet a spusť `bash e2e/e2e.sh reset-entry`. Od té doby všechny
automatické běhy (Mac, noc, CI) testují read-only.

> Ruční relé testy (`e2e.sh relays`) pak potřebují dočasně účet s *Control*: přepnout `e2e/.env`,
> `reset-entry`, pustit relé testy a pak zase vrátit read-only účet a `reset-entry`.

### 2. Instalace na Pi
```bash
ssh mastix@robsberry.local
cd ~/ha-2n-intercom && git pull --ff-only
sudo bash e2e/ci/install-pi.sh
```
Skript založí uživatele `ha2n-ci` (bez dockeru), nainstaluje helper, sudoers, `/etc/ha2n-ci/*`,
venv a složku na reporty. Na konci sám ověří, že `ha2n-ci` docker nevidí.

### 3. Vyplnit `/etc/ha2n-ci/e2e.env`
```bash
sudo nano /etc/ha2n-ci/e2e.env
```
- `INTERCOM_HOST`, `INTERCOM_PROTOCOL`, `INTERCOM_VERIFY_SSL` = stejné jako na Macu,
- `INTERCOM_USER` / `INTERCOM_PASSWORD` = **read-only účet** z kroku 1,
- `HA_TOKEN` (a `HA_E2E_PASSWORD`) = hodnoty pro staging HA z `e2e/.env` na Macu,
- `HA_URL` nech `http://127.0.0.1:8124`, `E2E_RELAY_NUMBERS` nech prázdné.

### 4. Zaregistrovat runner
Na GitHubu: **Settings → Actions → Runners → New self-hosted runner → Linux**. Architekturu
ověř na Pi příkazem `uname -m`: `aarch64` = ARM64, `armv7l` = ARM. GitHub ukáže příkazy ke
stažení a token. Spusť je **jako `ha2n-ci`**:
```bash
sudo -u ha2n-ci -H bash
mkdir -p /var/lib/ha2n-ci/actions-runner && cd /var/lib/ha2n-ci/actions-runner
# … curl + tar řádky z GitHubu …
./config.sh --url https://github.com/mastalir1980/ha-2N-intercom --token <TOKEN> \
  --name robsberry --labels ha2n-pi --unattended
exit
cd /var/lib/ha2n-ci/actions-runner && sudo ./svc.sh install ha2n-ci && sudo ./svc.sh start
```

Pak **znovu spusť `sudo bash e2e/ci/install-pi.sh`**. Skript runner najde, zapne v jeho `.env`
bránu (`ACTIONS_RUNNER_HOOK_JOB_STARTED`), převede `.env` na roota a službu restartuje.

### 5. Nastavení repa na GitHubu
- **Settings → Secrets and variables → Actions → Variables:** `E2E_PI_ACTORS` = `["mastalir1980"]`
  (později přidat účet agenta),
- **Settings → Actions → General → Fork pull request workflows:** *Require approval for all external contributors*
  (nejpřísnější volba).
  U cizího PR, který mění `.github/`, nikdy neklikej na *Approve and run* (brána na Pi ho stejně odmítne).
- **Settings → Rules → Rulesets → New branch ruleset** pro `main`: *Restrict deletions*, *Block force
  pushes*, *Require a pull request before merging* + *Require review from Code Owners*.
  `.github/CODEOWNERS` pak u změn v `.github/`, `e2e/ci/`, `e2e/scripts/`, `e2e/run.sh`,
  `e2e/nightly.sh` a `e2e/staging/` vyžaduje tvoje schválení. Plně to začne fungovat, až agent
  pushuje pod vlastním účtem.
- Seznam povolených lidí je na dvou místech a musí sedět: proměnná `E2E_PI_ACTORS` na GitHubu
  a `/etc/ha2n-ci/allowed-actors` na Pi. Rozhoduje to na Pi.
- **Registrační token** vezmi v UI (platí 1 hodinu) a předej ho jednorázově. Na Pi nedávej `gh`
  přihlášené tvým účtem: agent na Pi by měl admin práva k repu.

**Noční běh** (`nightly.sh`) od teď nasazuje jen `main` (proměnná `E2E_NIGHTLY_BRANCHES`).
Běží s plnými právy dockeru, takže nesmí nasazovat cizí větve. PR a větve testuje runner.

## První experiment
1. Před testem si poznamenej start produkční HA: `docker inspect -f '{{.State.StartedAt}}' homeassistant`.
2. Odkudkoli (Mac nebo VM) vytvoř větev s triviální změnou, třeba komentář v `README.md`, pushni
   ji a otevři PR.
3. U PR se má objevit check **e2e-pi**. V záložce Summary je souhrn, plné logy jsou na Pi
   v `/var/lib/ha2n-ci/reports/latest/`.
4. Ověř, že `StartedAt` produkční HA je pořád stejný.

Ruční spuštění: **Actions → E2E on the Pi → Run workflow**, zadej plné SHA commitu z větve repa.

## Provoz
- reporty: `/var/lib/ha2n-ci/reports/` (posledních 50), `latest` je symlink na poslední,
- kdo drží staging: `sudo -u ha2n-ci sudo -n -u mastix /usr/local/sbin/ha2n-staging status`,
- logy runneru: `journalctl -u 'actions.runner.*' -f`,
- po změně `e2e/ci/ha2n-staging` nebo `install-pi.sh` znovu spustit `sudo bash e2e/ci/install-pi.sh`.
