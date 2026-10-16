#!/usr/bin/env bash
# ha2n-run-task — turn one ready Backlog task into a PR, on Jan's command only.
# Runs as user ha2n-coder (installed root-owned as /usr/local/bin/ha2n-run-task by install-vm.sh).
# Hermes (user hermes) may start it only via:  sudo -n -u ha2n-coder /usr/local/bin/ha2n-run-task TASK-12
#
#   ha2n-run-task <TASK-ID>               start in the background, print the run id and exit
#   ha2n-run-task --foreground <TASK-ID>  run attached (for debugging)
#   ha2n-run-task --next                  start the next ready task if autostart allows it (systemd timer, see install-vm.sh)
#
# Flow: ready check → sandbox clone → Copilot implements → local gates (≤2 local fix rounds) →
# patch checked for protected paths/size → applied in our own clone → push + PR (Jan's token) →
# wait for PR checks incl. e2e-pi → on failure feed the public log back to Copilot (≤3 rounds) →
# independent review by a second model (only with /etc/ha2n-coder/review-model; blocking findings get ONE
# fix round, then checks and one more review) → report.
# Copilot never sees the repo token; this script never runs code from the repo (only git, gh, backlog).
# When everything is green and the review approved (or is not configured) it adds ONE last commit to the PR branch that sets the task Done and ticks its
# criteria (takes effect on main only when Jan merges; label manual-close opts out). Never merges. State: /var/lib/ha2n-coder/runs/<run>/{status,run.log,*.patch}; see ha2n-task-status.
set -uo pipefail
umask 027
if [ "${HA2N_CODER_TEST_ROOT+x}" = x ]; then
  REAL_USER="$(/usr/bin/id -un)" || { echo "cannot determine user for test override" >&2; exit 2; }
  [ "$REAL_USER" != ha2n-coder ] || { echo "test override refused for the production user" >&2; exit 2; }
fi
# Hermetic tests use a temporary root; sudo env_reset strips this override in production.
PATH="${HA2N_CODER_TEST_ROOT:+$HA2N_CODER_TEST_ROOT/bin:}/usr/local/bin:/usr/bin:/bin"
ME="$(id -un)"; [ "$ME" = ha2n-coder ] || { echo "must run as ha2n-coder" >&2; exit 2; }
HOME="$(getent passwd "$ME" | cut -d: -f6)"; export HOME
REPO="mastalir1980/ha-2N-intercom"
BASE="${HA2N_CODER_TEST_ROOT:-}/var/lib/ha2n-coder"; CLONE="$BASE/repo"; RUNS="$BASE/runs"
LIB="${HA2N_CODER_TEST_ROOT:-}/usr/local/lib/ha2n-coder"
SANDBOX=(sudo -n -u ha2n-copilot "$LIB/sandbox.sh")
REPO_TOKEN_FILE="${HA2N_CODER_TEST_ROOT:-}/etc/ha2n-coder/repo.token"
REVIEW_MODEL_FILE="${HA2N_CODER_TEST_ROOT:-}/etc/ha2n-coder/review-model"   # optional: its presence turns the review on
PROTECTED='(^|/)\.git|^(\.github/|e2e/ci/|e2e/scripts/|e2e/run\.sh$|e2e/nightly\.sh$|e2e/e2e\.sh$|e2e/staging/|e2e/\.env|e2e/tests/conftest\.py$|tools/coder/|CLAUDE\.md$|backlog/config\.yml$)'
MAX_FILES=40; MAX_LINES=2500; LOCAL_ROUNDS=2; CI_ROUNDS=3; REVIEW_ROUNDS=1; CHECKS_TIMEOUT=$((45*60))
COST_CSV="$BASE/cost.csv"   # one line per Copilot call; stays on the VM (the repo is public)

setup_auth() {  # sets TOKEN and AUTH, defines the two wrappers every git/gh call goes through
  TOKEN="$(cat "$REPO_TOKEN_FILE")"
  AUTH="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$TOKEN" | base64 -w0)"
  export GH_PROMPT_DISABLED=1 GH_NO_UPDATE_NOTIFIER=1
  # The token goes only to these two wrappers (env, not argv: invisible in `ps` to other users).
  gitauth() { GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0="http.https://github.com/.extraheader" GIT_CONFIG_VALUE_0="$AUTH" git "$@"; }
  ghx() { GH_TOKEN="$TOKEN" gh "$@"; }
}

launch_bg() {  # launch_bg <TASK> [next]: start a run in the background; "next" leaves a marker for the daily limit
  local run="$(date +%Y%m%d-%H%M%S)-$1"
  mkdir "$RUNS/$run" 2>/dev/null || { echo "a run of $1 was started this second already" >&2; exit 2; }
  [ "${2:-}" = next ] && : > "$RUNS/$run/next.marker"
  local -a detach=(nohup)
  command -v setsid >/dev/null 2>&1 && detach=(setsid nohup)   # setsid is Linux-only; macOS dev runs just use nohup
  "${detach[@]}" "$0" --foreground "$1" --run "$run" > "$RUNS/$run/run.log" 2>&1 < /dev/null 8>&- 9>&- &
  echo "started $run — status: ha2n-task-status $run"
}

