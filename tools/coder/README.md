# Headless kodér na virtuálu (TASK-23)

Druhá polovina autonomní pipeline. Na tvůj pokyn („vezmi TASK-12“) udělá virtuál z připraveného
Backlog úkolu PR. E2E na Pi (check `e2e-pi`, TASK-22) ho pak otestuje. **Merguješ vždycky ty.**

```
ty → Hermes (VM): „vezmi TASK-12“
  sudo -u ha2n-coder ha2n-run-task TASK-12          (orchestrátor, má token k repu)
    ├─ kontrola: úkol je To Do, přiřazený @copilot, závislosti hotové
    ├─ sudo -u ha2n-copilot sandbox.sh …             (pískoviště, BEZ tokenu k repu)
    │    čistý klon → Copilot CLI implementuje → unit testy / validate.py (Python 3.12)
    │    → ven jde jen patch
    ├─ patch: žádné chráněné soubory, max. 40 souborů / 2500 řádků → větev task-12-… z main
    ├─ push + PR (štítek agent) pod tvým účtem
    ├─ čeká na checky (e2e-pi, hassfest, HACS) → když padnou, log jde zpět Copilotovi (max. 3 kola)
    └─ zelené checky → nezávislé review druhým modelem (TASK-33) → komentář v PR s verdiktem;
       blokující nálezy jdou zpět kodéru (1 kolo `review-fix-1`) → checky → znovu review
  → stav: ha2n-task-status   → Hermes ti napíše výsledek (včetně verdiktu review) a odkaz na PR
```

## Bezpečnost

| Kdo | Co smí | Co nesmí |
|---|---|---|
| `hermes` | spustit `ha2n-run-task` a `ha2n-task-status` (sudo) | číst tokeny, sahat do klonů |
| `ha2n-coder` (orchestrátor) | token k repu, git push, `gh pr create/comment` | spouštět kód z repa; volá jen git, gh, backlog |
| `ha2n-copilot` (pískoviště) | Copilot, editace kódu, testy | token k repu; `git push`, `gh` a `url` má Copilot zakázané |

- **Token k repu** (fine-grained, jen `ha-2N-intercom`): Contents + Pull requests RW, **bez Workflows
  a Administration**. Na `.github/workflows/` nesáhne a nastavení repa nezmění.
- **Token pro Copilot:** jen *Copilot Requests*, žádná práva k repům.
- **Chráněné cesty** v patchi zastaví běh ještě před pushem: `.github/`, `e2e/ci/`, `e2e/scripts/`,
  `e2e/run.sh`, `e2e/nightly.sh`, `e2e/e2e.sh`, `e2e/staging/`, `tools/coder/`, `CLAUDE.md`,
  `backlog/config.yml`.
- **Kodér nikdy nemerguje.** Na `main` nastav ruleset bez výjimek (níž), pak token do `main`
  nepushne ani omylem.
- Copilot si může upravit testy tak, aby prošly. Proto každé PR kodéra prochází nezávislým review
  druhým modelem (viz níž); Claude reviewuje navíc na tvůj pokyn. Auto-merge zatím není.

## Instalace (jednorázově, jako uživatel se sudo)

```bash
git clone https://github.com/mastalir1980/ha-2N-intercom.git ~/ha-2n-intercom-install
cd ~/ha-2n-intercom-install
sudo bash tools/coder/install-vm.sh hermes
sudo ha2n-coder-set-token repo       # vlož token ha2n-coder-repo (nezobrazí se)
sudo ha2n-coder-set-token copilot    # vlož token copilot-cli-vm
sudo bash tools/coder/install-vm.sh hermes   # podruhé: self-check už vidí tokeny
```

**Model:** bez nastavení používá Copilot svůj výchozí model. Konkrétní model nastavíš jako root:
`echo <model-id> | sudo tee /etc/ha2n-coder/model`. Seznam ID modelů: `copilot help config` (u klíče `model`). Úroveň reasoningu: `echo high | sudo tee /etc/ha2n-coder/effort`
(none, minimal, low, medium, high, xhigh, max).
Pískoviště se před každým během maže, takže model vybraný ručně v Copilotu se neudrží. Platí jen tenhle soubor.

