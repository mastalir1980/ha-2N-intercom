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
    └─ čeká na checky (e2e-pi, hassfest, HACS) → když padnou, log jde zpět Copilotovi (max. 3 kola)
  → stav: ha2n-task-status   → Hermes ti napíše výsledek a odkaz na PR
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
- Copilot si může upravit testy tak, aby prošly. Proto se jeho PR vždycky reviewují (Claude na
  tvůj pokyn) a auto-merge zatím není.

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
| `label` | `implement`, `local-fix-N` (opravy po lokálních bránách) nebo `ci-fix-N` (opravy po červených checkách) |
| `model`, `effort` | co bylo nastaveno v `/etc/ha2n-coder/model` a `/etc/ha2n-coder/effort` (prázdné = výchozí) |
| `ai_credits`, `duration` | spotřeba a doba, jak je Copilot vypsal |
| `tokens_in`, `tokens_out` | tokeny; Copilot je zaokrouhluje (14,9k = 14900) |

Ceny jsou v kreditech, přepočet na peníze závisí na tvém tarifu. Když Copilot souhrn nevypíše,
řádek se zapíše s prázdnými hodnotami a běh pokračuje. Součet za běh: `ha2n-task-status --list`
(sloupec `cr`) a `ha2n-task-status <run-id>` (rozpis po voláních).

Aktualizace po změně v `tools/coder/`: `git pull` v instalačním klonu a znovu `install-vm.sh`.

**Ruleset na `main`** (GitHub → Settings → Rules → Rulesets → New branch ruleset):
- Target: `main`, Enforcement: **Active**, Bypass list: **prázdný**,
- zapnout *Restrict deletions*, *Block force pushes*, *Require a pull request before merging*
  (Required approvals = 0, protože vlastní PR si schválit nemůžeš).

## Jak to používat

- **Připravený úkol** = stav *To Do*, přiřazený `@copilot`, hotové závislosti, splněná Definition of
  Ready z `CLAUDE.md`. Připravuje ho Claude.
- Spuštění (Hermes nebo ty v terminálu):
  `sudo -n -u ha2n-coder /usr/local/bin/ha2n-run-task TASK-12`
- Stav: `sudo -n -u ha2n-coder /usr/local/bin/ha2n-task-status` (nebo `--list`).
- Výsledek je vždycky jeden z těchto:
  - `green`: PR s odkazem čeká na review,
  - `stopped`: s důvodem (úkol není připravený, Copilot narazil na nejasnost, patch sahá na chráněné soubory…),
  - `failed`: checky ani po 3 opravách nejsou zelené.
- Logy celého běhu: `/var/lib/ha2n-coder/runs/<run>/` (prompt, výstup Copilotu, brány, patche,
  checky).
- Když jsou všechny checky zelené (včetně `e2e-pi`), kodér přidá do PR **jeden poslední commit**: úkol dostane
  stav *Done*, odškrtnou se kritéria a doplní se shrnutí (odkaz na PR, checky, počet oprav). Na `main` se to dostane
  až tvým mergem. Když PR nezamergeš, na `main` se nezmění nic. Úkol se štítkem `manual-close` kodér nechá být
  (pro věci, které se ověřují až po mergi). Když se zavření nepovede, běh zůstane `green` a ve zprávě stojí, že
  úkol musíš zavřít ručně. Rodičovské úkoly (třeba TASK-2) se zavírají ručně.
- Omezení: poslední commit nemá žádné checky. Pokud někdy zapneš na `main` povinný check `e2e-pi`, GitHub tento
  commit zablokuje a zavírání se musí přesunout do workflow po mergi.

## Pro Hermese (instrukce, které mu dáš)

> Když tě Jan požádá „vezmi TASK-N“ / „pusť kodéra na TASK-N“, spusť
> `sudo -n -u ha2n-coder /usr/local/bin/ha2n-run-task TASK-N` a pošli mu vypsané run id.
> Pak každých 5 minut spusť `sudo -n -u ha2n-coder /usr/local/bin/ha2n-task-status` a jakmile je
> `state` `green`, `stopped` nebo `failed`, pošli Janovi `message` a `pr`. Jiné příkazy s
> `ha2n-coder` ani `ha2n-copilot` nespouštěj, tokeny nečti, nic nemerguj.
