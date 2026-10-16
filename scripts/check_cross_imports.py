"""Fail when code in one service or app imports code from another (ADR-0003).

Services share only through `contracts/` and generated clients, never by importing
each other's source. This script checks two things:

- Python: a file under `services/<a>/` imports a package that lives in
  `services/<b>/src/`.
- TypeScript/JavaScript: a file under `apps/<x>/` or `packages/<x>/` uses a relative
  import that resolves outside its own directory. Workspace packages must be imported
  by package name.

Standard library only, so CI can run it without installing anything.
Usage: python scripts/check_cross_imports.py
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    ".venv",
    "node_modules",
    "__pycache__",
    ".next",
    "dist",
    "build",
    "out",
    ".pytest_cache",
    ".ruff_cache",
    ".hypothesis",
}

JS_EXTENSIONS = {".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"}

# `import x from "s"`, `export * from "s"`, `import "s"`, `import("s")`, `require("s")`.
JS_SPECIFIER = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)["']([^"'\n]+)["']"""
)


def iter_files(base: Path, extensions: set[str]) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        found.extend(Path(dirpath) / name for name in filenames if Path(name).suffix in extensions)
    return sorted(found)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def python_packages() -> dict[str, str]:
    """Map each top-level package under services/*/src to the service that owns it."""
    owners: dict[str, str] = {}
    for src in sorted(ROOT.glob("services/*/src")):
        for package in src.iterdir():
            if package.is_dir() and package.name not in SKIP_DIRS:
                owners[package.name] = src.parent.name
    return owners


def check_python() -> list[str]:
    owners = python_packages()
    errors: list[str] = []
    for service_dir in sorted(p for p in ROOT.glob("services/*") if p.is_dir()):
        service = service_dir.name
        for path in iter_files(service_dir, {".py"}):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                errors.append(f"{rel(path)}:{exc.lineno}: cannot parse: {exc.msg}")
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
                else:
                    continue
                for name in names:
                    owner = owners.get(name.split(".")[0])
                    if owner is not None and owner != service:
                        errors.append(
                            f"{rel(path)}:{node.lineno}: {service} imports '{name}' from {owner}"
                        )
    return errors


def check_js() -> list[str]:
    errors: list[str] = []
    workspaces = sorted(ROOT.glob("apps/*")) + sorted(ROOT.glob("packages/*"))
    for workspace in (p for p in workspaces if p.is_dir()):
        for path in iter_files(workspace, JS_EXTENSIONS):
            text = path.read_text(encoding="utf-8")
            for match in JS_SPECIFIER.finditer(text):
                specifier = match.group(1)
                if not specifier.startswith("."):
                    continue
                target = Path(os.path.normpath(path.parent / specifier))
                if not target.is_relative_to(workspace):
                    line = text.count("\n", 0, match.start()) + 1
                    errors.append(
                        f"{rel(path)}:{line}: '{specifier}' resolves outside "
                        f"{rel(workspace)}/ (import workspace packages by name)"
                    )
    return errors


def main() -> int:
    errors = check_python() + check_js()
    for error in errors:
        print(error)
    if errors:
        print(f"\n{len(errors)} cross-boundary import(s) found (ADR-0003).", file=sys.stderr)
        return 1
    print("No cross-boundary imports.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