last_run_blocks() {  # last_run_blocks <TASK>: 0 = keep it off; 1 = a new attempt is fair
  # The newest run of a task keeps it off until its task file on origin/main changed after that run started.
  local run started changed
  run="$(ls -1d "$RUNS"/*-"$1" 2>/dev/null | sort | tail -1)"
  [ -n "$run" ] || return 1
  # A run that stopped before it chose a branch (e.g. the ready check refused it) implemented nothing. Such a task
  # becomes ready through another task's file (a dependency gets Done), so waiting for its own file would be forever.
  grep -qx 'state=stopped' "$run/status" 2>/dev/null && grep -qx 'branch=' "$run/status" && return 1
  started="$(sed -n 's/^started=//p' "$run/status" 2>/dev/null | head -1)"
  if ! [[ "$started" =~ ^[0-9]+$ ]]; then   # runs from before started= existed: the run id holds the local start time
    started="$(python3 -c 'import sys, time; print(int(time.mktime(time.strptime(sys.argv[1], "%Y%m%d-%H%M%S"))))' \
      "$(basename "$run" | cut -c1-15)" 2>/dev/null)"
    [[ "$started" =~ ^[0-9]+$ ]] || return 0
  fi
  # --first-parent: the time the change landed on main (merge commit), not when it was written on a branch
  changed="$(git log -1 --first-parent --format=%ct origin/main -- "backlog/tasks/task-${1#TASK-} - *" 2>/dev/null)"
  [[ "$changed" =~ ^[0-9]+$ ]] && [ "$changed" -gt "$started" ] && return 1
  return 0
}

# Backlog output differs between backlog.md versions (1.48: "Dependencies: TASK-x" line, no --json;
# 1.53: --json, and --plain prints a "Depends on (…):" tree instead). Prefer --json, fall back to both plain forms.
task_json() {  # task_json <TASK> <field>: one value per line from `backlog task view --json`; fails if unsupported
  local out
  out="$(backlog task view "$1" --json 2>/dev/null)" || return 1
  python3 -c '
import json, sys
task = json.loads(sys.stdin.read())["task"]
if sys.argv[1] not in task:
    sys.exit(1)
value = task[sys.argv[1]]
print("\n".join(value) if isinstance(value, list) else (value or ""))' "$2" <<<"$out" 2>/dev/null
}

dep_ids() {  # dep_ids <TASK>: direct dependencies, one per line
  local out
  if out="$(task_json "$1" dependencies)"; then printf '%s\n' "$out"; return 0; fi
  out="$(backlog task view "$1" --plain 2>/dev/null | sed '/^Description:/q')" || return 1
  { sed -n 's/^Dependencies: //p' <<<"$out" | grep -oE 'TASK-[0-9]+(\.[0-9]+)?'
    # tree: top-level "├─ TASK-x - title [Status]" lines under "Depends on"; indented lines are indirect
    awk '/^Depends on/ { f = 1; next } f && !NF { f = 0 } f' <<<"$out" | sed -nE 's/^(├─|└─) (TASK-[0-9]+(\.[0-9]+)?) - .*/\2/p'
  } | sort -u
}

task_done() {  # task_done <TASK>
  local status
  status="$(task_json "$1" status)" && [ -n "$status" ] && { [ "$status" = Done ]; return; }
  backlog task view "$1" --plain 2>/dev/null | sed '/^Description:/q' | grep -q '^Status: .*Done'
}

deps_done() {  # deps_done <TASK>: fails when a direct dependency is not Done (or the task cannot be read)
  local ids dep
  ids="$(dep_ids "$1")" || return 1
  for dep in $ids; do task_done "$dep" || return 1; done
}

candidate_row() {  # candidate_row <TASK>: prints a sort-key line when the coder may start it, fails otherwise
  local id="$1" view header mid mtitle ver a b c prio prank mrank num
  view="$(backlog task view "$id" --plain 2>/dev/null)" || return 1
  header="$(sed '/^Description:/q' <<<"$view")"
  grep -q '^Status: .*To Do' <<<"$header" || return 1
  grep -Eq '^Assignee:.*@copilot([^-[:alnum:]_]|$)' <<<"$header" || return 1
  sed -n 's/^Labels: //p' <<<"$header" | tr ',' '\n' | sed 's/^ *//; s/ *$//' | grep -qxE 'on-hold|manual-path' && return 1
  deps_done "$id" || return 1
  # Sort key: milestone (semver of its title; unversioned after, none last), priority, lowest id.
  mid="$(sed -n 's/^Milestone: //p' <<<"$header" | head -1 | tr -d '[:space:]')"
  if [ -z "$mid" ]; then mrank=2
  else
    mtitle="$(backlog milestone list --plain 2>/dev/null | awk -v id="$mid" '{ sub(/^ +/, "") } index($0, id ": ") == 1 { s = substr($0, length(id) + 3); sub(/ \([0-9]+\/[0-9]+ done\)$/, "", s); print s; exit }')"
    [ -n "$mtitle" ] || mtitle="$mid"
    ver="$(grep -oE '[0-9]+(\.[0-9]+)+' <<<"$mtitle" | head -1)"
    if [ -n "$ver" ]; then
      IFS=. read -r a b c <<<"$ver"
      mrank="$(printf '0%05d%05d%05d' "$((10#$a))" "$((10#${b:-0}))" "$((10#${c:-0}))")"
    else mrank="1$mtitle"; fi
  fi
  prio="$(sed -n 's/^Priority: //p' <<<"$header" | head -1)"
  case "$prio" in High*) prank=1 ;; Medium*) prank=2 ;; Low*) prank=3 ;; *) prank=4 ;; esac
  num="${id#TASK-}"
  printf '%s\t%s\t%010d\t%s\n' "$mrank" "$prank" "$((10#${num%%.*}))" "$id"
}

