#!/usr/bin/env python3
"""Sanitised markdown summary of one Pi CI E2E report, safe for a PUBLIC PR check.

    ci_summary.py <report-dir> [<env-file>]

The repo is public, so job logs and summaries are readable by anyone. Only status, versions,
counts and failing test names + first line of the message go out. The free-text messages are
masked: the sensitive values from the env file, IPv4/IPv6 and MAC addresses, LAN hostnames,
2N serial numbers and anything that looks like key=secret. Versions and counts come from
known fields and are not masked.
Full logs stay on the Pi in <report-dir>.
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PATTERNS = [
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"),                 # IPv4[:port]
    re.compile(r"\b(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}\b"),          # MAC
    re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){3,7}[0-9a-fA-F]{1,4}\b"),        # IPv6-ish
    re.compile(r"\b\d{2}-\d{4}-\d{4}\b"),                                # 2N serial number
    re.compile(r"\b[\w.-]+\.(?:local|lan|home|internal)\b", re.I),       # LAN hostnames
    re.compile(r"(?i)(password|token|secret|authorization)\S*\s*[:=]\s*\S+"),
]


SECRET_KEYS = ("INTERCOM_HOST", "INTERCOM_USER", "INTERCOM_PASSWORD", "HA_TOKEN", "HA_E2E_PASSWORD")


def env_secrets(env_file: Path | None) -> list[str]:
    """Values of the sensitive keys only (not every setting, e.g. not 'https' or '1')."""
    if not env_file or not env_file.is_file():
        return []
    vals = []
    for line in env_file.read_text().splitlines():
        key, sep, raw = line.partition("=")
        if sep and key.strip() in SECRET_KEYS:
            v = raw.split(" #", 1)[0].strip().strip("'\"")
            if v:
                vals.append(v)
    return sorted(vals, key=len, reverse=True)


def scrub(text: str, secrets: list[str]) -> str:
    """Mask secrets as whole words (a user 'test' must not turn 'tests' into garbage)."""
    for s in secrets:
        text = re.sub(rf"(?<![\w.-]){re.escape(s)}(?![\w-])", "«redacted»", text)
    for p in PATTERNS:
        text = p.sub("«redacted»", text)
    return text


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def main(report: Path, env_file: Path | None) -> str:
    secrets = env_secrets(env_file)
    summary, ctx = load(report / "summary.json"), load(report / "context.json")
    status = summary.get("status", "error")
    head = {"passed": "✅ E2E on the Pi passed", "failed": "❌ E2E on the Pi failed",
            "error": "⚠️ E2E pipeline error"}.get(status, status)
    dev = ctx.get("intercom") or {}
    out = [f"### {head}", "",
           f"- commit: `{summary.get('deployed_sha', '?')}`",
           f"- Home Assistant: {ctx.get('ha_version', '?')}",
           f"- intercom: {dev.get('variant', '?')} fw {dev.get('swVersion', '?')}"]
    if status != "passed" and summary.get("failed_stage"):
        out.append(f"- failed stage: **{summary['failed_stage']}**")
    junit = report / "junit.xml"
    if junit.exists():
        try:
            root = ET.parse(junit).getroot()
        except ET.ParseError:
            root = None
        suite = None if root is None else (root if root.tag == "testsuite" else root.find("testsuite"))
        if suite is not None:
            total = int(suite.get("tests", 0))
            fail = int(suite.get("failures", 0)) + int(suite.get("errors", 0))
            skip = int(suite.get("skipped", 0))
            out.append(f"- tests: {total - fail - skip} passed, {fail} failed, {skip} skipped")
            bad_lines = []
            for case in suite.iter("testcase"):
                bad = case.find("failure")
                if bad is None:
                    bad = case.find("error")
                if bad is not None:
                    msg = (bad.get("message") or "").splitlines()[0][:200] if bad.get("message") else ""
                    name = f"{case.get('classname', '')}::{case.get('name', '')}".strip(":")
                    bad_lines.append(f"- `{name}` — {scrub(msg, secrets)}")
            if bad_lines:
                out += ["", "**Failing tests**", *bad_lines]
    out += ["", f"Full report stays on the Pi: `reports/{report.name}`"]
    return "\n".join(out)


if __name__ == "__main__":
    env = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    print(main(Path(sys.argv[1]).resolve(), env))
