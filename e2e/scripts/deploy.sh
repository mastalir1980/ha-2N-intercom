#!/usr/bin/env bash
# Deploy custom_components/2n_intercom to the STAGING Home Assistant on the Pi
# and restart it. Never touches the production HA.
#
#   deploy.sh [--ref <git-ref> | --worktree] [--pull] [--no-restart]
#
#   --ref <ref>   deploy a committed git ref (default: HEAD) via `git archive`
#   --worktree    deploy the current working tree incl. uncommitted changes
#   --pull        pull the newest HA image for staging before restart
#   --no-restart  copy files only
set -euo pipefail

E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="$(cd "$E2E_DIR/.." && pwd)"
# shellcheck disable=SC1091
set -a; [ -f "$E2E_DIR/.env" ] && . "$E2E_DIR/.env"; set +a
. "$E2E_DIR/scripts/pi.sh"

: "${PI_SSH:?PI_SSH missing in e2e/.env}"
: "${PI_STAGING_DIR:?PI_STAGING_DIR missing in e2e/.env}"
: "${HA_URL:?HA_URL missing in e2e/.env}"
HA_CONTAINER="${HA_CONTAINER:-ha-staging}"
case "$HA_URL" in
  *:8124|*:8124/*) ;;
  *) echo "HA_URL=$HA_URL není staging (port 8124) — nasazuju jen na staging, ne do produkční HA." >&2; exit 2 ;;
esac
[ "$HA_CONTAINER" = "homeassistant" ] && { echo "HA_CONTAINER=homeassistant je produkce — odmítám." >&2; exit 2; }

REF="HEAD"; WORKTREE=0; PULL=0; RESTART=1
while [ $# -gt 0 ]; do
  case "$1" in
    --ref) REF="$2"; shift 2 ;;
    --worktree) WORKTREE=1; shift ;;
    --pull) PULL=1; shift ;;
    --no-restart) RESTART=0; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

cd "$REPO_DIR"
if [ "$WORKTREE" = 1 ]; then
  SHA="$(git rev-parse --short HEAD)-dirty"
  echo "==> deploying working tree ($SHA)"
  # COPYFILE_DISABLE: stop macOS bsdtar from adding ._* AppleDouble files
  STREAM() { COPYFILE_DISABLE=1 tar --exclude='__pycache__' --exclude='*.pyc' --exclude='._*' --exclude='.DS_Store' -cf - custom_components/2n_intercom; }
else
  SHA="$(git rev-parse --short "$REF")"
  echo "==> deploying git ref $REF ($SHA)"
  STREAM() { git archive --format=tar "$REF" custom_components/2n_intercom; }
fi

DEST="$PI_STAGING_DIR/config"
IMAGE="${HA_IMAGE:-ghcr.io/home-assistant/home-assistant:stable}"
# keep the staging compose file on the Pi in sync with the repo
pi "cat > '$PI_STAGING_DIR/docker-compose.yml'" < "$E2E_DIR/staging/docker-compose.yml"
# HA runs as root in the container and leaves root-owned __pycache__ behind,
# so the old version is removed from inside a throwaway container, not by our user.
STREAM | pi "set -e
  mkdir -p '$DEST/custom_components'
  if [ -e '$DEST/custom_components/2n_intercom' ]; then
    rm -rf '$DEST/custom_components/2n_intercom' 2>/dev/null ||
      docker run --rm --entrypoint /bin/rm -v '$DEST/custom_components:/cc' '$IMAGE' -rf /cc/2n_intercom
  fi
  tar -x -C '$DEST'
  printf '{\"sha\": \"%s\", \"deployed_at\": \"%s\"}\n' '$SHA' \"\$(date -Is)\" > '$DEST/custom_components/2n_intercom/.e2e_deployed.json'"
mkdir -p "$E2E_DIR/state"
echo "$SHA" > "$E2E_DIR/state/last_deployed_sha"

if [ "$RESTART" = 1 ]; then
  if [ "$PULL" = 1 ]; then
    echo "==> pulling newest HA image for staging"
    pi "cd '$PI_STAGING_DIR' && docker compose pull -q"
  fi
  echo "==> (re)starting $HA_CONTAINER"
  pi "cd '$PI_STAGING_DIR' && docker compose up -d --force-recreate '$HA_CONTAINER' >/dev/null"
  echo -n "==> waiting for HA at $HA_URL "
  for _ in $(seq 1 100); do
    if curl -fsS -o /dev/null --max-time 5 "$HA_URL/manifest.json"; then echo " up"; exit 0; fi
    echo -n "."; sleep 3
  done
  echo " TIMEOUT" >&2
  exit 1
fi