pick_next() {  # prints the task to start (nothing when none is ready); exits 1 when origin/main cannot be read
  [ -r "$REPO_TOKEN_FILE" ] || { echo "missing repo token (sudo ha2n-coder-set-token repo)" >&2; exit 1; }
  setup_auth
  [ -d "$CLONE/.git" ] || git clone -q "https://github.com/$REPO.git" "$CLONE" || { echo "clone failed" >&2; exit 1; }
  cd "$CLONE" || exit 1
  gitauth fetch -q --prune origin || { echo "git fetch failed" >&2; exit 1; }
  { git checkout -q --detach -f origin/main && git reset -q --hard origin/main && git clean -qfdx; } \
    || { echo "cannot reset own clone" >&2; exit 1; }
  local rows="" id row
  for id in $(backlog task list --status "To Do" --plain 2>/dev/null | sed -nE 's/^ +(\[[^]]*\] )*(TASK-[0-9]+(\.[0-9]+)?) - .*/\2/p'); do
    row="$(candidate_row "$id")" && rows+="$row"$'\n'
  done
  while IFS=$'\t' read -r _ _ _ id; do
    [ -n "$id" ] || continue
    if ! last_run_blocks "$id"; then echo "$id"; return 0; fi
  done <<<"$(LC_ALL=C sort <<<"$rows")"
  return 0
}

start_next() {  # the timer's entry point: start the next ready task if autostart allows it
  local cfg="${HA2N_CODER_TEST_ROOT:-}/etc/ha2n-coder" max=3 recent=0 task
  [ -e "$cfg/autostart" ] || return 0   # kill switch: no root-owned file, nothing starts (silent)
  if [ -e "$cfg/max-runs-per-day" ]; then
    max="$(tr -d '[:space:]' < "$cfg/max-runs-per-day")"
    [[ "$max" =~ ^[0-9]+$ ]] || { echo "invalid /etc/ha2n-coder/max-runs-per-day" >&2; return 1; }
  fi
  exec 8>"$BASE/next.lock"; flock -n 8 || { echo "another autostart check is running"; return 0; }   # held until exit, so the count below cannot race
  [ -d "$RUNS" ] && recent="$(find "$RUNS" -mindepth 2 -maxdepth 2 -name next.marker -mmin -1440 | wc -l | tr -d ' ')"
  [ "$recent" -lt "$max" ] || { echo "daily limit reached: $recent autostarted runs in the last 24 h (max $max)"; return 0; }
  exec 9>"$BASE/run.lock"; flock -n 9 || { echo "a task is running; not starting another"; return 0; }
  task="$(pick_next)" || return 1
  exec 9>&-   # the run takes this lock itself; release it first
  [ -n "$task" ] || return 0
  launch_bg "$task" next
}

FG=0; [ "${1:-}" = "--foreground" ] && { FG=1; shift; }
if [ "${1:-}" = "--next" ]; then
  [ "$FG" = 0 ] && [ "$#" = 1 ] || { echo "usage: ha2n-run-task --next" >&2; exit 2; }
  start_next; exit $?
fi
TASK="${1:-}"
[[ "$TASK" =~ ^TASK-[0-9]+(\.[0-9]+)?$ ]] || { echo "usage: ha2n-run-task [--foreground] TASK-<n> | --next" >&2; exit 2; }
if [ "$FG" = 0 ]; then launch_bg "$TASK"; exit 0; fi
shift
RUN="${2:-}"; [ "${1:-}" = "--run" ] && [ -n "$RUN" ] || RUN="$(date +%Y%m%d-%H%M%S)-$TASK"
[[ "$RUN" =~ ^[0-9]{8}-[0-9]{6}-TASK-[0-9]+(\.[0-9]+)?$ ]] || { echo "invalid run id" >&2; exit 2; }
DIR="$RUNS/$RUN"; mkdir -p "$DIR"
STARTED="$(date +%s)"   # epoch of this run; last_run_blocks compares task-file commits with it

