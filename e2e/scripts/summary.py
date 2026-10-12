#!/usr/bin/env python3
"""Short, phone-friendly summary of one E2E report (for Telegram via Hermes)."""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def main(report: Path) -> str:
    summary, ctx = load(report / "summary.json"), load(report / "context.json")
    status = summary.get("status", "error")
    head = {"passed": "✅ E2E OK", "failed": "❌ E2E FAILED", "error": "⚠️ E2E pipeline error"}.get(status, status)
    dev = ctx.get("intercom") or {}
    lines = [
        f"{head} — ha-2n-intercom",
        f"Spouštěč: {summary.get('trigger', '?')}",
        f"Verze: integrace {summary.get('deployed_sha', '?')}, HA {ctx.get('ha_version', '?')}, "
        f"{dev.get('variant', 'interkom')} fw {dev.get('swVersion', '?')}",
    ]
    junit = report / "junit.xml"
    if junit.exists():
        root = ET.parse(junit).getroot()
        suite = root if root.tag == "testsuite" else root.find("testsuite")
        if suite is not None:
            total, fail = int(suite.get("tests", 0)), int(suite.get("failures", 0)) + int(suite.get("errors", 0))
            skip = int(suite.get("skipped", 0))
            lines.append(f"Testy: {total - fail - skip} ok, {fail} chyb, {skip} přeskočeno")
            for case in suite.iter("testcase"):
                bad = case.find("failure") if case.find("failure") is not None else case.find("error")
                if bad is not None:
                    msg = (bad.get("message") or "").splitlines()[0][:140]
                    lines.append(f"• {case.get('name')}: {msg}")
    elif status != "passed":
        lines.append(f"Selhala fáze: {summary.get('failed_stage', '?')} (viz {report.name})")
    if status != "passed":
        lines.append("Další krok: na Macu `bash e2e/e2e.sh run --ref origin/main` — agent založí bugy v Backlogu.")
    lines.append(f"Report na Pi: {report}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(main(Path(sys.argv[1]).resolve()))