**Cena běhů (AI Credits):** Copilot na konci každého volání vypíše řádky `AI Credits` a `Tokens`
(proto kodér nepoužívá přepínač `-s`, ten by je potlačil). Po každém volání z nich `ha2n-run-task`
zapíše jeden řádek do `/var/lib/ha2n-coder/cost.csv`. Soubor zůstává jen na VM, nikdy se nepushuje
ani nedává do komentářů u PR (repo je veřejné).

| Sloupec | Význam |
|---|---|
| `time`, `run`, `task` | kdy, které id běhu, který úkol |
| `label` | `implement`, `local-fix-N` (opravy po lokálních bránách), `ci-fix-N` (opravy po červených checkách), `review-N` (volání reviewera) nebo `review-fix-1` (oprava po review) |
| `model`, `effort` | co bylo nastaveno v `/etc/ha2n-coder/model` a `/etc/ha2n-coder/effort` (u `review-N` z `review-model` a `review-effort`; prázdné = výchozí) |
| `ai_credits`, `duration` | spotřeba a doba, jak je Copilot vypsal |
| `tokens_in`, `tokens_out` | tokeny; Copilot je zaokrouhluje (14,9k = 14900) |

Ceny jsou v kreditech, přepočet na peníze závisí na tvém tarifu. Když Copilot souhrn nevypíše,
řádek se zapíše s prázdnými hodnotami a běh pokračuje. Součet za běh: `ha2n-task-status --list`
(sloupec `cr`) a `ha2n-task-status <run-id>` (rozpis po voláních).

**Review druhým modelem (TASK-33):** po zelených checkách spustí orchestrátor v pískovišti jedno review
jiným modelem, než který implementoval (doporučení: model Claude ze seznamu Copilot CLI, aby review
pocházelo od jiného výrobce než GPT kodér). Zapíná se souborem, bez něj se review přeskočí
(běh pak končí jako dřív, ve zprávě stojí `review skipped`):

```bash
echo <model-id> | sudo tee /etc/ha2n-coder/review-model     # povinné pro review
echo high       | sudo tee /etc/ha2n-coder/review-effort    # volitelné (stejné hodnoty jako effort)
```

Review dostane úkol, celý diff proti `origin/main` a pravidla z `CLAUDE.md` (architektura, Definition of
Done) a zapíše JSON `{verdict: approve|changes, findings: [{severity: blocking|minor, file, line, summary}]}`.
Jakákoli jeho změna souborů se zahodí. Verdikt a nálezy se přidají jako jeden komentář do PR (bez cen
a bez dat o VM; odkazy, tokeny a zmínky se z textu nálezů odstraní). Nečitelný výstup je „review failed“,
nikdy ne approve. Blokující nálezy jdou kodérovi zpět v jednom kole `review-fix-1` (nezapočítává se do 3 kol
oprav CI), pak znovu checky a ještě jedno review. Úkol se zavře až po verdiktu `approve`.
Review nemá token k repu, `git push`, `gh` ani `url` mají zakázané jako u kodéra.

Aktualizace po změně v `tools/coder/`: `git pull` v instalačním klonu a znovu `install-vm.sh`.

**Ruleset na `main`** (GitHub → Settings → Rules → Rulesets → New branch ruleset):
- Target: `main`, Enforcement: **Active**, Bypass list: **prázdný**,
- zapnout *Restrict deletions*, *Block force pushes*, *Require a pull request before merging*
  (Required approvals = 0, protože vlastní PR si schválit nemůžeš).

## Jak to používat

