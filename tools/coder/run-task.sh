#!/usr/bin/env bash
# ha2n-run-task — turn one ready Backlog task into a PR, on Jan's command only.
# Runs as user ha2n-coder (installed root-owned as /usr/local/bin/ha2n-run-task by install-vm.sh).
# Hermes (user hermes) may start it only via:  sudo -n -u ha2n-coder /usr/local/bin/ha2n-run-task TASK-12
#
#   ha2n-run-task <TASK-ID>               start in the background, print the run id and exit
#   ha2n-run-task --foreground <TASK-ID>  run attached (for debugging)
#
# Flow: ready check → sandbox clone → Copilot implements → local gates (≤2 local fix rounds) →
# patch checked for protected paths/size → applied in our own clone → push + PR (Jan's token) →
# wait for PR checks incl. e2e-pi → on failure feed the public log back to Copilot (≤3 rounds) → report.
# Copilot never sees the repo token; this script never runs code from the repo (only git, gh, backlog).
# Never merges. State: /var/lib/ha2n-coder/runs/<run>/{status,run.log,*.patch}; see ha2n-task-status.
set -uo pipefail
umask 027
PATH=/usr/local/bin:/usr/bin:/bin
ME="$(id -un)"; [ "$ME" = ha2n-coder ] || { echo "must run as ha2n-coder" >&2; exit 2; }
HOME="$(getent passwd "$ME" | cut -d: -f6)"; export HOME
REPO="mastalir1980/ha-2N-intercom"
BASE="/var/lib/ha2n-coder"; CLONE="$BASE/repo"; RUNS="$BASE/runs"
LIB=/usr/local/lib/ha2n-coder
SANDBOX=(sudo -n -u ha2n-copilot "$LIB/sandbox.sh")
REPO_TOKEN_FILE=/etc/ha2n-coder/repo.token
PROTECTED='(^|/)\.git|^(\.github/|e2e/ci/|e2e/scripts/|e2e/run\.sh$|e2e/nightly\.sh$|e2e/e2e\.sh$|e2e/staging/|e2e/\.env|e2e/tests/conftest\.py$|tools/coder/|CLAUDE\.md$|backlog/config\.yml$)'
MAX_FILES=40; MAX_LINES=2500; LOCAL_ROUNDS=2; CI_ROUNDS=3; CHECKS_TIMEOUT=$((45*60))

FG=0; [ "${1:-}" = "--foreground" ] && { FG=1; shift; }
TASK="${1:-}"
[[ "$TASK" =~ ^TASK-[0-9]+(\.[0-9]+)?$ ]] || { echo "usage: ha2n-run-task [--foreground] TASK-<n>" >&2; exit 2; }

if [ "$FG" = 0 ]; then
  RUN="$(date +%Y%m%d-%H%M%S)-$TASK"
  mkdir "$RUNS/$RUN" 2>/dev/null || { echo "a run of $TASK was started this second already" >&2; exit 2; }
  setsid nohup "$0" --foreground "$TASK" --run "$RUN" > "$RUNS/$RUN/run.log" 2>&1 < /dev/null &
  echo "started $RUN — status: ha2n-task-status $RUN"; exit 0
fi
shift
RUN="${2:-}"; [ "${1:-}" = "--run" ] && [ -n "$RUN" ] || RUN="$(date +%Y%m%d-%H%M%S)-$TASK"
[[ "$RUN" =~ ^[0-9]{8}-[0-9]{6}-TASK-[0-9]+(\.[0-9]+)?$ ]] || { echo "invalid run id" >&2; exit 2; }
DIR="$RUNS/$RUN"; mkdir -p "$DIR"

status() {  # status <state> <message>  — states: running, stopped, green, failed
  { echo "task=$TASK"; echo "state=$1"; echo "message=$2"; echo "branch=${BRANCH:-}"; echo "pr=${PR_URL:-}"
    echo "round=${ROUND:-0}"; echo "updated=$(date -Is)"; } > "$DIR/status.tmp" && mv "$DIR/status.tmp" "$DIR/status"
  echo "[$(date +%H:%M:%S)] $1: $2"
}
stop() { status stopped "$*"; exit 1; }

exec 9>"$BASE/run.lock"
flock -n 9 || stop "another task is running (one at a time)"
ln -sfn "$DIR" "$RUNS/latest"
[ -r "$REPO_TOKEN_FILE" ] || stop "missing repo token (sudo ha2n-coder-set-token repo)"
TOKEN="$(cat "$REPO_TOKEN_FILE")"
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
{ git checkout -q --detach origin/main && git reset -q --hard && git clean -qfdx; } || stop "cannot reset own clone"
backlog task view "$TASK" --plain > "$DIR/task.txt" 2>&1 || stop "task $TASK not found"
HEADER="$(sed '/^Description:/q' "$DIR/task.txt")"   # only the metadata part, not the free text
grep -q '^Status: .*To Do' <<<"$HEADER"   || stop "task is not 'To Do' — not ready for the coder"
grep -q '^Assignee: .*@copilot' <<<"$HEADER" || stop "task is not assigned to @copilot — not ready"
if awk '/^Depends on/{f=1;next} /^Dependents|^Description/{f=0} f && /TASK-/ && !/completed/' "$DIR/task.txt" | grep -q .; then
  stop "task has dependencies that are not done"
