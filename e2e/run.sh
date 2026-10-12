#!/usr/bin/env bash
# Full pipeline: unit tests -> deploy to staging HA -> E2E vs real 2N -> agent triage.
#
#   e2e/run.sh [--ref <git-ref> | --worktree] [--relays] [--pull] [--no-agent] [--trigger <text>]
#
# Exit code: 0 green, 1 tests failed, 2 pipeline error (deploy/unit/infra).
# Report: e2e/reports/<timestamp>/ (summary.json, junit.xml, logs, triage.md)
set -uo pipefail

E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$E2E_DIR/.." && pwd)"
set -a; [ -f "$E2E_DIR/.env" ] && . "$E2E_DIR/.env"; set +a
. "$E2E_DIR/scripts/pi.sh"
. "$E2E_DIR/scripts/lock.sh"

DEPLOY_ARGS=(); PYTEST_ARGS=(); AGENT="${E2E_AGENT:-1}"; TRIGGER="manual"; REF_LABEL="HEAD"
while [ $# -gt 0 ]; do
  case "$1" in
    --ref) DEPLOY_ARGS+=(--ref "$2"); REF_LABEL="$2"; shift 2 ;;
    --worktree) DEPLOY_ARGS+=(--worktree); REF_LABEL="worktree"; shift ;;
    --pull) DEPLOY_ARGS+=(--pull); shift ;;
    --relays) PYTEST_ARGS+=(--relays); shift ;;
    --no-agent) AGENT=0; shift ;;
    --trigger) TRIGGER="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

TS="$(date +%Y%m%d-%H%M%S)"
REPORT="$E2E_DIR/reports/$TS"
mkdir -p "$REPORT"
ln -sfn "$REPORT" "$E2E_DIR/reports/latest"
PY="$E2E_DIR/.venv/bin/python"
[ -x "$PY" ] || { echo "run e2e/e2e.sh setup first" >&2; exit 2; }

STAGE="init"; STATUS="error"
finish() {
  local sha; sha="$(cat "$E2E_DIR/state/last_deployed_sha" 2>/dev/null || echo unknown)"
  cat > "$REPORT/summary.json" <<EOF
{"timestamp": "$TS", "trigger": "$TRIGGER", "ref": "$REF_LABEL", "deployed_sha": "$sha",
 "status": "$STATUS", "failed_stage": "$( [ "$STATUS" = passed ] && echo "" || echo "$STAGE")",
 "relays": $( [[ " ${PYTEST_ARGS[*]-} " == *" --relays "* ]] && echo true || echo false )}
EOF
  echo "==> result: $STATUS (stage: $STAGE) — report: $REPORT"
}

# ---- 1. unit tests + static validation (fast, local) -------------------------
STAGE="unit"
echo "==> [1/4] unit tests + validate"
(
  cd "$REPO_DIR" &&
  "$PY" -m unittest discover -s tests -t tests &&
  "$PY" validate.py &&
  "$PY" -m py_compile custom_components/2n_intercom/*.py
) > "$REPORT/unit.log" 2>&1
if [ $? -ne 0 ]; then
  tail -30 "$REPORT/unit.log"; STATUS="failed"
else
  # ---- 2. deploy to staging HA ------------------------------------------------
  STAGE="deploy"
  # One run at a time on the shared staging HA (Mac, nightly and the Pi CI runner).
  LOCK_OWNER="run-$(hostname -s 2>/dev/null || echo host)-$$"
  trap 'staging_unlock "$LOCK_OWNER"' EXIT
  echo "==> [2/4] deploy to staging HA"
  if ! staging_lock "$LOCK_OWNER"; then
    STATUS="error"
  elif ! bash "$E2E_DIR/scripts/deploy.sh" ${DEPLOY_ARGS[@]+"${DEPLOY_ARGS[@]}"} 2>&1 | tee "$REPORT/deploy.log"; then
    STATUS="error"
  else
    sleep "${E2E_SETTLE_SECONDS:-20}"  # let the integration finish setup + first log/subscribe
    # Staging HA is shared by all branches: drop restored entities whose platform module is
    # not in the code just deployed (left by another branch). Never aborts the run.
    echo "==> pruning orphaned entities left by other deploys"
    if [ "$REF_LABEL" = "worktree" ]; then PRUNE_SRC=(--worktree); else PRUNE_SRC=(--ref "$REF_LABEL"); fi
    "$PY" "$E2E_DIR/scripts/prune_orphans.py" "${PRUNE_SRC[@]}" --out "$REPORT/pruned_entities.json" 2>&1 \
      | tee "$REPORT/prune.log" || echo "    prune failed — see $REPORT/prune.log (continuing)"
    # ---- 3. E2E tests ---------------------------------------------------------
    STAGE="e2e"
    echo "==> [3/4] E2E tests against the intercom"
    ( cd "$E2E_DIR" && E2E_REPORT_DIR="$REPORT" "$PY" -m pytest ${PYTEST_ARGS[@]+"${PYTEST_ARGS[@]}"} \
        --junitxml="$REPORT/junit.xml" ) 2>&1 | tee "$REPORT/pytest.log"
    rc=${PIPESTATUS[0]}
    if [ "$rc" -eq 0 ]; then STATUS="passed"; elif [ "$rc" -eq 1 ]; then STATUS="failed"; else STATUS="error"; fi
  fi
fi

# Container log for the agent (last 400 lines, integration lines first)
if [ "$STAGE" != "unit" ]; then
  pi "docker logs --tail 400 ${HA_CONTAINER:-ha-staging} 2>&1" > "$REPORT/ha_container.log" 2>/dev/null || true
  # Free the Pi's RAM between runs (next run recreates the container anyway)
  if [ "${E2E_STOP_STAGING:-0}" = "1" ]; then
    pi "cd '$PI_STAGING_DIR' && docker compose stop -t 20 >/dev/null 2>&1" || true
  fi
fi
# Free staging for the next run before the (slow) agent triage starts.
if [ -n "${LOCK_OWNER:-}" ]; then staging_unlock "$LOCK_OWNER"; fi
finish

# ---- 4. agent triage -> Backlog.md --------------------------------------------
# Only real test failures go to the agent; infra/deploy errors are printed for a human.
if [ "$STATUS" = "failed" ] && [ "$AGENT" = "1" ]; then
  echo "==> [4/4] agent triage -> backlog"
  if command -v claude >/dev/null && command -v backlog >/dev/null; then
    echo "    (agent běží, obvykle 1–4 min; průběh: tail -f $REPORT/triage.md — Ctrl+C ho bezpečně přeruší)"
    ( cd "$REPO_DIR" && claude -p "$(sed "s#{{REPORT}}#$REPORT#g" "$E2E_DIR/agent/triage.md")" \
        --allowedTools "Read" "Grep" "Glob" "Bash(backlog:*)" "Bash(git log:*)" "Bash(git diff:*)" "Bash(git show:*)" \
        --max-turns 25 ) > "$REPORT/triage.md" 2>&1 || echo "agent triage failed — see $REPORT/triage.md"
    tail -20 "$REPORT/triage.md"
  else
    echo "claude or backlog CLI not on PATH — skipping triage" | tee "$REPORT/triage.md"
  fi
fi

case "$STATUS" in passed) exit 0 ;; failed) exit 1 ;; *) exit 2 ;; esac