status() {  # status <state> <message>  — states: running, stopped, green, review, failed
  { echo "task=$TASK"; echo "started=$STARTED"; echo "state=$1"; echo "message=$2"; echo "branch=${BRANCH:-}"; echo "pr=${PR_URL:-}"
    echo "round=${ROUND:-0}"; echo "review=${REVIEW_VERDICT:-}"; echo "updated=$(date -Is)"; } > "$DIR/status.tmp" && mv "$DIR/status.tmp" "$DIR/status"
  echo "[$(date +%H:%M:%S)] $1: $2"
}
stop() { status stopped "$*"; exit 1; }
stop_clean() {
  git reset -q --hard && git clean -qfdx || stop "cannot clean own clone after: $*"
  stop "$@"
}

exec 9>"$BASE/run.lock"
flock -n 9 || stop "another task is running (one at a time)"
ln -sfn "$DIR" "$RUNS/latest"
[ -r "$REPO_TOKEN_FILE" ] || stop "missing repo token (sudo ha2n-coder-set-token repo)"
TOKEN="$(cat "$REPO_TOKEN_FILE")"
REVIEW_ON=0; REVIEW_MODEL=""
if [ -e "$REVIEW_MODEL_FILE" ]; then
  REVIEW_MODEL="$(tr -d '[:space:]' < "$REVIEW_MODEL_FILE" 2>/dev/null)"
  [[ "$REVIEW_MODEL" =~ ^[A-Za-z0-9._-]{1,64}$ ]] || stop "unreadable or invalid /etc/ha2n-coder/review-model"
  REVIEW_ON=1
fi
AUTH="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$TOKEN" | base64 -w0)"
export GH_PROMPT_DISABLED=1 GH_NO_UPDATE_NOTIFIER=1
# The token goes only to these two wrappers (env, not argv: invisible in `ps` to other users).
gitauth() { GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0="http.https://github.com/.extraheader" GIT_CONFIG_VALUE_0="$AUTH" git "$@"; }
ghx() { GH_TOKEN="$TOKEN" gh "$@"; }
status running "starting"

# ---- 1. own clean clone + ready check -------------------------------------------------------
[ -d "$CLONE/.git" ] || git clone -q "https://github.com/$REPO.git" "$CLONE" || stop "clone failed"
cd "$CLONE" || stop "no clone"
git config user.name "ha2n-coder (Copilot)"; git config user.email "ha2n-coder@localhost"
git config core.hooksPath /dev/null
gitauth fetch -q --prune origin || stop "git fetch failed"
{ git reset -q --hard && git clean -qfdx && git checkout -q --detach -f origin/main \
    && git reset -q --hard origin/main && git clean -qfdx; } || stop "cannot reset own clone"
backlog task view "$TASK" --plain > "$DIR/task.txt" 2>&1 || stop "task $TASK not found"
HEADER="$(sed '/^Description:/q' "$DIR/task.txt")"   # only the metadata part, not the free text
grep -q '^Status: .*To Do' <<<"$HEADER"   || stop "task is not 'To Do' — not ready for the coder"
grep -q '^Assignee: .*@copilot' <<<"$HEADER" || stop "task is not assigned to @copilot — not ready"
deps_done "$TASK" || stop "task has dependencies that are not done"
TITLE="$(sed -n "s/^Task $TASK - //p" "$DIR/task.txt" | head -1)"
NUM="${TASK#TASK-}"
SLUG="$(printf '%s' "$TITLE" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//' | cut -c1-40 | sed -E 's/-+$//')"
BRANCH="task-$NUM-${SLUG:-change}"
gitauth ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1 && stop "branch $BRANCH already exists on GitHub"
status running "ready: $TITLE"

render() {  # render <template> <failure-file|-> <where>
  python3 - "$LIB/prompts/$1" "$DIR/task.txt" "$2" "$3" "$TASK" "$BRANCH" <<'PY'
import sys, pathlib
tpl, task, fail, where, tid, br = sys.argv[1:7]
s = pathlib.Path(tpl).read_text()
fail_text = pathlib.Path(fail).read_text()[-12000:] if fail != "-" else ""
for k, v in {"TASK_ID": tid, "BRANCH": br, "TASK_TEXT": pathlib.Path(task).read_text()[:20000],
             "FAILURE": fail_text, "WHERE": where}.items():
    s = s.replace("{{" + k + "}}", v)
sys.stdout.write(s)
PY
}

log_cost() {  # log_cost <label> [log] — one cost.csv line from the summary Copilot printed in the log (default copilot-$ROUND.log)
  # Columns: time,run,task,label,model,effort,ai_credits,tokens_in,tokens_out,duration
  # Tokens are as printed (14.9k -> 14900). Never fails the run: missing/odd output -> empty fields.
  python3 - "$COST_CSV" "${2:-$DIR/copilot-$ROUND.log}" "$RUN" "$TASK" "$1" <<'PY' 2>/dev/null || true
import csv, datetime, os, re, sys
path, log, run, task, label = sys.argv[1:6]
try:
    text = open(log, errors="replace").read()
except OSError:
    text = ""
text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)          # colour codes
def last(rx):
    m = re.findall(rx, text, re.M)
    return m[-1] if m else None
