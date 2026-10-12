#!/usr/bin/env bash
# ha2n-task-status — what the headless coder is doing / did. Read-only. Installed as /usr/local/bin/ha2n-task-status.
#   ha2n-task-status            latest run: status + last log lines
#   ha2n-task-status <run-id>   that run
#   ha2n-task-status --list     last 10 runs, one line each
set -uo pipefail
RUNS=/var/lib/ha2n-coder/runs
if [ "${1:-}" = "--list" ]; then
  for d in $(ls -1d "$RUNS"/2* 2>/dev/null | sort | tail -10); do
    printf '%-32s %-8s %s\n' "$(basename "$d")" "$(sed -n 's/^state=//p' "$d/status" 2>/dev/null)" \
      "$(sed -n 's/^message=//p' "$d/status" 2>/dev/null | cut -c1-90)"
  done; exit 0
fi
RUN="${1:-latest}"
[[ "$RUN" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "bad run id" >&2; exit 2; }
D="$RUNS/$RUN"; [ -f "$D/status" ] || { echo "no such run: $RUN" >&2; exit 1; }
cat "$D/status"; echo "--- last log lines"; tail -15 "$D/run.log" 2>/dev/null
