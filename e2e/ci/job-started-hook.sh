#!/usr/bin/env bash
# Runner job-started hook: the Pi's own gate, independent of anything on GitHub.
# Installed root-owned as /usr/local/lib/ha2n-ci/job-started.sh and enabled in the runner's .env:
#     ACTIONS_RUNNER_HOOK_JOB_STARTED=/usr/local/lib/ha2n-ci/job-started.sh
# The runner executes it before the first step of EVERY job; a non-zero exit fails the job.
#
# Allowed: only .github/workflows/e2e-pi.yml from main of this repo, triggered by
# pull_request_target (same-repo PR, author + actor allow-listed) or workflow_dispatch
# (actor allow-listed). Everything else — a workflow added in a fork PR, a workflow on another
# branch, any other event — is refused even if someone clicked "Approve and run" on GitHub.
# Allow-list: /etc/ha2n-ci/allowed-actors (root-owned, one GitHub login per line).
set -u
REPO="mastalir1980/ha-2N-intercom"
WANT_WORKFLOW="$REPO/.github/workflows/e2e-pi.yml@refs/heads/main"
ALLOWED=/etc/ha2n-ci/allowed-actors

deny() { echo "ha2n-ci gate: REFUSED — $*" >&2; exit 1; }
allowed() { [ -n "$1" ] && grep -qxF "$1" "$ALLOWED" 2>/dev/null; }

[ "${GITHUB_REPOSITORY:-}" = "$REPO" ] || deny "repository '${GITHUB_REPOSITORY:-?}'"
[ "${GITHUB_WORKFLOW_REF:-}" = "$WANT_WORKFLOW" ] || deny "workflow '${GITHUB_WORKFLOW_REF:-?}' (only e2e-pi.yml from main)"
allowed "${GITHUB_ACTOR:-}" || deny "actor '${GITHUB_ACTOR:-?}' not in $ALLOWED"

case "${GITHUB_EVENT_NAME:-}" in
  workflow_dispatch) ;;
  pull_request_target)
    info="$(python3 - "${GITHUB_EVENT_PATH:-/nonexistent}" <<'PY'
import json, sys
try:
    pr = json.load(open(sys.argv[1]))["pull_request"]
    print(pr["user"]["login"], pr["head"]["repo"]["full_name"], pr["base"]["ref"])
except Exception:
    print("? ? ?")
PY
)"
    read -r author head_repo base_ref <<<"$info"
    [ "$head_repo" = "$REPO" ] || deny "PR from '$head_repo' (forks never run here)"
    [ "$base_ref" = "main" ] || deny "PR into '$base_ref' (only into main)"
    allowed "$author" || deny "PR author '$author' not in $ALLOWED" ;;
  *) deny "event '${GITHUB_EVENT_NAME:-?}'" ;;
esac
echo "ha2n-ci gate: allowed ($GITHUB_EVENT_NAME by $GITHUB_ACTOR)"