def first(rx):   # model/effort lines are printed by sandbox.sh before Copilot starts
    m = re.findall(rx, text, re.M)
    return m[0] if m else None
def tokens(s):
    m = re.fullmatch(r"([0-9]*\.?[0-9]+)([kKmM]?)", (s or "").replace(",", "").replace(" ", ""))
    if not m:
        return ""
    return str(round(float(m.group(1)) * {"": 1, "k": 1e3, "m": 1e6}[m.group(2).lower()]))
cr = last(r"AI Credits[ \t]+([0-9][0-9.,]*)")
dur = last(r"AI Credits[ \t]+[0-9][0-9.,]*[ \t]*\(([^)]*)\)")
tk = last(r"Tokens[ \t]+↑[ \t]*([0-9][0-9.,]*[ \t]*[kKmM]?)[^↓\n]*↓[ \t]*([0-9][0-9.,]*[ \t]*[kKmM]?)")
tin, tout = (tokens(tk[0]), tokens(tk[1])) if tk else ("", "")
row = [datetime.datetime.now().astimezone().isoformat(timespec="seconds"), run, task, label,
       first(r"^model: (.+?)\s*$") or "", first(r"^reasoning effort: (.+?)\s*$") or "",
       (cr or "").replace(",", ""), tin, tout, dur or ""]
new = not os.path.exists(path) or os.path.getsize(path) == 0
with open(path, "a", newline="") as f:
    w = csv.writer(f, lineterminator="\n")
    if new:
        w.writerow(["time", "run", "task", "label", "model", "effort", "ai_credits", "tokens_in", "tokens_out", "duration"])
    w.writerow(row)
PY
}

copilot_round() {  # copilot_round <template> <failure-file|-> <where> <label>
  render "$1" "$2" "$3" | "${SANDBOX[@]}" copilot > "$DIR/copilot-$ROUND.log" 2>&1
  local rc=$?
  log_cost "$4"
  tail -5 "$DIR/copilot-$ROUND.log"
  [ "$rc" = 3 ] && stop "Copilot stopped: $(sed -n '/asked to stop/,$p' "$DIR/copilot-$ROUND.log" | tail -n +2 | head -5 | tr '\n' ' ')"
  [ "$rc" = 0 ] || stop "Copilot run failed (exit $rc), see copilot-$ROUND.log"
}

local_gates() {  # implement + up to LOCAL_ROUNDS local fixes until gates are green
  local i=0
  while :; do
    if "${SANDBOX[@]}" gates > "$DIR/gates-$ROUND-$i.log" 2>&1; then status running "local gates green"; return 0; fi
    [ "$i" -ge "$LOCAL_ROUNDS" ] && stop "local gates still red after $LOCAL_ROUNDS fix rounds (gates-$ROUND-$i.log)"
    i=$((i+1)); status running "local gates red — Copilot fix $i/$LOCAL_ROUNDS"
    copilot_round fix.md "$DIR/gates-$ROUND-$((i-1)).log" "local gates (unit tests / validate.py / py_compile)" "local-fix-$i"
  done
}

publish() {  # take the diff from the sandbox, apply it, check what is ACTUALLY staged, commit, push
  "${SANDBOX[@]}" patch > "$DIR/change-$ROUND.diff" 2> "$DIR/patch-$ROUND.log" || stop "no changes produced"
  { git checkout -q -B "$BRANCH" origin/main && git reset -q --hard && git clean -qfdx; } || stop "cannot reset own clone"
  git apply --index --whitespace=nowarn "$DIR/change-$ROUND.diff" 2> "$DIR/apply-$ROUND.log" \
    || stop_clean "diff does not apply on main (apply-$ROUND.log)"
  git diff --cached --no-renames --name-only -z | tr '\0' '\n' > "$DIR/files-$ROUND.txt"
  [ -s "$DIR/files-$ROUND.txt" ] || stop_clean "no changes produced"
  if grep -E "$PROTECTED" "$DIR/files-$ROUND.txt" > "$DIR/protected.txt"; then
    stop_clean "change touches protected paths: $(head -5 "$DIR/protected.txt" | tr '\n' ' ')"
  fi
  git diff --cached --no-renames --summary | grep -Eq 'mode (120000|160000)|mode change' \
    && stop_clean "symlinks, submodules and file-mode changes are not allowed"
  git diff --cached --no-renames --numstat | awk '$1=="-"' | grep -q . && stop_clean "binary files are not allowed"
  local n lines
  n="$(wc -l < "$DIR/files-$ROUND.txt")"
  lines="$(git diff --cached --no-renames --numstat | awk '{a+=$1; d+=$2} END {print a+d}')"
  [ "$n" -le "$MAX_FILES" ] && [ "$lines" -le "$MAX_LINES" ] || stop_clean "change too big for one PR ($n files, $lines lines)"
  git commit -q -m "$TASK: $TITLE" -m "Implemented by GitHub Copilot CLI (headless, ha2n-coder), round $ROUND." \
    || stop_clean "commit failed"
  gitauth push -q --force-with-lease origin "$BRANCH" || stop_clean "push failed"
  status running "pushed $(git rev-parse --short HEAD) ($n files, $lines lines)"
}

