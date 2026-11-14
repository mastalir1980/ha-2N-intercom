"""Check that the unit-test requirements are installed in the running Python.

The pipeline runs the unit suite with the E2E venv. A venv that lacks a
unit-test dependency fails with an ImportError deep in the unit log; this
check names the requirements file and the install command instead.

Usage: python e2e/e2elib/unitdeps.py <requirements.txt>
"""

from __future__ import annotations

import re
import sys
from importlib import metadata
from pathlib import Path


def requirement_names(text: str) -> list[str]:
    """Return the distribution names listed in requirements-file text."""
    names: list[str] = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = re.split(r"[\s<>=!~;\[@]", line, maxsplit=1)[0]
        if name:
            names.append(name)
    return names


def missing(requirements: Path) -> list[str]:
    """Return the listed distributions that are not installed."""
    absent: list[str] = []
    for name in requirement_names(requirements.read_text(encoding="utf-8")):
        try:
            metadata.version(name)
        except metadata.PackageNotFoundError:
            absent.append(name)
    return absent


def main(argv: list[str]) -> int:
    requirements = Path(argv[1])
    absent = missing(requirements)
    if not absent:
        return 0
    print(
        f"Unit-test requirements are missing in this Python: {', '.join(absent)}\n"
        f"They are listed in {requirements}. Install them with:\n"
        f"  {sys.executable} -m pip install -r {requirements}\n"
        "or run: bash e2e/e2e.sh setup"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
