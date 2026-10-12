#!/usr/bin/env bash
# ha2n-coder-set-token repo|copilot — store a token without it showing on screen or in shell history.
# Installed as /usr/local/sbin/ha2n-coder-set-token. Run: sudo ha2n-coder-set-token repo
#   repo    -> /etc/ha2n-coder/repo.token     (root:ha2n-coder 0640)    fine-grained PAT for this repo
#   copilot -> /etc/ha2n-coder/copilot.token  (root:ha2n-copilot 0640)  fine-grained PAT, Copilot Requests only
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
case "${1:-}" in
  repo) f=/etc/ha2n-coder/repo.token; g=ha2n-coder ;;
  copilot) f=/etc/ha2n-coder/copilot.token; g=ha2n-copilot ;;
  *) echo "usage: sudo ha2n-coder-set-token repo|copilot" >&2; exit 2 ;;
esac
read -r -s -p "Paste the $1 token (input hidden), then Enter: " t; echo
[[ "$t" =~ ^github_pat_[A-Za-z0-9_]{20,}$ ]] || { echo "that does not look like a fine-grained token (github_pat_…)" >&2; exit 1; }
install -d -o root -g root -m 0755 /etc/ha2n-coder
( umask 077; printf '%s\n' "$t" > "$f.tmp" ); chown root:"$g" "$f.tmp"; chmod 0640 "$f.tmp"; mv "$f.tmp" "$f"
echo "stored $f (readable by $g only)"