open_pr() {
  ghx label create agent -R "$REPO" --color 5319e7 --description "Opened by the headless coder" >/dev/null 2>&1 || true
  {
    echo "Implements **$TASK** — $TITLE"; echo
    echo "Opened by **ha2n-coder** (GitHub Copilot CLI, headless on the VM) on Jan's command."
    echo "Local gates (unit tests, validate.py, py_compile on Python 3.12) were green before push;"
    echo "E2E runs as the \`e2e-pi\` check. When all checks are green the coder adds one last commit that"
    echo "sets the task Done and ticks its criteria; that takes effect when you merge (label manual-close opts out)."
  } > "$DIR/pr-body.md"
  PR_URL="$(ghx pr create -R "$REPO" --base main --head "$BRANCH" --title "$TASK: $TITLE" \
            --body-file "$DIR/pr-body.md" --label agent 2>/dev/null \
         || ghx pr create -R "$REPO" --base main --head "$BRANCH" --title "$TASK: $TITLE" --body-file "$DIR/pr-body.md")" \
    || stop "could not open the PR"
  status running "PR opened"
}

wait_checks() {  # -> 0 green (e2e-pi = pass, nothing failed), 1 failed (details in $DIR/ci-$ROUND.txt)
  local head deadline=$(( $(date +%s) + CHECKS_TIMEOUT ))
  head="$(git rev-parse HEAD)"
  # GitHub must see the new head first, otherwise we would read the previous push's checks
  until [ "$(ghx pr view "$PR_URL" -R "$REPO" --json headRefOid -q .headRefOid 2>/dev/null)" = "$head" ]; do
    [ "$(date +%s)" -gt "$deadline" ] && stop "GitHub does not show the pushed commit on the PR"
    sleep 10
  done
  sleep 30
  while :; do
    ghx pr checks "$PR_URL" -R "$REPO" --json name,bucket,link > "$DIR/checks.json" 2>/dev/null || echo '[]' > "$DIR/checks.json"
    if python3 - "$DIR/checks.json" <<'PY'; then break; fi
import json, sys
c = json.load(open(sys.argv[1]))
done = any(x["name"] == "e2e-pi" for x in c) and all(x["bucket"] != "pending" for x in c)
sys.exit(0 if done else 1)
PY
    [ "$(date +%s)" -gt "$deadline" ] && stop "checks did not finish within $((CHECKS_TIMEOUT/60)) min (is the Pi runner online?)"
    sleep 30
  done
  python3 - "$DIR/checks.json" > "$DIR/ci-$ROUND.txt" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
bad = [x for x in c if x["bucket"] in ("fail", "cancel")]
bad += [x for x in c if x["name"] == "e2e-pi" and x["bucket"] != "pass" and x not in bad]  # skipped e2e-pi is not green
for x in bad: print(x["name"], x["bucket"], x.get("link", ""))
sys.exit(1 if bad else 0)
PY
}

failure_text() {  # public logs of the failed checks (e2e-pi prints only its sanitised summary)
  local f="$DIR/ci-fail-$ROUND.txt"; : > "$f"
  while read -r name _ link; do
    run_id="$(sed -nE 's#.*/actions/runs/([0-9]+).*#\1#p' <<<"$link")"
    echo "### Check: $name" >> "$f"
    [ -n "$run_id" ] && ghx run view "$run_id" -R "$REPO" --log-failed 2>/dev/null \
      | sed -E 's/^[^\t]*\t[^\t]*\t//' | tail -120 >> "$f"
    echo >> "$f"
  done < "$DIR/ci-$ROUND.txt"
  echo "$f"
}

review() {  # one review round of the published PR head -> REVIEW_VERDICT (approve|changes|failed), REVIEW_BLOCKING, REVIEW_MINOR
  # The reviewer never gets more than the coder did (no repo token); its JSON is validated and only the parsed,
  # sanitised fields (no links, no token-like strings, no mentions) reach the PR comment. Anything unusable is
  # "failed", never "approve".
  REVIEWS=$((REVIEWS+1))
  local n="$REVIEWS" rc parsed
  status running "independent review $n by $REVIEW_MODEL"
  render review.md - "" | "${SANDBOX[@]}" review > "$DIR/review-$n.raw" 2>&1
  rc=$?
  parsed="$(python3 - "$DIR/review-$n" "$rc" "$REVIEW_MODEL" <<'PY' 2>/dev/null
import json, re, sys
base, rc, model = sys.argv[1], int(sys.argv[2]), sys.argv[3]
MARK = "\n=== REVIEW JSON ===\n"
text = open(base + ".raw", encoding="utf-8", errors="replace").read()
i = ("\n" + text).rfind(MARK)
log, raw = (text[:max(i - 1, 0)], text[i - 1 + len(MARK):]) if i >= 0 else (text, "")
open(base + ".log", "w", encoding="utf-8").write(log)
open(base + ".json", "w", encoding="utf-8").write(raw)
SECRET = re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+\S+)")
def clean(value, limit):
    t = " ".join(str(value).split())
    t = re.sub(r"[A-Za-z][A-Za-z0-9+.-]*://\S+", "[link removed]", t)
    t = SECRET.sub("[redacted]", t)[:limit]
    t = t.replace("<", "&lt;").replace(">", "&gt;").replace("](", "] (")
    return re.sub(r"@(?=\w)", "@\u200b", t)
