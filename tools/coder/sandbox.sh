#!/usr/bin/env bash
# ha2n-coder sandbox — runs as user ha2n-copilot, the only place where Copilot and the code it writes run.
# Installed root-owned as /usr/local/lib/ha2n-coder/sandbox.sh by tools/coder/install-vm.sh; the
# orchestrator (user ha2n-coder) may call it only via:
#     sudo -n -u ha2n-copilot /usr/local/lib/ha2n-coder/sandbox.sh <verb> [arg]
# This user has NO token for the repo. It sees only its own Copilot token (Copilot Requests only).
# Nothing leaves the sandbox except stdout: the Copilot transcript, gate output and the patch.
#
#   sandbox.sh prepare <branch>   fresh clone of main into ~/work/src, new local branch
#   sandbox.sh copilot            run Copilot CLI headless on the prompt read from stdin
#   sandbox.sh gates              unit tests + validate.py + py_compile (Python 3.12 venv)
#   sandbox.sh patch              the whole change vs origin/main as one plain diff (stdout)
#
# Exit codes: 0 ok, 1 failed, 2 usage/config error, 3 Copilot asked to stop (.agent-stop).
set -uo pipefail
umask 022
ME="$(id -un)"
HOME="$(getent passwd "$ME" | cut -d: -f6)"; export HOME
VENV=/opt/ha2n-coder/py312   # root-owned: the sandbox cannot tamper with its own toolchain
PATH="$VENV/bin:/usr/local/bin:/usr/bin:/bin"; export PATH
cd "$HOME" || exit 2   # sudo keeps the caller's cwd, which this user cannot read
REPO_URL="https://github.com/mastalir1980/ha-2N-intercom.git"
WORK="$HOME/work"; SRC="$WORK/src"
COPILOT_TOKEN_FILE=/etc/ha2n-coder/copilot.token
die() { echo "sandbox: $*" >&2; exit 2; }
[ "$ME" = ha2n-copilot ] || die "must run as ha2n-copilot"
mkdir -p "$WORK"

case "${1:-}" in
  prepare)
    br="${2:-}"
    [[ "$br" =~ ^task-[0-9]+(\.[0-9]+)?-[a-z0-9-]{1,50}$ ]] || die "invalid branch name"
    # Nothing survives from the previous run: no leftover processes, no config, caches or Copilot state.
    pkill -9 -u "$ME" --older 5 2>/dev/null || true
    find "$HOME" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null
    mkdir -p "$WORK"
    git clone -q "$REPO_URL" "$SRC" || exit 1
    cd "$SRC" || exit 1
    git checkout -q -b "$br" origin/main
    git config user.name "ha2n-coder (Copilot)"
    git config user.email "ha2n-coder@localhost"
    git config core.hooksPath /dev/null
    echo "prepared $br at $(git rev-parse --short HEAD)" ;;

  copilot)
    [ -d "$SRC/.git" ] || die "run prepare first"
    [ -r "$COPILOT_TOKEN_FILE" ] || die "missing $COPILOT_TOKEN_FILE (sudo ha2n-coder-set-token copilot)"
    cat > "$WORK/prompt.md"
    [ -s "$WORK/prompt.md" ] || die "empty prompt"
    MODEL_ARGS=()   # optional, root-owned: /etc/ha2n-coder/model holds one model id (else Copilot's default)
    if [ -r /etc/ha2n-coder/model ]; then
      m="$(tr -d '[:space:]' < /etc/ha2n-coder/model)"
      [[ "$m" =~ ^[A-Za-z0-9._-]{1,64}$ ]] || die "invalid model id in /etc/ha2n-coder/model"
      MODEL_ARGS=(--model "$m"); echo "model: $m"
    else
      echo "model: Copilot default"
    fi
    if [ -r /etc/ha2n-coder/effort ]; then   # optional, root-owned: reasoning effort
      e="$(tr -d '[:space:]' < /etc/ha2n-coder/effort)"
      [[ "$e" =~ ^(none|minimal|low|medium|high|xhigh|max)$ ]] || die "invalid effort in /etc/ha2n-coder/effort"
      MODEL_ARGS+=(--reasoning-effort "$e"); echo "reasoning effort: $e"
    fi
    cd "$SRC" || exit 1
    rm -f .agent-stop
    # Clean environment: only what Copilot needs. No repo token exists for this user at all.
    env -i HOME="$HOME" PATH="$PATH" LANG=C.UTF-8 TERM=dumb \
      COPILOT_GITHUB_TOKEN="$(cat "$COPILOT_TOKEN_FILE")" \
      timeout "${COPILOT_TIMEOUT:-50m}" # No -s (silent): with it Copilot prints nothing but the answer, and run-task.sh needs the
      # "AI Credits" / "Tokens" summary at the end of the output to log the cost (cost.csv).
      copilot -p "$(cat "$WORK/prompt.md")" --no-ask-user "${MODEL_ARGS[@]}" \
        --allow-all-tools --deny-tool 'shell(git push)' --deny-tool 'shell(gh)' --deny-tool 'url'
    rc=$?
    if [ -f .agent-stop ]; then
      echo "=== Copilot asked to stop ==="; cat .agent-stop; rm -f .agent-stop; exit 3
    fi
    exit "$rc" ;;

  gates)
    cd "$SRC" || die "run prepare first"
    python3 --version
    python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || die "Python 3.12+ venv missing ($VENV)"
    echo "== unit tests";  python3 -m unittest discover -s tests -t tests 2>&1 | tail -40; r1=${PIPESTATUS[0]}
    echo "== validate.py"; python3 validate.py 2>&1 | tail -20; r2=${PIPESTATUS[0]}
    echo "== py_compile";  python3 -m py_compile custom_components/2n_intercom/*.py; r3=$?
    [ "$r1$r2$r3" = 000 ] && { echo "GATES: green"; exit 0; }
    echo "GATES: red (unit=$r1 validate=$r2 compile=$r3)"; exit 1 ;;

  patch)
    cd "$SRC" || die "run prepare first"
    rm -f .agent-stop
    if [ -n "$(git status --porcelain)" ]; then
      git add -A && git commit -q -m "chore: changes left uncommitted by Copilot" >&2
    fi
    [ "$(git rev-list --count origin/main..HEAD)" -gt 0 ] || { echo "no commits" >&2; exit 1; }
    git diff --no-renames --full-index origin/main HEAD ;;

  *) die "usage: sandbox.sh prepare <branch> | copilot < prompt | gates | patch" ;;
esac
