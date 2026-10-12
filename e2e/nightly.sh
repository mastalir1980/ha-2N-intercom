#!/usr/bin/env bash
# Nightly check (launchd). Runs the read-only pipeline ONLY when something changed:
#   - new commit on any origin branch, or the set of origin branches changed
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
RAN=0; RC_ANY=""; RUNS=(); rc=0
# Running on the Pi itself: keep the e2e scripts in the clone current (ff-only, never rewrites)
if [ "${PI_SSH:-}" = "local" ]; then git -C "$REPO_DIR" pull -q --ff-only || echo "git pull failed (local changes?)"; fi

cd "$REPO_DIR"
git fetch -q origin --prune || { echo "git fetch failed"; exit 2; }
MAIN_SHA="$(git rev-parse --short origin/main)"

# --- Vsechny puvodni vetve (ne jen main): testujeme i vyvijejece vetve ---------
# Barevné vyloučení: HEAD, remotes/origin/HEAD a doc-predpony; hlidaji se ostatní.
# origin/main always runs first, the rest in alphabetical order.
ALL_BRANCHES="$(git for-each-ref --format='%(refname:short)' refs/remotes/origin \
  | grep -v -e '^origin/HEAD$' | sort)"
BRANCHES="$( { grep -x 'origin/main' <<<"$ALL_BRANCHES"; grep -vx 'origin/main' <<<"$ALL_BRANCHES"; } || true)"
echo "branches under watch: $(echo "$BRANCHES" | tr '\n' ' ')"

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

CHANGES=()
for B in $BRANCHES; do
  SHA="$(git rev-parse --short "origin/${B#origin/}")"
  LAST_SHA="$(cat "$E2E_DIR/state/last_sha_${B//\//_}" 2>/dev/null || true)"
  if [ "$SHA" != "$LAST_SHA" ]; then
    if [ -n "$LAST_SHA" ]; then CHANGES+=("$B: new commit $SHA"); fi
  fi
done
BRANCHES_LAST="$(cat "$E2E_DIR/state/last_nightly_branches" 2>/dev/null || true)"
[ "$(sort <<<"$BRANCHES")" != "$BRANCHES_LAST" ] && CHANGES+=("branch set changed")
FW_LAST="$(cat "$E2E_DIR/state/last_nightly_fw" 2>/dev/null || true)"
[ "$FW" != "$FW_LAST" ] && CHANGES+=("intercom firmware $FW")
HA_LAST="$(cat "$E2E_DIR/state/last_nightly_haimg" 2>/dev/null || true)"
[ "${HA_IMG:-unknown}" != "${HA_LAST:-}" ] && CHANGES+=("HA image ${HA_IMG:-unknown}")
TRIGGER="nightly: ${CHANGES[*]}"
if [ "${#CHANGES[@]}" -eq 0 ] && [ "${E2E_FORCE:-0}" != "1" ]; then
  echo "nothing changed — skip"; exit 0
fi
echo "trigger: $TRIGGER"

# --- Běh pro každou změněnou větev (main vždy první) ---------------------------
FAILED_BRANCHES=()
for B in $BRANCHES; do
  SHA="$(git rev-parse --short "origin/${B#origin/}")"
  LAST_SHA="$(cat "$E2E_DIR/state/last_sha_${B//\//_}" 2>/dev/null || true)"
  [ "$SHA" = "$LAST_SHA" ] && { echo "branch $B unchanged ($SHA) — skip"; continue; }
  if [ "$B" != "origin/main" ] && [ "$(git merge-base --is-ancestor "$B" origin/main && echo yes || echo no)" = "yes" ]; then
    echo "branch $B is already merged into main — skip"
    echo "$SHA" > "$E2E_DIR/state/last_sha_${B//\//_}"
    continue
  fi
  if ! git cat-file -e "$B:custom_components/2n_intercom/manifest.json" 2>/dev/null; then
    echo "branch $B has no custom_components/2n_intercom (old layout) — skip"
    echo "$SHA" > "$E2E_DIR/state/last_sha_${B//\//_}"
    continue
  fi
  echo "==> running E2E for $B ($SHA)"
  bash "$E2E_DIR/run.sh" --ref "$B" --trigger "$TRIGGER branch $B"
  brc=$?
  RAN=$((RAN+1)); RC_ANY="$brc"; RUNS+=("$B:$brc")
  echo "$SHA" > "$E2E_DIR/state/last_sha_${B//\//_}"
  if [ "$brc" -ne 0 ]; then FAILED_BRANCHES+=("$B"); fi
done
rc=0; [ "${#FAILED_BRANCHES[@]}" -gt 0 ] && rc=1
[ "$RAN" -eq 0 ] && rc=0
# Remember global state even on failure: the bugs are in the backlog, don't re-report every night.
echo "$FW" > "$E2E_DIR/state/last_nightly_fw"
echo "${HA_IMG:-unknown}" > "$E2E_DIR/state/last_nightly_haimg"
sort <<<"$BRANCHES" > "$E2E_DIR/state/last_nightly_branches"
echo "$TRIGGER" > "$E2E_DIR/state/last_nightly_trigger"
if [ "$RAN" -eq 0 ]; then
  echo "no branch produced a run (all unchanged/merged)"
  exit 0
fi

if command -v osascript >/dev/null; then
  case $rc in
    0) msg="E2E OK ($TRIGGER)";;
    1) msg="E2E FAILED — bugy v backlogu ($TRIGGER)";;
    *) msg="E2E pipeline error ($TRIGGER)";;
  esac
  osascript -e "display notification \\\"$msg\\\" with title \\\"ha-2n-intercom\\\"" || true
fi
# human-readable run line for the summary script
: > "$E2E_DIR/state/last_nightly_runs"
for r in "${RUNS[@]}"; do echo "$r" >> "$E2E_DIR/state/last_nightly_runs"; done
printf '%s\n' "${FAILED_BRANCHES[*]}" > "$E2E_DIR/state/last_nightly_failed"
exit $rc