def fail(reason):
    open(base + ".comment.md", "w", encoding="utf-8").write(
        f"## Independent review ({clean(model, 64)})\n\n**Review failed: {reason}.** "
        "This is not an approval; the PR needs a human review.\n")
    open(base + ".blocking.txt", "w", encoding="utf-8").write("")
    print("failed 0 0")
    sys.exit(0)
if rc != 0:
    fail(f"the reviewer run ended with exit code {rc}")
try:
    data = json.loads(raw)
    assert isinstance(data, dict) and data.get("verdict") in ("approve", "changes")
    assert isinstance(data.get("findings"), list) and len(data["findings"]) <= 100
    findings = []
    for f in data["findings"]:
        assert isinstance(f, dict) and f.get("severity") in ("blocking", "minor")
        assert isinstance(f.get("summary"), str) and f["summary"].strip()
        assert f.get("file") is None or isinstance(f["file"], str)
        line = f.get("line")
        assert line is None or (isinstance(line, int) and not isinstance(line, bool) and line >= 1)
        where = clean(f.get("file") or "", 200) + (f":{line}" if line else "")
        findings.append((f["severity"], where, clean(f["summary"], 600)))
except (ValueError, AssertionError):
    fail("the reviewer output is not valid JSON in the expected shape")
blocking = [x for x in findings if x[0] == "blocking"]
minor = [x for x in findings if x[0] == "minor"]
verdict = "approve" if data["verdict"] == "approve" and not blocking else "changes"
def render(items):
    return "".join(f"- `{w}` — {s}\n" if w else f"- {s}\n" for _, w, s in items)
out = [f"## Independent review ({clean(model, 64)})\n\n",
       "**Verdict: approve**\n" if verdict == "approve" else "**Verdict: changes requested**\n"]
if blocking:
    out.append("\n**Blocking**\n" + render(blocking))
if minor:
    out.append("\n**Minor**\n" + render(minor))
if not findings:
    out.append("\nNo findings.\n")
if verdict == "changes" and not blocking:
    out.append("\nThe reviewer asks for changes but named no blocking finding; a human decides.\n")
open(base + ".comment.md", "w", encoding="utf-8").write("".join(out))
open(base + ".blocking.txt", "w", encoding="utf-8").write("".join(
    f"- [blocking] {w or 'general'}: {s}\n" for _, w, s in blocking))
print(verdict, len(blocking), len(minor))
PY
)"
  [ -n "$parsed" ] || { parsed="failed 0 0"; echo "Review failed: the review output could not be processed. This is not an approval." > "$DIR/review-$n.comment.md"; }
  read -r REVIEW_VERDICT REVIEW_BLOCKING REVIEW_MINOR <<<"$parsed"
  log_cost "review-$n" "$DIR/review-$n.log"
  ghx pr comment "$PR_URL" -R "$REPO" --body-file "$DIR/review-$n.comment.md" >/dev/null 2>&1 || true
}

close_task() {  # last commit on the PR branch: task Done + criteria ticked. Never fails the run (sets CLOSE_NOTE).
  # Only called after wait_checks was green, so nothing waits for checks on this commit. Reaches main with Jan's merge.
  CLOSE_NOTE=""
  if grep -q '^Labels: .*manual-close' <<<"$HEADER"; then CLOSE_NOTE="label manual-close: task not closed"; return 0; fi
  if grep -q '^Status: .*Done' <<<"$HEADER"; then CLOSE_NOTE="task is already Done"; return 0; fi
  cd "$CLONE" || { CLOSE_NOTE="task not closed (no clone): close it by hand"; return 0; }
  [ "$(git rev-parse --abbrev-ref HEAD)" = "$BRANCH" ] || { CLOSE_NOTE="task not closed (unexpected branch): close it by hand"; return 0; }
  local before checks summary i
  local -a acs=()
  before="$(git rev-parse HEAD)"
  checks="$(python3 - "$DIR/checks.json" 2>/dev/null <<'PY' || echo "see the PR checks"
import json, sys
print(", ".join(f'{x["name"]}={x["bucket"]}' for x in json.load(open(sys.argv[1]))))
PY
)"
  summary="Implemented by the headless coder. Checks green on ${before:0:9} after $ROUND fix round(s): $checks. PR: $PR_URL. Done takes effect when the PR is merged."
  backlog task view "$TASK" --plain > "$DIR/task-close.txt" 2>&1
  for i in $(sed -nE 's/^- \[ \] #([0-9]+) .*/\1/p' "$DIR/task-close.txt"); do acs+=(--check-ac "$i"); done
  if ! backlog task edit "$TASK" -s Done ${acs[@]+"${acs[@]}"} --final-summary "$summary" > "$DIR/close.log" 2>&1; then
    git reset -q --hard "$before"; git clean -qfd -- backlog
    CLOSE_NOTE="task not closed (backlog edit failed, see close.log): close it by hand"; return 0
  fi
  git add -A
  git diff --cached --name-only -z | tr '\0' '\n' > "$DIR/close-files.txt"
  if [ ! -s "$DIR/close-files.txt" ]; then CLOSE_NOTE="task not closed (nothing changed): close it by hand"; return 0; fi
  if grep -qv '^backlog/' "$DIR/close-files.txt" || grep -qE "$PROTECTED" "$DIR/close-files.txt"; then
    git reset -q --hard "$before"; git clean -qfd
    CLOSE_NOTE="task not closed (the edit touched files outside backlog/): close it by hand"; return 0
  fi
  if ! git commit -q -m "$TASK: close task (checks green)" \
       -m "Set by the headless coder after e2e-pi passed. Takes effect when the PR is merged."; then
    git reset -q --hard "$before"; CLOSE_NOTE="task not closed (commit failed): close it by hand"; return 0
  fi
  if ! gitauth push -q origin "$BRANCH"; then
    git reset -q --hard "$before"; CLOSE_NOTE="task not closed (push failed): close it by hand"; return 0
  fi
  CLOSE_NOTE="task set to Done in the PR's last commit (takes effect when merged)"
}

