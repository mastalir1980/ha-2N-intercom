"""Shared fixtures for the 2N integration E2E suite (staging HA <-> real 2N device)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from e2elib import env  # noqa: E402
from e2elib.ha import HA  # noqa: E402
from e2elib.twon import TwoN  # noqa: E402

CFG = env.load()
REPORT_DIR = Path(os.environ.get("E2E_REPORT_DIR", env.E2E_DIR / "reports" / "adhoc"))


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--relays", action="store_true", default=False,
        help="physically switch the relays listed in E2E_RELAY_NUMBERS (manual runs only)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "relay: test physically switches a relay on the intercom")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--relays"):
        return
    skip = pytest.mark.skip(reason="relay test — run manually with --relays")
    for item in items:
        if "relay" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def ha() -> HA:
    env.assert_staging_url(CFG["HA_URL"])
    client = HA(CFG["HA_URL"], CFG.get("HA_TOKEN"))
    client.wait_up(timeout=120)
    return client


@pytest.fixture(scope="session")
def twon() -> TwoN:
    return TwoN(
        CFG["INTERCOM_HOST"], CFG["INTERCOM_USER"], CFG["INTERCOM_PASSWORD"],
        protocol=CFG.get("INTERCOM_PROTOCOL", "https"),
        verify=env.flag(CFG, "INTERCOM_VERIFY_SSL"),
    )


@pytest.fixture(scope="session")
def entry(ha: HA) -> dict:
    entries = ha.entries()
    assert len(entries) == 1, f"expected exactly one 2N config entry on staging, got {len(entries)}"
    return entries[0]


@pytest.fixture(scope="session")
def registry(ha: HA, entry: dict) -> list[dict]:
    return [e for e in ha.entity_registry() if e.get("config_entry_id") == entry["entry_id"]]


def find_by_suffix(registry: list[dict], entry_id: str, suffix: str) -> dict | None:
    uid = f"{entry_id}_{suffix}"
    return next((e for e in registry if e.get("unique_id") == uid), None)


@pytest.fixture(scope="session", autouse=True)
def run_context(ha: HA, twon: TwoN) -> None:
    """Write context.json for the report/agent: versions of everything under test."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ctx: dict = {"ha_url": ha.url}
    try:
        ctx["ha_version"] = ha.config().get("version")
    except Exception as err:  # noqa: BLE001
        ctx["ha_version_error"] = str(err)
    try:
        info = twon.system_info()
        ctx["intercom"] = {k: info.get(k) for k in ("variant", "deviceName", "swVersion", "buildType", "hwVersion")}
    except Exception as err:  # noqa: BLE001
        ctx["intercom_error"] = str(err)
    sha_file = env.E2E_DIR / "state" / "last_deployed_sha"
    ctx["deployed_sha"] = sha_file.read_text().strip() if sha_file.exists() else None
    pruned_file = REPORT_DIR / "pruned_entities.json"  # written by scripts/prune_orphans.py via run.sh
    if pruned_file.exists():
        try:
            pruned = json.loads(pruned_file.read_text())
            ctx["pruned_entities"] = pruned.get("pruned", [])
            if pruned.get("error"):
                ctx["pruned_entities_error"] = pruned["error"]
        except ValueError as err:
            ctx["pruned_entities_error"] = f"unreadable {pruned_file.name}: {err}"
    (REPORT_DIR / "context.json").write_text(json.dumps(ctx, indent=2))


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Dump HA's system log so the triage agent sees the integration's errors."""
    try:
        client = HA(CFG["HA_URL"], CFG.get("HA_TOKEN"))
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        (REPORT_DIR / "ha_system_log.json").write_text(json.dumps(client.system_log(), indent=2))
    except Exception as err:  # noqa: BLE001
        print(f"[e2e] could not dump system log: {err}")
