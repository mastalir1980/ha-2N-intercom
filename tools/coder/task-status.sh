#!/usr/bin/env bash
# ha2n-task-status — what the headless coder is doing / did. Read-only. Installed as /usr/local/bin/ha2n-task-status.
#   ha2n-task-status            latest run: status + last log lines
#   ha2n-task-status <run-id>   that run
#   ha2n-task-status --list     last 10 runs, one line each
set -uo pipefail
RUNS=/var/lib/ha2n-coder/runs
COST=/var/lib/ha2n-coder/cost.csv   # written by run-task.sh, columns: time,run,task,label,model,effort,ai_credits,tokens_in,tokens_out,duration
credits() {  # total AI credits of one run, "-" when nothing is logged
  [ -r "$COST" ] || { printf -- "-"; return; }
  awk -F, -v r="$1" 'NR>1 && $2==r {s+=$7; n++} END {if (n) printf "%.2f", s; else printf "-"}' "$COST"
}
if [ "${1:-}" = "--list" ]; then
  for d in $(ls -1d "$RUNS"/2* 2>/dev/null | sort | tail -10); do
    mark=""; [ -e "$d/next.marker" ] && mark="auto"   # started by the timer (--next)
    printf '%-32s %-8s %-5s %9s cr  %s\n' "$(basename "$d")" "$(sed -n 's/^state=//p' "$d/status" 2>/dev/null)" \
      "$mark" "$(credits "$(basename "$d")")" "$(sed -n 's/^message=//p' "$d/status" 2>/dev/null | cut -c1-80)"
  done; exit 0
fi
RUN="${1:-latest}"
[[ "$RUN" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "bad run id" >&2; exit 2; }
D="$RUNS/$RUN"; [ -f "$D/status" ] || { echo "no such run: $RUN" >&2; exit 1; }
RUN_ID="$(basename "$(readlink -f "$D")")"   # "latest" is a symlink; cost.csv has the real run id
cat "$D/status"
if [ -r "$COST" ] && awk -F, -v r="$RUN_ID" 'NR>1 && $2==r {f=1} END {exit !f}' "$COST"; then
  echo "--- cost per Copilot call (label, model, effort, AI credits, tokens in/out, duration)"
  awk -F, -v r="$RUN_ID" 'NR>1 && $2==r {printf "%-12s %-18s %-7s %8s cr  %s / %s  %s\n", $4, $5, $6, $7, $8, $9, $10}' "$COST"
  echo "total: $(credits "$RUN_ID") AI credits"
fi
echo "--- last log lines"; tail -15 "$D/run.log" 2>/dev/null