- **Připravený úkol** = stav *To Do*, přiřazený `@copilot`, hotové závislosti, bez štítků `on-hold` a `manual-path`,
  splněná Definition of Ready z `CLAUDE.md`. Připravuje ho Claude. Kodér ho vybere sám (viz *Automatický start*).
- Spuštění (Hermes nebo ty v terminálu):
  `sudo -n -u ha2n-coder /usr/local/bin/ha2n-run-task TASK-12`
- Stav: `sudo -n -u ha2n-coder /usr/local/bin/ha2n-task-status` (nebo `--list`).
- Výsledek je vždycky jeden z těchto:
  - `green`: PR s odkazem čeká na review,
  - `stopped`: s důvodem (úkol není připravený, Copilot narazil na nejasnost, patch sahá na chráněné soubory…),
  - `review`: checky jsou zelené, ale review neschválilo (blokující nálezy zůstaly i po opravě, nebo review
    selhalo). Nálezy jsou v komentáři v PR a ve zprávě; úkol zůstává *In Progress* a rozhoduješ ty,
  - `failed`: checky ani po 3 opravách nejsou zelené.

  Verdikt review (`approve`, `changes`, `failed` nebo `skipped`) je v řádku `review=` stavu (`ha2n-task-status`).
- Logy celého běhu: `/var/lib/ha2n-coder/runs/<run>/` (prompt, výstup Copilotu, brány, patche,
  checky).
- Pokud je vlastní klon poškozený, obnovíš ho příkazem `sudo rm -rf /var/lib/ha2n-coder/repo`; další běh ho znovu naklonuje (nejdřív ověř, že žádný běh neprobíhá).
- Když jsou všechny checky zelené (včetně `e2e-pi`) a review dalo `approve` (nebo je vypnuté), kodér přidá do PR **jeden poslední commit**: úkol dostane
  stav *Done*, odškrtnou se kritéria a doplní se shrnutí (odkaz na PR, checky, počet oprav). Na `main` se to dostane
  až tvým mergem. Když PR nezamergeš, na `main` se nezmění nic. Úkol se štítkem `manual-close` kodér nechá být
  (pro věci, které se ověřují až po mergi). Když se zavření nepovede, běh zůstane `green` a ve zprávě stojí, že
  úkol musíš zavřít ručně. Rodičovské úkoly (třeba TASK-2) se zavírají ručně.
- Omezení: poslední commit nemá žádné checky. Pokud někdy zapneš na `main` povinný check `e2e-pi`, GitHub tento
  commit zablokuje a zavírání se musí přesunout do workflow po mergi.

## Automatický start (časovač)

Na VM běží systemd časovač `ha2n-coder-next.timer` (5 min po startu, pak každých 10 min). Spouští
`ha2n-run-task --next`: vezme připravený úkol (viz výše) a spustí ho stejně jako ruční běh. Zapnutý je
ale jen po vytvoření souboru `/etc/ha2n-coder/autostart`; bez něj nedělá nic (ani nic nezapisuje).

- Zapnout: `sudo touch /etc/ha2n-coder/autostart`
- Vypnout: `sudo rm /etc/ha2n-coder/autostart` (běžící úkol se tím nezastaví; dokončí se)
- Denní limit: `/etc/ha2n-coder/max-runs-per-day` (jedno číslo, výchozí 3). Počítají se automatické starty za posledních 24 h.
  Při dosažení limitu časovač jen zapíše zprávu a skončí.
- Pořadí: nejdřív úkol z nejstaršího otevřeného milníku (podle verze), pak z dalších milníků, nakonec úkoly bez milníku.
  Uvnitř skupiny podle priority (High, Medium, Low), pak podle čísla úkolu.
- Běh spuštěný časovačem má v `ha2n-task-status --list` značku `auto`.

Pojistky proti smyčkám:

