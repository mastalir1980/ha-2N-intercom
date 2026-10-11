#!/usr/bin/env bash
# Nightly check (launchd). Runs the read-only pipeline ONLY when something changed:
#   - new commit on origin/main
#   - different intercom firmware (swVersion)
#   - newer Home Assistant image (staging is pulled first)
# Never switches relays.
set -uo pipefail

E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$E2E_DIR/.." && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$HOME/.npm-global/bin:$PATH"
set -a; [ -f "$E2E_DIR/.env" ] && . "$E2E_DIR/.env"; set +a
. "$E2E_DIR/scripts/pi.sh"
mkdir -p "$E2E_DIR/state" "$E2E_DIR/reports"
LOG="$E2E_DIR/reports/nightly.log"
exec >>"$LOG" 2>&1
echo "=== nightly $(date -Is 2>/dev/null || date)"
# Running on the Pi itself: keep the e2e scripts in the clone current (ff-only, never rewrites)
if [ "${PI_SSH:-}" = "local" ]; then git -C "$REPO_DIR" pull -q --ff-only || echo "git pull failed (local changes?)"; fi

cd "$REPO_DIR"
git fetch -q origin || { echo "git fetch failed"; exit 2; }
MAIN_SHA="$(git rev-parse --short origin/main)"

FW="$(cd "$E2E_DIR" && "$E2E_DIR/.venv/bin/python" - <<'PY'
import sys; sys.path.insert(0, ".")
from e2elib import env; from e2elib.twon import TwoN
c = env.load()
try:
    print(TwoN(c["INTERCOM_HOST"], c["INTERCOM_USER"], c["INTERCOM_PASSWORD"],
               c.get("INTERCOM_PROTOCOL", "https"), env.flag(c, "INTERCOM_VERIFY_SSL")).system_info().get("swVersion"))
except Exception as e:
    print(f"unreachable")
PY
)"
FW="${FW:-unreachable}"

# Pull newest HA image for staging; ID changes when a new HA release is out.
pi "cd '$PI_STAGING_DIR' && docker compose pull -q" || echo "pull failed"
HA_IMG="$(pi "docker image inspect --format '{{.Id}}' \${HA_IMAGE:-ghcr.io/home-assistant/home-assistant:stable}" 2>/dev/null | cut -c8-19)"

KEY="main=$MAIN_SHA fw=$FW ha=${HA_IMG:-unknown}"
LAST="$(cat "$E2E_DIR/state/last_nightly_key" 2>/dev/null || true)"
echo "state: $KEY (last: ${LAST:-none})"
if [ "$KEY" = "$LAST" ] && [ "${E2E_FORCE:-0}" != "1" ]; then
  echo "nothing changed — skip"; exit 0
fi

CHANGES=()
[[ "$LAST" != *"main=$MAIN_SHA"* ]] && CHANGES+=("new commit $MAIN_SHA")
[[ "$LAST" != *"fw=$FW"* ]] && CHANGES+=("intercom firmware $FW")
[[ "$LAST" != *"ha=${HA_IMG:-unknown}"* ]] && CHANGES+=("HA image ${HA_IMG:-unknown}")
TRIGGER="nightly: ${CHANGES[*]}"

bash "$E2E_DIR/run.sh" --ref origin/main --trigger "$TRIGGER"
rc=$?
# Remember the state even on failure: the bug is in the backlog, don't re-report every night.
echo "$KEY" > "$E2E_DIR/state/last_nightly_key"

if command -v osascript >/dev/null; then
  case $rc in
    0) msg="E2E OK ($TRIGGER)";;
    1) msg="E2E FAILED — bugy v backlogu ($TRIGGER)";;
    *) msg="E2E pipeline error ($TRIGGER)";;
  esac
  osascript -e "display notification \"$msg\" with title \"ha-2n-intercom\"" || true
fi
exit $rc