# ---- 2. implement --------------------------------------------------------------------------
ROUND=0; CI_USED=0; REVIEWS=0; REVIEW_FIX=0; REVIEW_VERDICT=""; REVIEW_BLOCKING=0; REVIEW_MINOR=0; CLOSE_NOTE=""
"${SANDBOX[@]}" prepare "$BRANCH" > "$DIR/prepare.log" 2>&1 || stop "sandbox prepare failed (prepare.log)"
status running "Copilot implementing"
copilot_round implement.md - "" "implement"
local_gates
publish
open_pr

# ---- 3. PR checks, independent review, fix rounds ------------------------------------------
while :; do
  status running "waiting for PR checks (e2e-pi on the Pi)"
  if wait_checks; then
    REVIEW_NOTE="review skipped (no review-model configured)"; REVIEW_VERDICT=skipped
    if [ "$REVIEW_ON" = 1 ]; then
      review
      if [ "$REVIEW_VERDICT" = changes ] && [ "$REVIEW_BLOCKING" -gt 0 ] && [ "$REVIEW_FIX" -lt "$REVIEW_ROUNDS" ]; then
        REVIEW_FIX=$((REVIEW_FIX+1)); ROUND=$((ROUND+1))
        status running "review found $REVIEW_BLOCKING blocking finding(s) — Copilot fix review-fix-$REVIEW_FIX"
        copilot_round fix.md "$DIR/review-$REVIEWS.blocking.txt" "independent code review (blocking findings; the PR checks are green)" "review-fix-$REVIEW_FIX"
        local_gates
        publish
        continue
      fi
      case "$REVIEW_VERDICT" in
        approve) REVIEW_NOTE="review approved (${REVIEW_MINOR} minor finding(s))" ;;
        changes) status review "independent review: changes requested ($REVIEW_BLOCKING blocking, $REVIEW_MINOR minor) — findings in the PR comment; task stays In Progress: $PR_URL"; exit 1 ;;
        *)       status review "independent review failed (output unusable, see review-$REVIEWS.log) — not approved; task stays In Progress: $PR_URL"; exit 1 ;;
      esac
    fi
    close_task
    ghx pr comment "$PR_URL" -R "$REPO" --body "✅ All checks green (incl. \`e2e-pi\`) after $ROUND fix round(s). Ready for review — the coder never merges. ${REVIEW_NOTE:+Review: $REVIEW_NOTE.}${CLOSE_NOTE:+ Task: $CLOSE_NOTE.}" >/dev/null 2>&1 || true
    status green "PR ready for review: $PR_URL — $REVIEW_NOTE${CLOSE_NOTE:+ — $CLOSE_NOTE}"; exit 0
  fi
  [ "$CI_USED" -ge "$CI_ROUNDS" ] && { status failed "checks still red after $CI_ROUNDS fix rounds: $(cut -d' ' -f1 "$DIR/ci-$ROUND.txt" | tr '\n' ' ')"; exit 1; }
  grep -q '^e2e-pi skipping' "$DIR/ci-$ROUND.txt" \
    && stop "e2e-pi was skipped — PR author not allowed for the Pi runner (E2E_PI_ACTORS / allowed-actors)?"
  FAIL_FILE="$(failure_text)"
  CI_USED=$((CI_USED+1)); ROUND=$((ROUND+1)); status running "checks red ($(cut -d' ' -f1 "$DIR/ci-$((ROUND-1)).txt" | tr '\n' ' ')) — Copilot fix $CI_USED/$CI_ROUNDS"
  copilot_round fix.md "$FAIL_FILE" "PR checks on GitHub (e2e-pi runs the E2E suite on the Pi; hassfest/HACS validate)" "ci-fix-$CI_USED"
  local_gates
  publish
done