- Běží nejvýš jeden úkol. Když běží jiný běh (zámek `run.lock`), časovač nic nespustí.
- Úkol, jehož nejnovější běh už existuje (ať skončil jakkoli: `green`, `review`, `stopped`, `failed`, nebo
  spadl uprostřed), se znovu nespustí. Počká, dokud se soubor úkolu v Backlogu na `origin/main`
  nezmění po začátku toho běhu (rozhoduje čas, kdy změna dorazila na `main`; u starších běhů bez řádku
  `started=` ve `status` se začátek bere z run id). Nový pokus tedy znamená úpravu úkolu (Claude nebo ty).
- Ruční `ha2n-run-task TASK-N` tyto pojistky obchází (limit a pravidlo opakování hlídá jen `--next`).
  Připravenost úkolu (stav, přiřazení, hotové závislosti) kontroluje stejně.
- Chyba konfigurace (nečíselný `max-runs-per-day`) skončí chybou a nic nespustí.

## Regresní testy orchestrátoru

```bash
python3 -m unittest discover -s tools/coder/tests
```

Testy běží celé v dočasných adresářích s lokálním bare repozitářem a stuby `sudo`, `gh`,
`backlog`, `copilot` a `sleep` na `PATH`. Nepřistupují na VM ani k síti či skutečným tokenům.
Bez Bash 4+ nebo `flock` se korektně přeskočí (systémový Bash na macOS je 3.x).
Ověřují úklid zamítnutého patche i další běh po změně stejného souboru na `main`. Testy `--next` ověřují
vypínač, denní limit, zámek běhu, přeskočení `on-hold`/`manual-path`/cizího přiřazení/nesplněných závislostí,
pořadí podle milníku a priority a zákaz opakování po ukončeném běhu. Stejná sada pokrývá celý
průběh review (TASK-33) od PR po zavření úkolu: approve, changes → oprava → approve, changes bez opravy,
chybějící `review-model`, nečitelný výstup, selhání reviewera, oddělený rozpočet oprav CI, štítky v `cost.csv`
a `bash -n` všech skriptů. `sandbox.sh` samotný běží jen na VM (`bash -n` v testech).

Proměnná `HA2N_CODER_TEST_ROOT` přesměruje pracovní adresáře, cestu k testovací náhradě tokenu
a přidá testovací `bin` na `PATH`; kontrola uživatele zůstává platná. Je jen pro testy:
produkční `sudo` ji díky `env_reset` odstraní. Nepřidávej ji do `env_keep` ani ji nepředávej
přes `sudo -E`; bez ní zůstávají produkční cesty a `PATH` beze změny.
Před změnou `PATH` se účet ověří přes `/usr/bin/id -un` a produkčnímu uživateli `ha2n-coder` se nastavený testovací override vždy odmítne.

## Pro Hermese (instrukce, které mu dáš)

> Když tě Jan požádá „vezmi TASK-N“ / „pusť kodéra na TASK-N“, spusť
> `sudo -n -u ha2n-coder /usr/local/bin/ha2n-run-task TASK-N` a pošli mu vypsané run id.
> Pak každých 5 minut spusť `sudo -n -u ha2n-coder /usr/local/bin/ha2n-task-status` a jakmile je
> `state` `green`, `review`, `stopped` nebo `failed`, pošli Janovi `message`, `pr` a verdikt review (řádek `review=`:
> `approve`/`changes`/`failed`/`skipped`) jednou zprávou. Běhy spuštěné časovačem (značka `auto`) hlásíš stejně:
> každých 5 minut spusť `sudo -n -u ha2n-coder /usr/local/bin/ha2n-task-status --list`; u každého run id, které
> dosáhlo konečného stavu a ještě jsi ho nehlásil, spusť `ha2n-task-status <run-id>` a pošli Janovi totéž.
> Hlídej si, které run id jsi už nahlásil. Časovač sám nic
> neohlašuje. Ty ho nespouštíš (`--next`), ale můžeš pustit `ha2n-run-task TASK-N`, když Jan výslovně požádá.
> Jiné příkazy s `ha2n-coder` ani `ha2n-copilot` nespouštěj, tokeny nečti, nic nemerguj.
