"""Fail when a service's Alembic migrations have more than one head.

    python scripts/check_alembic_heads.py

Two lanes that each write the next migration on top of the same revision leave two heads (PR D
and PR E both wrote 0011 on 26/10). Only the integration lane may write migrations (see
`scripts/hooks/serial_guard.py`); this check is the second net, in CI. It reads the files
directly, so it needs no database and no service dependencies.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ["core-api", "ai-service"]


def _value(node: ast.expr) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.Tuple | ast.List):
        return [v for element in node.elts for v in _value(element)]
    return []


def _revisions(path: Path) -> tuple[str | None, list[str]]:
    revision: str | None = None
    down: list[str] = []
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        else:
            continue
        if isinstance(target, ast.Name) and target.id == "revision":
            revision = next(iter(_value(value)), None)
        elif isinstance(target, ast.Name) and target.id == "down_revision":
            down = _value(value)
    return revision, down


def heads(versions: Path) -> list[str]:
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in versions.glob("*.py"):
        revision, down = _revisions(path)
        if revision:
            revisions.add(revision)
            parents.update(down)
    return sorted(revisions - parents)


def main() -> int:
    failed = False
    for service in SERVICES:
        found = heads(ROOT / "services" / service / "migrations" / "versions")
        if len(found) != 1:
            failed = True
            print(f"{service}: {len(found)} Alembic heads {found}; expected exactly 1.")
            print("  Only the integration lane writes migrations; rebase on main and renumber.")
        else:
            print(f"{service}: one head ({found[0]})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
