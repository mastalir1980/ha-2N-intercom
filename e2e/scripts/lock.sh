# Staging lock shared by every E2E run (Mac over ssh, nightly/Hermes on the Pi, the Pi CI runner).
# Only one run may deploy to + test the staging HA at a time. Requires pi() from pi.sh.
#
# Protocol (also implemented in e2e/ci/ha2n-staging — keep both in sync):
#   lock     = directory $PI_STAGING_DIR/.e2e.lock created atomically with mkdir
#   owner    = file .e2e.lock/owner containing "<owner-tag> <epoch-seconds>"
#   stale    = a lock older than E2E_LOCK_STALE seconds (default 5400) is broken
#   waiting  = up to E2E_LOCK_WAIT seconds (default 1800), polling every 10 s
#
#   staging_lock <owner-tag>     -> 0 when acquired, 1 on timeout
#   staging_unlock <owner-tag>   -> removes the lock only if <owner-tag> holds it

staging_lock() {
  local owner="$1" wait="${E2E_LOCK_WAIT:-1800}" stale="${E2E_LOCK_STALE:-5400}" waited=0 out
  local dir="$PI_STAGING_DIR/.e2e.lock"
  while :; do
    out="$(pi "d='$dir'; now=\$(date +%s)
      if mkdir \"\$d\" 2>/dev/null; then echo '$owner' \$now > \"\$d/owner\"; echo acquired; exit 0; fi
      read -r o t 2>/dev/null < \"\$d/owner\" || { o=unknown; t=\$(stat -c %Y \"\$d\" 2>/dev/null || stat -f %m \"\$d\" 2>/dev/null || echo \$now); }
      if [ \$((now - \${t:-\$now})) -gt $stale ]; then
        if mv \"\$d\" \"\$d.stale.\$\$\" 2>/dev/null; then rm -rf \"\$d.stale.\$\$\"; fi; echo stale \"\$o\"
      else echo held \"\$o\"; fi")" || out="error"
    case "$out" in
      acquired) return 0 ;;
      stale*) echo "==> broke stale staging lock (${out#stale })"; continue ;;
    esac
    if [ "$waited" -ge "$wait" ]; then
      echo "staging lock still held after ${wait}s (${out#held }) — giving up" >&2; return 1
    fi
    [ "$waited" -eq 0 ] && echo "==> staging busy (${out#held }), waiting for the lock…"
    sleep 10; waited=$((waited + 10))
  done
}

staging_unlock() {
  local dir="$PI_STAGING_DIR/.e2e.lock"
  pi "d='$dir'; read -r o _ 2>/dev/null < \"\$d/owner\" && [ \"\$o\" = '$1' ] && rm -rf \"\$d\"" >/dev/null 2>&1 || true
}
