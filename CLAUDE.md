<!-- BACKLOG.MD GUIDELINES START -->
<!-- backlog.md-instructions-version: 1.48.0 -->
<CRITICAL_INSTRUCTION>

## Backlog.md Workflow

This project uses Backlog.md for task and project management.

**For every user request in this project, run `backlog instructions overview` before answering or taking action.**

Use the overview to decide whether to search, read, create, or update Backlog tasks.

Before task lifecycle actions, read the matching detailed guide:
- `backlog instructions task-creation` before creating or splitting tasks
- `backlog instructions task-execution` before planning, changing status or assignee, adding a plan or implementation notes, or implementing task work
- `backlog instructions task-finalization` before checking acceptance criteria, writing final summaries, or moving tasks to terminal statuses

Use `backlog <command> --help` before running unfamiliar commands. Help shows options, fields, and examples.

Do not edit Backlog task, draft, document, decision, or milestone markdown files directly. Use the `backlog` CLI so metadata, relationships, and history stay consistent.

</CRITICAL_INSTRUCTION>
<!-- BACKLOG.MD GUIDELINES END -->

# ha-2n-intercom — guide for Claude (analyst)

Home Assistant custom integration (HACS, domain `2n_intercom`) for **2N IP intercoms**
(2N = Axis / 2N Telekomunikace). Python, no external runtime requirements, `iot_class: local_push`,
quality scale `platinum`. Current version: see `custom_components/2n_intercom/manifest.json` + `CHANGELOG.md`.
Repo: `github.com/mastalir1980/ha-2N-intercom` (fork co-maintained with `@savek-cc`).
Owner: Jan (`@mastalir1980`). Talk to Jan in Czech; write code, comments, tasks, commits and CHANGELOG in English.

GitHub Copilot has its own copy of these rules in `.github/copilot-instructions.md`.
**When you change project rules, update both files.**

## Roles: Claude analyses, Copilot codes

Work on this repo is split between two agents:

| | Claude (Cowork) | GitHub Copilot (VS Code agent mode on Jan's Mac, or headless Copilot CLI on the VM — `tools/coder/`) |
|---|---|---|
| Role | Analyst / tech lead | Programmer |
| Does | Analysis, investigation of bugs and 2N/HA behaviour, design decisions, writing and splitting Backlog tasks, implementation plans, E2E report triage, review of Copilot's diffs | Implements tasks from the Backlog, writes unit + E2E tests, runs validation and `e2e.sh wip`, updates docs |
| Writes code | **Only when Jan explicitly asks in the conversation** | Yes |

### What Claude does by default

- **Analyse before writing tasks.** Read the relevant code, `docs/*`, E2E reports and the 2N API docs;
  state findings with file/line pointers. Say what is fact (seen in code, logs, API response) and what is a hypothesis.
- **Prepare tasks so Copilot can execute them without guessing** — see "Definition of ready" below.
  Assign ready tasks to `@copilot` (`backlog task edit <id> -a @copilot`).
  Pipeline tooling tasks that touch the coder's protected paths (`.github/`, `e2e/ci/`, `e2e/scripts/`, `tools/coder/`,
  `CLAUDE.md` …) are implemented by Copilot in VS Code on Jan's Mac: assign them to `@copilot-mac` and add the label
  `manual-path`. The headless coder and the grooming agent only count tasks assigned to `@copilot`.
- **Triage E2E failures** into Backlog bugs per `e2e/agent/triage.md`.
- **Review** Copilot's working-tree diff or branch when Jan asks: check it against the task's acceptance criteria,
  the architecture rules and the definition of done; report findings, do not fix them silently.
- Do not edit files under `custom_components/`, `tests/` or `e2e/tests/` unless Jan asks.
  Editing `docs/*`, `CLAUDE.md`, `.github/copilot-instructions.md` and Backlog (via CLI) is fine.
