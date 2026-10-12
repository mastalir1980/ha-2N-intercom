#!/usr/bin/env bash
# One-time (and after every change in tools/coder/) install of the headless coder on Jan's VM.
# Run as an admin user with sudo, from a clone of the repo:
#
#   sudo bash tools/coder/install-vm.sh            # Hermes runs as user 'hermes'
#   sudo bash tools/coder/install-vm.sh <user>     # the user allowed to start tasks
#
# Creates/updates: users ha2n-coder (orchestrator, holds the repo token) and ha2n-copilot (sandbox,
# runs Copilot + the code it writes, no repo token), root-owned copies of the scripts, sudoers rules,
# gh CLI (apt), uv + Python 3.12 venv for ha2n-copilot. Idempotent. Tokens: sudo ha2n-coder-set-token.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CALLER="${1:-hermes}"
id "$CALLER" >/dev/null 2>&1 || { echo "user $CALLER does not exist" >&2; exit 1; }
for b in git curl python3 copilot backlog; do
  command -v "$b" >/dev/null || { echo "missing $b — install it first (copilot: npm i -g @github/copilot, backlog: npm i -g backlog.md)" >&2; exit 1; }
done

echo "==> users"
id ha2n-coder   >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/ha2n-coder --shell /bin/bash ha2n-coder
id ha2n-copilot >/dev/null 2>&1 || useradd --system --create-home --home-dir /home/ha2n-copilot --shell /bin/bash ha2n-copilot
for u in ha2n-coder ha2n-copilot; do
  for g in sudo docker adm; do id -nG "$u" | grep -qw "$g" && gpasswd -d "$u" "$g" >/dev/null; done
done
chmod 0750 /var/lib/ha2n-coder /home/ha2n-copilot
install -d -o ha2n-coder -g ha2n-coder -m 0750 /var/lib/ha2n-coder/runs

echo "==> gh CLI"
if ! command -v gh >/dev/null; then
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg
  chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list
  apt-get update -qq && apt-get install -y -qq gh
fi
gh --version | head -1

echo "==> Python 3.12 (uv, root-owned under /opt/ha2n-coder; system python untouched)"
cd /
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh >/dev/null
fi
install -d -o root -g root -m 0755 /opt/ha2n-coder
if [ ! -x /opt/ha2n-coder/py312/bin/python3 ]; then
  UV_PYTHON_INSTALL_DIR=/opt/ha2n-coder/python uv venv -q --python 3.12 /opt/ha2n-coder/py312
fi
chmod -R go-w /opt/ha2n-coder; chmod -R a+rX /opt/ha2n-coder
sudo -u ha2n-copilot /opt/ha2n-coder/py312/bin/python3 --version

echo "==> scripts (root-owned copies)"
install -d -o root -g root -m 0755 /usr/local/lib/ha2n-coder /usr/local/lib/ha2n-coder/prompts /etc/ha2n-coder
install -o root -g root -m 0755 "$SRC/sandbox.sh"     /usr/local/lib/ha2n-coder/sandbox.sh
install -o root -g root -m 0644 "$SRC"/prompts/*.md   /usr/local/lib/ha2n-coder/prompts/
install -o root -g root -m 0755 "$SRC/run-task.sh"    /usr/local/bin/ha2n-run-task
install -o root -g root -m 0755 "$SRC/task-status.sh" /usr/local/bin/ha2n-task-status
install -o root -g root -m 0755 "$SRC/set-token.sh"   /usr/local/sbin/ha2n-coder-set-token

echo "==> sudoers: $CALLER may only start/inspect tasks; ha2n-coder may only call the sandbox"
TMP="$(mktemp)"
cat > "$TMP" <<SUDO
$CALLER ALL=(ha2n-coder) NOPASSWD: /usr/local/bin/ha2n-run-task, /usr/local/bin/ha2n-task-status
ha2n-coder ALL=(ha2n-copilot) NOPASSWD: /usr/local/lib/ha2n-coder/sandbox.sh
SUDO
visudo -cf "$TMP" >/dev/null
install -o root -g root -m 0440 "$TMP" /etc/sudoers.d/ha2n-coder; rm -f "$TMP"

echo "==> self-check"
ok=1
sudo -u ha2n-copilot -H copilot --version >/dev/null 2>&1 || { echo "!! ha2n-copilot cannot run copilot (is it installed under another user's home, e.g. nvm? install it globally: sudo npm i -g @github/copilot)"; ok=0; }
sudo -u ha2n-coder -H backlog --version >/dev/null 2>&1 || { echo "!! ha2n-coder cannot run backlog (install globally: sudo npm i -g backlog.md)"; ok=0; }
for f in /etc/ha2n-coder/repo.token /etc/ha2n-coder/copilot.token; do
  [ -f "$f" ] || { echo "    $f not set yet — run: sudo ha2n-coder-set-token $(basename "$f" .token)"; continue; }
  sudo -u "$CALLER" test -r "$f" && { echo "!! $CALLER can read $f"; ok=0; }
done
[ -f /etc/ha2n-coder/repo.token ] && sudo -u ha2n-copilot test -r /etc/ha2n-coder/repo.token && { echo "!! ha2n-copilot can read the repo token"; ok=0; }
sudo -u ha2n-copilot test -r /var/lib/ha2n-coder && { echo "!! ha2n-copilot can read /var/lib/ha2n-coder"; ok=0; }
CALLER_HOME="$(getent passwd "$CALLER" | cut -d: -f6)"
sudo -u ha2n-copilot test -r "$CALLER_HOME" && { echo "!! ha2n-copilot can read $CALLER_HOME (Hermes' secrets) — run: sudo chmod 700 $CALLER_HOME"; ok=0; }
sudo -u ha2n-copilot test -w /opt/ha2n-coder/py312/bin && { echo "!! ha2n-copilot can modify its Python toolchain"; ok=0; }
sudo -u "$CALLER" sudo -n -u ha2n-coder /usr/local/bin/ha2n-task-status --list >/dev/null && echo "    $CALLER -> ha2n-task-status OK"
[ "$ok" = 1 ] && echo "OK." || { echo "self-check FAILED" >&2; exit 1; }
