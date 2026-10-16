"""Fail when a dependency is GPL or AGPL licensed (ADR-0011).

LGPL is allowed: it does not extend to code that only links to the library (psycopg, libvips
in sharp). A package with no license information fails too, so nothing slips through unread.

Usage:
  # Python: run with the service's own interpreter, from the service directory.
  uv run --no-sync python ../../scripts/check_licenses.py python
  # JavaScript: feed it pnpm's report, from the app directory.
  pnpm licenses list --json | python ../../scripts/check_licenses.py pnpm -

Standard library only.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from dataclasses import dataclass
from importlib.metadata import distributions
from pathlib import Path

# Packages reviewed by hand, with the reason. Keep this empty unless a real case comes up.
ALLOWED: dict[str, str] = {}

LESSER = re.compile(
    r"\bLGPL[\w.+-]*"
    r"|GNU (?:Library or )?Lesser General Public License(?: v\d(?: or later)?)?(?: \([^)]*\))?"
    r"|GNU Library General Public License",
    re.IGNORECASE,
)
COPYLEFT = re.compile(r"\bA?GPL|General Public License|Affero", re.IGNORECASE)
UNKNOWN = {"", "unknown", "unlicensed", "see license", "see license file", "other"}


@dataclass(frozen=True)
class Package:
    name: str
    version: str
    license: str  # what the package declares, for the report
    spdx: bool  # True when `license` is an SPDX expression, so "OR" can be trusted


def is_copyleft(text: str) -> bool:
    return COPYLEFT.search(LESSER.sub("", text)) is not None


def verdict(package: Package) -> str | None:
    """Why the package is rejected, or None when it is fine."""
    text = package.license.strip()
    if text.lower() in UNKNOWN or text.lower().startswith("see license"):
        return "no license information"
    if package.spdx:
        # "MIT OR GPL-3.0" lets us pick MIT; "Apache-2.0 AND GPL-3.0" does not.
        options = [o.strip(" ()") for o in re.split(r"\s+OR\s+", text)]
        if all(is_copyleft(option) for option in options):
            return "copyleft (GPL/AGPL)"
        return None
    # Free text: be conservative, "GPL or commercial" is still GPL for us.
    return "copyleft (GPL/AGPL)" if is_copyleft(text) else None


def python_packages() -> list[Package]:
    project = tomllib.loads(Path("pyproject.toml").read_text("utf-8"))["project"]["name"]
    packages: list[Package] = []
    for dist in distributions():
        meta = dist.metadata
        name = meta["Name"]
        if _normalize(name) == _normalize(project):
            continue
        expression = meta.get("License-Expression")
        if expression:
            packages.append(Package(name, dist.version, expression, spdx=True))
            continue
        # Many packages put the whole license text in License; its first line names it.
        parts = [(meta.get("License") or "").strip().split("\n")[0]]
        parts += [
            c.split(" :: ", 1)[1]
            for c in meta.get_all("Classifier") or []
            if c.startswith("License :: ") and c != "License :: OSI Approved"
        ]
        text = "; ".join(p for p in parts if p)
        packages.append(Package(name, dist.version, text, spdx=False))
    return packages


def pnpm_packages(report: str) -> list[Package]:
    packages: list[Package] = []
    for license_name, entries in json.loads(report).items():
        for entry in entries:
            for version in entry["versions"]:
                packages.append(Package(entry["name"], version, license_name, spdx=True))
    return packages


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def main(argv: list[str]) -> int:
    if argv[:1] == ["python"]:
        packages = python_packages()
    elif argv[:1] == ["pnpm"] and len(argv) == 2:
        report = sys.stdin.read() if argv[1] == "-" else Path(argv[1]).read_text("utf-8")
        packages = pnpm_packages(report)
    else:
        print(__doc__, file=sys.stderr)
        return 2

    rejected = [
        (package, reason)
        for package in sorted(packages, key=lambda p: p.name.lower())
        if (reason := verdict(package)) and _normalize(package.name) not in ALLOWED
    ]
    for package, reason in rejected:
        print(f"{package.name} {package.version}: {reason} [{package.license}]")
    if rejected:
        print(
            f"\n{len(rejected)} package(s) rejected (ADR-0011). Remove them, or review by hand "
            "and add to ALLOWED in scripts/check_licenses.py with a reason.",
            file=sys.stderr,
        )
        return 1
    print(f"{len(packages)} packages checked, no GPL/AGPL or unknown licenses.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
