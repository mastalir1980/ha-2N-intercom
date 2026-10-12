#!/usr/bin/env bash
# E2E for one commit, run on the Pi by the self-hosted GitHub Actions runner (user ha2n-ci).
# Called by .github/workflows/e2e-pi.yml (workflow + this script come from main, never the PR).
#
#   bash e2e/ci/pr-e2e.sh <full-40-char-sha>
#
# Read-only: never passes --relays. Physical safety is enforced by the intercom itself — the
# account in /etc/ha2n-ci/e2e.env and the staging config entry have no Control privilege.
# Staging is touched only through `sudo -u <staging-user> /usr/local/sbin/ha2n-staging`.
# Exit code: 0 passed, 1 tests failed, 2 pipeline error.
set -uo pipefail
PATH=/usr/local/bin:/usr/bin:/bin

SHA="${1:-}"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "usage: pr-e2e.sh <full-40-char-sha>" >&2; exit 2; }
CI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF=/etc/ha2n-ci/staging.conf
[ -r "$CONF" ] || { echo "missing $CONF — run e2e/ci/install-pi.sh on the Pi" >&2; exit 2; }
# shellcheck disable=SC1090
. "$CONF"
: "${STAGING_USER:?}" "${CI_HOME:?}"
E2E_ENV="${E2E_ENV:-/etc/ha2n-ci/e2e.env}"
VENV="$CI_HOME/venv"; REPORTS="$CI_HOME/reports"
REPO="${GITHUB_REPOSITORY:-mastalir1980/ha-2N-intercom}"
HELPER=(sudo -n -u "$STAGING_USER" /usr/local/sbin/ha2n-staging)
OWNER="ci-${GITHUB_RUN_ID:-manual$$}-${GITHUB_RUN_ATTEMPT:-1}"

TS="$(date +%Y%m%d-%H%M%S)"
REPORT="$REPORTS/$TS-${SHA:0:7}"
mkdir -p "$REPORT"; ln -sfn "$REPORT" "$REPORTS/latest"
WORK="$(mktemp -d)"
STAGE="init"; STATUS="error"; DEPLOYED=0

finish() {
  trap - EXIT INT TERM
  # unlock FIRST: on cancel the runner escalates to SIGKILL within seconds
  if [ "$DEPLOYED" = 1 ]; then
    "${HELPER[@]}" logs > "$REPORT/ha_container.log" 2>&1 &
    LOGS_PID=$!
  fi
  "${HELPER[@]}" unlock "$OWNER" >/dev/null 2>&1
  [ -n "${LOGS_PID:-}" ] && wait "$LOGS_PID"
  cat > "$REPORT/summary.json" <<JSON
{"timestamp": "$TS", "trigger": "pi-ci run ${GITHUB_RUN_ID:-manual}", "ref": "$SHA",
 "deployed_sha": "${SHA:0:7}", "status": "$STATUS",
 "failed_stage": "$( [ "$STATUS" = passed ] && echo "" || echo "$STAGE")", "relays": false}
JSON
  "$VENV/bin/python" "$CI_DIR/ci_summary.py" "$REPORT" "$E2E_ENV" > "$REPORT/ci_summary.md" 2>&1 \
    || echo "summary failed (status: $STATUS, stage: $STAGE)" > "$REPORT/ci_summary.md"
  cat "$REPORT/ci_summary.md"
  [ -n "${GITHUB_STEP_SUMMARY:-}" ] && cat "$REPORT/ci_summary.md" >> "$GITHUB_STEP_SUMMARY"
  rm -rf "$WORK"
  # keep the newest 50 reports
  ls -1d "$REPORTS"/2* 2>/dev/null | sort | head -n -50 | xargs -r rm -rf
  case "$STATUS" in passed) exit 0 ;; failed) exit 1 ;; *) exit 2 ;; esac
}
trap finish EXIT INT TERM

# Code under test runs with a clean environment: no GitHub token, no runner variables.
sandbox() { env -i PATH=/usr/local/bin:/usr/bin:/bin HOME="$WORK" LANG=C.UTF-8 \
  E2E_ENV_FILE="$E2E_ENV" E2E_REPORT_DIR="$REPORT" E2E_RELAY_NUMBERS= "$@"; }

echo "==> [1/4] checkout ${SHA:0:12} (logs stay on the Pi: $REPORT)"
STAGE="checkout"
{ git init -q "$WORK/src" &&
  git -C "$WORK/src" fetch -q --depth 1 "https://github.com/$REPO" "$SHA" &&
  git -C "$WORK/src" checkout -q --detach FETCH_HEAD; } > "$REPORT/checkout.log" 2>&1 || exit

echo "==> [2/4] staging lock + deploy"
STAGE="deploy"
"${HELPER[@]}" lock "$OWNER" > "$REPORT/lock.log" 2>&1 || exit
DEPLOYED=1
"${HELPER[@]}" deploy "$OWNER" "$SHA" > "$REPORT/deploy.log" 2>&1 || exit
sleep "${E2E_SETTLE_SECONDS:-20}"
(cd "$WORK/src" && sandbox "$VENV/bin/python" e2e/scripts/prune_orphans.py --ref HEAD \
   --out "$REPORT/pruned_entities.json") > "$REPORT/prune.log" 2>&1 || echo "    prune failed (continuing)"

echo "==> [3/4] E2E tests (read-only, no relays)"
STAGE="e2e"
# -m "not relay": defence in depth on top of the read-only 2N account (the marker comes from the branch)
(cd "$WORK/src/e2e" && sandbox "$VENV/bin/python" -m pytest -p no:cacheprovider -m "not relay" \
   --junitxml="$REPORT/junit.xml") > "$REPORT/pytest.log" 2>&1
rc=$?
if [ "$rc" -eq 0 ]; then STATUS="passed"; elif [ "$rc" -eq 1 ]; then STATUS="failed"; else STATUS="error"; fi
echo "==> [4/4] result: $STATUS"
