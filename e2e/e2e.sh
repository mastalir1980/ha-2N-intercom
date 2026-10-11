#!/usr/bin/env bash
# Entry point for the E2E pipeline. Usage: bash e2e/e2e.sh <command>
#
#   setup       local venv + Backlog.md CLI + e2e/.env from template
#   bootstrap   one-time: staging HA on the Pi, token, 2N config entry
#   run         full pipeline on HEAD (read-only)          [extra args go to run.sh]
#   wip         full pipeline on the working tree (uncommitted changes)
#   relays      manual run incl. PHYSICAL relay tests (asks for confirmation)
#   tests       only pytest against what is already deployed
#   schedule    install nightly launchd job (03:30)
#   unschedule  remove it
#   report      latest summary + agent triage
#   reset-entry deploy working tree to staging, delete + re-create the 2N config entry
#               (needed when config-flow logic changed, e.g. protocol auto-detection)
#   hermes      for a Hermes --no-agent cron job on the Pi: runs nightly.sh (no relays,
#               no LLM triage) and prints a short summary ONLY when a test run happened
#   install-slash-command   copy /e2e command into .claude/commands
set -euo pipefail
E2E="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$E2E/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/cz.mastix.ha2n-e2e.plist"
cmd="${1:-help}"; shift || true

case "$cmd" in
  setup)
    python3 -m venv "$E2E/.venv"
    "$E2E/.venv/bin/pip" install -q -r "$E2E/requirements.txt"
    command -v backlog >/dev/null || npm i -g backlog.md
    if [ ! -f "$E2E/.env" ]; then
      cp "$E2E/.env.example" "$E2E/.env"; chmod 600 "$E2E/.env"; echo "→ vyplň e2e/.env"
    fi ;;
  bootstrap) "$E2E/.venv/bin/python" "$E2E/scripts/bootstrap_staging.py" ;;
  run)       bash "$E2E/run.sh" "$@" ;;
  wip)       bash "$E2E/run.sh" --worktree "$@" ;;
  relays)
    relays="$(grep '^E2E_RELAY_NUMBERS' "$E2E/.env" | cut -d= -f2 | cut -d'#' -f1 | tr -d ' ')"
    read -r -p "Relé ${relays} se FYZICKY sepne (dveře/brána). Pokračovat? [y/N] " a
    [ "$a" = y ] || exit 1
    bash "$E2E/run.sh" --worktree --relays "$@" ;;
  tests)     cd "$E2E" && .venv/bin/python -m pytest "$@" ;;
  schedule)
    mkdir -p "$E2E/reports" "$(dirname "$PLIST")"
    sed "s#REPO_DIR#$REPO#g" "$E2E/launchd/cz.mastix.ha2n-e2e.plist" > "$PLIST"
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST" && echo "noční E2E naplánováno (03:30)" ;;
  unschedule) launchctl unload "$PLIST" 2>/dev/null || true; rm -f "$PLIST"; echo "odplánováno" ;;
  report)
    cat "$E2E/reports/latest/summary.json"; echo
    cat "$E2E/reports/latest/triage.md" 2>/dev/null || true ;;
  reset-entry)
    E2E_DIR_PY="$E2E" "$E2E/.venv/bin/python" - <<'PY'
import os, sys; sys.path.insert(0, os.environ["E2E_DIR_PY"])
from e2elib import env; from e2elib.ha import HA
c = env.load(); env.assert_staging_url(c["HA_URL"])
ha = HA(c["HA_URL"], c["HA_TOKEN"])
for e in ha.entries():
    r = __import__("requests").delete(
        f"{ha.url}/api/config/config_entries/entry/{e['entry_id']}",
        headers={"Authorization": f"Bearer {ha.token}"}, timeout=30)
    print(f"==> deleted staging entry {e['title']} ({r.status_code})")
PY
    "$E2E/.venv/bin/python" "$E2E/scripts/bootstrap_staging.py" ;;
  hermes)
    before="$(readlink "$E2E/reports/latest" 2>/dev/null || true)"
    E2E_AGENT=0 bash "$E2E/nightly.sh" || true
    after="$(readlink "$E2E/reports/latest" 2>/dev/null || true)"
    # nothing changed -> print nothing -> Hermes sends nothing
    if [ -n "$after" ] && [ "$after" != "$before" ]; then
      "$E2E/.venv/bin/python" "$E2E/scripts/summary.py" "$after"
    fi
    exit 0 ;;
  install-slash-command)
    mkdir -p "$REPO/.claude/commands"
    cp "$E2E/agent/claude-command-e2e.md" "$REPO/.claude/commands/e2e.md" && echo "/e2e nainstalováno" ;;
  *) sed -n '2,19p' "$0" ;;
esac