fi
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

copilot_round() {  # copilot_round <template> <failure-file|-> <where>
  render "$1" "$2" "$3" | "${SANDBOX[@]}" copilot > "$DIR/copilot-$ROUND.log" 2>&1
  local rc=$?
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
    copilot_round fix.md "$DIR/gates-$ROUND-$((i-1)).log" "local gates (unit tests / validate.py / py_compile)"
  done
}

publish() {  # take the diff from the sandbox, apply it, check what is ACTUALLY staged, commit, push
  "${SANDBOX[@]}" patch > "$DIR/change-$ROUND.diff" 2> "$DIR/patch-$ROUND.log" || stop "no changes produced"
  { git checkout -q -B "$BRANCH" origin/main && git reset -q --hard && git clean -qfdx; } || stop "cannot reset own clone"
  git apply --index --whitespace=nowarn "$DIR/change-$ROUND.diff" 2> "$DIR/apply-$ROUND.log" \
    || stop "diff does not apply on main (apply-$ROUND.log)"
  git diff --cached --no-renames --name-only -z | tr '\0' '\n' > "$DIR/files-$ROUND.txt"
  [ -s "$DIR/files-$ROUND.txt" ] || stop "no changes produced"
  if grep -E "$PROTECTED" "$DIR/files-$ROUND.txt" > "$DIR/protected.txt"; then
    stop "change touches protected paths: $(head -5 "$DIR/protected.txt" | tr '\n' ' ')"
  fi
  git diff --cached --no-renames --summary | grep -Eq 'mode (120000|160000)|mode change' \
    && stop "symlinks, submodules and file-mode changes are not allowed"
  git diff --cached --no-renames --numstat | awk '$1=="-"' | grep -q . && stop "binary files are not allowed"
  local n lines
  n="$(wc -l < "$DIR/files-$ROUND.txt")"
  lines="$(git diff --cached --no-renames --numstat | awk '{a+=$1; d+=$2} END {print a+d}')"
  [ "$n" -le "$MAX_FILES" ] && [ "$lines" -le "$MAX_LINES" ] || stop "change too big for one PR ($n files, $lines lines)"
  git commit -q -m "$TASK: $TITLE" -m "Implemented by GitHub Copilot CLI (headless, ha2n-coder), round $ROUND." \
    || stop "commit failed"
  gitauth push -q --force-with-lease origin "$BRANCH" || stop "push failed"
  status running "pushed $(git rev-parse --short HEAD) ($n files, $lines lines)"
}

open_pr() {
  ghx label create agent -R "$REPO" --color 5319e7 --description "Opened by the headless coder" >/dev/null 2>&1 || true
  {
    echo "Implements **$TASK** — $TITLE"; echo
    echo "Opened by **ha2n-coder** (GitHub Copilot CLI, headless on the VM) on Jan's command."
    echo "Local gates (unit tests, validate.py, py_compile on Python 3.12) were green before push;"
    echo "E2E runs as the \`e2e-pi\` check. The task is left *In Progress*: acceptance criteria are"
    echo "ticked and the task set Done during review, after \`e2e-pi\` is green."
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

# ---- 2. implement --------------------------------------------------------------------------
ROUND=0
"${SANDBOX[@]}" prepare "$BRANCH" > "$DIR/prepare.log" 2>&1 || stop "sandbox prepare failed (prepare.log)"
status running "Copilot implementing"
copilot_round implement.md - ""
local_gates
publish
open_pr

# ---- 3. PR checks + fix rounds -------------------------------------------------------------
while :; do
  status running "waiting for PR checks (e2e-pi on the Pi)"
  if wait_checks; then
    ghx pr comment "$PR_URL" -R "$REPO" --body "✅ All checks green (incl. \`e2e-pi\`) after $ROUND fix round(s). Ready for review — the coder never merges." >/dev/null 2>&1 || true
    status green "PR ready for review: $PR_URL"; exit 0
  fi
  [ "$ROUND" -ge "$CI_ROUNDS" ] && { status failed "checks still red after $CI_ROUNDS fix rounds: $(cut -d' ' -f1 "$DIR/ci-$ROUND.txt" | tr '\n' ' ')"; exit 1; }
  grep -q '^e2e-pi skipping' "$DIR/ci-$ROUND.txt" \
    && stop "e2e-pi was skipped — PR author not allowed for the Pi runner (E2E_PI_ACTORS / allowed-actors)?"
  FAIL_FILE="$(failure_text)"
  ROUND=$((ROUND+1)); status running "checks red ($(cut -d' ' -f1 "$DIR/ci-$((ROUND-1)).txt" | tr '\n' ' ')) — Copilot fix $ROUND/$CI_ROUNDS"
  copilot_round fix.md "$FAIL_FILE" "PR checks on GitHub (e2e-pi runs the E2E suite on the Pi; hassfest/HACS validate)"
  local_gates
  publish
done
