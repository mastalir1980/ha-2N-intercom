#!/usr/bin/env bash
# Testovaci pipeline pro 2N Intercom integraci (bezi na Raspberry Pi).
# Pouziti: ./run_tests.sh
set -euo pipefail
cd "$(dirname "$0")"

PY=".venv/bin/python"

if [ ! -x "$PY" ]; then
  echo "✗ Chybi venv (.venv). Vytvor ho: uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python homeassistant pytest"
  exit 1
fi

echo "== 1/2 Unit testy =="
"$PY" -m pytest tests/ -q

echo "== 2/2 Staticka validace integrace =="
"$PY" validate.py | tail -5

echo ""
echo "✅ PIPELINE OK — vsechny testy prosly. Muzes nasadit: ./deploy_test.sh"
