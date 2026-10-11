"""Load e2e/.env (simple KEY=VALUE, `#` comments) with process env taking precedence."""

from __future__ import annotations

import os
import re
from pathlib import Path

E2E_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = Path(os.environ.get("E2E_ENV_FILE", E2E_DIR / ".env"))

_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def _parse(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = _LINE.match(raw)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if value[:1] in ("'", '"') and value[-1:] == value[:1]:
            value = value[1:-1]
        else:
            value = re.sub(r"\s+#.*$", "", value)  # inline comment
        out[key] = value
    return out


def load() -> dict[str, str]:
    values = _parse(ENV_FILE.read_text()) if ENV_FILE.exists() else {}
    for key in list(values):
        if key in os.environ:
            values[key] = os.environ[key]
    for key, val in os.environ.items():
        if key.startswith(("HA_", "PI_", "INTERCOM_", "E2E_")):
            values.setdefault(key, val)
    return values


def update_env_file(updates: dict[str, str]) -> None:
    """Set keys in e2e/.env in place (adds missing keys), keep the file private."""
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    seen: set[str] = set()
    for i, raw in enumerate(lines):
        m = _LINE.match(raw)
        if m and m.group(1) in updates:
            lines[i] = f"{m.group(1)}={updates[m.group(1)]}"
            seen.add(m.group(1))
    lines += [f"{k}={v}" for k, v in updates.items() if k not in seen]
    ENV_FILE.write_text("\n".join(lines) + "\n")
    ENV_FILE.chmod(0o600)


def flag(values: dict[str, str], key: str, default: bool = False) -> bool:
    raw = values.get(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


PROD_PORT = 8123


def assert_staging_url(url: str) -> None:
    """Refuse to talk to the production HA (port 8123) — the pipeline is staging-only."""
    from urllib.parse import urlparse
    port = urlparse(url).port
    if port == PROD_PORT or port is None:
        raise SystemExit(
            f"HA_URL={url} vypadá jako produkční HA (port {port or 'výchozí'}). "
            "E2E pipeline smí jen na staging (port 8124). Oprav HA_URL v e2e/.env."
        )