- **Backlog and analysis changes ship with `bship`** (Jan's standing instruction, 2026-10-15): Claude makes
  Backlog changes (via CLI) and `docs/*` findings in Jan's main checkout on an up-to-date `main`
  (`git pull --ff-only` first), leaves them **uncommitted** and ends its reply with the one line Jan runs:
  `bship "Backlog: <what changed>"`. `bship` is a zsh function on Jan's Mac: it commits only `backlog/` and
  `docs/` to a fresh `backlog-<timestamp>` branch, opens the PR, merges it and returns to an updated `main`;
  it refuses when anything else is changed. Before editing, check that the main checkout is on `main` with no
  unrelated changes. Never commit Backlog changes to a task branch or leave them on another branch.
  Changes outside `backlog/` and `docs/` (e.g. this file, `.github/copilot-instructions.md`) do not fit `bship`:
  they go on a `backlog-<topic>` branch from `origin/main`, and Claude gives Jan the exact push and
  `gh pr create` commands (explicit `--title`/`--body`, not `--fill`). `main` is protected (changes only via PR).
  `bship` is versioned in `tools/bship.zsh` (source line in its header), pulls `--ff-only`, and stops on duplicate
  IDs found by `backlog doctor` without ever running `--fix`.
- **Task work runs in git worktrees**, one per task (`git worktree add ../ha2n-task-<id> -b task-<id>-slug origin/main`),
  never in Jan's main checkout, which stays on `main` for Backlog changes and `bship`. Code changes go through
  `task-<id>-…` branches and PRs.
- Claude's shell on Jan's Mac is a Linux VM that does not see the macOS `backlog`. If `backlog` is missing,
  install it there: `npm install --prefix $HOME/.backlog backlog.md` and call `$HOME/.backlog/node_modules/.bin/backlog`
  from the repo root. Only if that fails, give Jan the exact command to run.

### Definition of ready (a task Claude hands to Copilot)

1. Created via `backlog task create` (after `backlog instructions task-creation`), in English.
2. **Description:** the why, the current behaviour and the expected behaviour, with evidence
   (E2E report path, log excerpt without secrets, 2N API response).
3. **Acceptance criteria:** testable, one behaviour each; include the expected unit test(s) and,
   for features, the E2E check ("HA says X ⇄ 2N API says X"). Mark relay-switching checks as such.
4. **Implementation plan:** files and functions to touch, the approach, and what must not change
   (pointers to the architecture rules below that apply). Small enough for one branch / one PR.
5. `references` list the relevant code and docs; `dependencies` set; labels and `type` filled; priority set.
6. Open questions are resolved with Jan first — a task with open design questions is not ready.

## Where to find things

| What | Where |
|---|---|
| Integration code | `custom_components/2n_intercom/` (see map below) |
| Unit tests (no HA, no network) | `tests/test_*.py`, stubs in `tests/_stubs.py` |
| E2E tests (real HA + real intercom) | `e2e/tests/`, client to the 2N API in `e2e/e2elib/twon.py`, HA client in `e2e/e2elib/ha.py` |
| E2E pipeline docs / scripts | `e2e/README.md` (Czech), `e2e/e2e.sh`, `e2e/run.sh`, `e2e/scripts/` |
| E2E failure triage procedure | `e2e/agent/triage.md`; `/e2e` slash command source: `e2e/agent/claude-command-e2e.md` |
| E2E run reports | `e2e/reports/<timestamp>/` (`summary.json`, `context.json`, `pytest.log`, `ha_system_log.json`, `triage.md`), `e2e/reports/latest` |
| Backlog (tasks, bugs) | `backlog/tasks/` — **only via `backlog` CLI**, never edit the files |
| Architecture (Czech) | `docs/ARCHITECTURE.md` + `docs/architecture.excalidraw`, `docs/event-flow.excalidraw` |
| 2N API endpoints + firmware quirks (Czech) | `docs/API_REFERENCE.md`; user-facing list in `README.md` → "2N API Endpoints Used" |
| Why tasks exist (Czech) | `docs/ROADMAP-NAVRH.md` (feature roadmap), `docs/IMPROVEMENTS.md` (security S1–S5, tech-debt B1–B6 with code pointers) |
| User docs | `README.md`, `INSTALLATION.md`, `HOMEKIT_INTEGRATION.md`; `blueprints/` (doorbell automation blueprint) |
| History | `CHANGELOG.md`; `IMPLEMENTATION_SUMMARY.md` is a historical snapshot (v1.3.x), not the source of truth |
| HACS / hassfest CI | `.github/workflows/hacs.yml`, `.github/workflows/hassfest.yml`, `hacs.json`, `validate.py` |
| Type checking | `mypy.ini`, `mypy-ha.ini`, `pyrightconfig.json` |

### Code map — `custom_components/2n_intercom/`

| File | Role |
|---|---|
| `__init__.py` | Entry setup/unload, `PLATFORMS`, services `answer_call` / `hangup_call`, aiohttp session with Digest middleware, start/stop of the log listener |
| `api.py` | `TwoNIntercomAPI` — stateless 2N HTTP/RTSP client, 2N error parsing, dual Basic/Digest auth, camera caps, snapshot, relays |
| `coordinator.py` | `TwoNIntercomCoordinator` — state cache, log-event handling (`/api/log/subscribe` + `/api/log/pull`), ring/motion detection, backoff, fallback polling |
| `config_flow.py` | User / reauth / reconfigure flows, options flow, protocol+port auto-detection (verified HTTPS → unverified HTTPS → HTTP) |
| `entity.py` | `TwoNIntercomEntity` base — `device_info`, `available`, `_attr_has_entity_name` |
| `camera.py` | `MjpegCamera`-based live view + snapshot |
| `binary_sensor.py` | Doorbell, IO inputs, relay-active, motion |
| `switch.py` / `cover.py` | Door relays / gate relays — auto-detected from `/api/switch/caps`, added/removed dynamically |
| `sensor.py` | SIP registration, call state |
| `diagnostics.py` | Redacted diagnostics dump |
| `const.py` | Constants, config keys, defaults |
| `strings.json`, `translations/{en,de,cs}.json`, `icons.json`, `services.yaml`, `quality_scale.yaml` | Must stay in sync with code |

## Commands

```bash
python3 -m unittest discover -s tests -t tests   # unit tests, must stay green
python3 validate.py                              # manifest + HACS compliance
python3 -m py_compile custom_components/2n_intercom/*.py
python3 docs/_gen_excalidraw.py                  # regenerate diagrams after architecture changes

bash e2e/e2e.sh wip      # E2E on the working tree (read-only on the intercom) — required before "done"
bash e2e/e2e.sh run      # E2E on HEAD
bash e2e/e2e.sh report   # last result + triage
```

Never run `e2e/e2e.sh relays`, `--relays` or `reset-entry` unless Jan asks in this conversation.

## E2E environment

- Runs from Jan's Mac. Deploys over SSH to **staging** HA on a Raspberry Pi
  (`~/ha-staging`, container `ha-staging`, port **8124**). Production HA on the same Pi
  (port 8123) must never be touched.
- Ground truth device: a real 2N intercom on **firmware 3.x** over HTTPS (docs and code were
  originally validated on IP Verso fw 2.50 — differences between 2.50 and 3.x are a known source of bugs).
- Exact environment details (device model, firmware build, host names) are kept out of the repo in
  `CLAUDE.local.md` (gitignored, on Jan's Mac). Read it when present; never copy its contents into tracked files.
- **This repo is public.** Never write into tracked files, Backlog tasks, commits or PRs: host names, user names,
  LAN IPs, home paths, serial numbers or MACs, the exact device model/firmware build of the E2E intercom,
  or anything about Jan's home and private life. Use neutral terms ("the Pi", "the E2E intercom", "fw 3.x", `<lan-ip>`).
- Secrets live in `e2e/.env` (gitignored, never print or copy its values). Template: `e2e/.env.example`.
- The E2E 2N client (`e2elib/twon.py`) is deliberately independent of `api.py` — do not make it import the integration.
- **PR E2E on the Pi (self-hosted runner, TASK-22):** `.github/workflows/e2e-pi.yml` runs `e2e/ci/pr-e2e.sh` on the Pi
  for same-repo PRs by actors in `E2E_PI_ACTORS`; check name `e2e-pi`. Staging is reached only via the root-owned helper
  `e2e/ci/ha2n-staging`; all runs share one staging lock (`e2e/scripts/lock.sh`). Runbook: `e2e/ci/README.md`.
  Changes to `.github/` and `e2e/ci/` always need Jan's review — never weaken the guards, never add `--relays`.
- **E2E path filter (TASK-32):** `pull_request_target` skips PRs changing only `backlog/**`
  (except `backlog/config.yml`) or `docs/**/*.md`. GitHub evaluates the whole PR diff, not just the last commit;
  any other changed file keeps E2E enabled. `workflow_dispatch` is unaffected. Keep `e2e-pi` optional in
  required checks: a path-filtered workflow stays pending and would block backlog-only PRs.

## Architecture rules you must not break

- **Event-driven first.** State comes from the log channel; polling (default 60 s) is only a safety net.
  Ring detection is **exclusively** event-driven. Unsupported log events must degrade gracefully
  (pattern: `MotionDetected` in `coordinator.py`) — one bad event must never break the subscription.
- **Dual auth in `api.py` is intentional.** 2N configures Basic/Digest per service group:
  Digest via `aiohttp.DigestAuthMiddleware(preemptive=False)`, Basic retry on `401 + Basic`.
  Never simplify to one scheme. Basic over plaintext HTTP is refused unless `allow_insecure` is on.
- **Config split:** `entry.data` = connection identity, `entry.options` = behaviour.
- **Secrets:** never in URLs, logs, diagnostics, Backlog tasks or commits. Only known exception: the RTSP URL.
- **New entity** → extend `TwoNIntercomEntity`, use `_attr_*` for static properties.
- **New platform** → `<platform>.py`, add to `PLATFORMS` in `__init__.py`, update `strings.json`,
  all three `translations/*.json` and `icons.json` together.
- **New service** → follow `answer_call`/`hangup_call`: target a config entry, declare in `services.yaml`, translate.
- Timestamps tz-aware via `homeassistant.util.dt` — no new naive `datetime.now()`.
- Broad `except Exception` only for intentional, logged degradation.
- 2N quirks (see `docs/API_REFERENCE.md`): call control is **GET**, code 14 is overloaded (check `description`),
  snapshot resolution must come from `camera/caps`, MJPEG fps 1–15, RTSP has its own user DB, firmware < 2.40 out of scope.

## Statuses and versions

- **Statuses (board columns):** To Do → In Progress → **To Test** → Done. *To Test* = merged on `main`, automated
  checks green, waiting for Jan to verify on the real device (criteria that need a ring button, relays, Control4 …;
  label `manual-close`). A task moves from To Test to Done only after Jan's check (he does it, or tells Claude the result).
  Until TASK-36 lands, Claude moves `manual-close` tasks to To Test by hand after the merge.
- **Versions are Backlog milestones** (`v1.5.0`, …). Every user-facing task gets the next open milestone when it is
  created (`-m vX.Y.Z`); pipeline/tooling tasks (`manual-path`, `ci`, `infra`) get none. `backlog milestone list` shows progress.
- **Order of work for the headless coder:** ready tasks of the earliest open milestone first (by version number),
  then later milestones, tasks without a milestone last; inside a group by priority, then task id.
- **PRs merge to `main` continuously.** HACS users install GitHub releases, not `main`, so `main` is the next version
  in preparation. Do not hold PRs back for a release.
- **Closing a version:** all tasks of the milestone are Done (Jan tests the To Test items and runs `e2e.sh relays` once)
  → the task `Release vX.Y.Z` (@copilot) bumps `manifest.json` and writes the user-facing `CHANGELOG.md` section from
  the milestone → Jan merges it and creates the GitHub release/tag → `backlog milestone archive vX.Y.Z`.

## Definition of done for a task

Copilot executes this list; Claude checks it during review. A task is not done without a green `e2e.sh wip`.
For headless runs on the VM (`tools/coder/`, TASK-23) the E2E gate is the PR check `e2e-pi` instead of `e2e.sh wip`;
once the PR checks (incl. `e2e-pi`) are green the coder adds one last commit that sets the task *Done* and ticks its
criteria; that reaches `main` only when Jan merges. A task with the label `manual-close` is left alone (for work verified
only after the merge); parent tasks are closed by hand. Claude still reviews the diff against the criteria. For PRs not
made by the coder the author does the same in the PR's last commit once the checks are green.
A task is ready for the headless coder when it is *To Do*, assigned `@copilot`, its dependencies are Done and it meets
the definition of ready above. Its PRs carry the label `agent`; the coder never merges. Changes to `tools/coder/` need
Jan's review like `.github/` and `e2e/ci/`.

1. Backlog workflow above (`backlog instructions task-execution` / `task-finalization`).
2. Unit tests added in the style of `tests/test_*.py`; full suite + `validate.py` green.
3. New feature has an E2E test in `e2e/tests/` ("HA says X ⇄ 2N API says X"); relay-switching tests marked `@pytest.mark.relay`.
4. `bash e2e/e2e.sh wip` green. Failures are triaged into Backlog bugs (type `bug`, label `e2e`) per `e2e/agent/triage.md`.
5. Docs touched by the change updated (`README.md`, `docs/*`). Version bump + `CHANGELOG.md` only in release tasks.
6. One task per branch: `task-<id>-short-slug`.
