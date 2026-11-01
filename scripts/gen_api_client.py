"""Regenerate packages/api-client from core-api's OpenAPI document, without pnpm or bash.

    python scripts/gen_api_client.py               # dump openapi.json, regenerate src/schema.d.ts
    python scripts/gen_api_client.py --typecheck   # ... then typecheck apps/web

pnpm and WSL bash are unusable on some machines (untrusted shim), so this calls node directly on the
locally installed openapi-typescript, next and tsc binaries. The generate command is read from
packages/api-client/package.json. Typecheck runs under `with_lock.py web`. CI keeps using
scripts/gen_api_client.sh. node_modules is looked up in this checkout, then in the main checkout
(lane worktrees have none). Exit code is non-zero on any failure.
"""

import argparse
import json
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
Runner = Callable[..., int]


class GenError(Exception):
    pass


def _run(cmd: list[str], cwd: Path | None = None) -> int:
    return subprocess.run(cmd, cwd=cwd, check=False).returncode


def _module_roots(package_dir: Path, root: Path) -> list[Path]:
    roots = [package_dir]
    try:
        common = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        main = (root / common).resolve().parent
        if main != root.resolve():
            roots.append(main / package_dir.relative_to(root))
    except (subprocess.CalledProcessError, OSError, ValueError):
        pass
    return roots


def resolve_bin(package_dir: Path, package: str, bin_name: str, root: Path = ROOT) -> Path:
    """Path of a package's bin script inside node_modules (no .bin shims, no pnpm)."""
    tried = []
    for base in _module_roots(package_dir, root):
        pkg = base / "node_modules" / package
        manifest = pkg / "package.json"
        tried.append(str(pkg))
        if not manifest.is_file():
            continue
        bins = json.loads(manifest.read_text(encoding="utf-8")).get("bin", {})
        rel = bins if isinstance(bins, str) else bins.get(bin_name)
        if rel and (pkg / rel).is_file():
            return pkg / rel
    raise GenError(f"{package} is not installed; looked in: {', '.join(tried)}")


def generate_args(root: Path) -> list[str]:
    manifest = json.loads((root / "packages/api-client/package.json").read_text(encoding="utf-8"))
    script = manifest["scripts"]["generate"]
    parts = shlex.split(script)
    if not parts or parts[0] != "openapi-typescript":
        raise GenError(f"unexpected generate script: {script}")
    return parts[1:]


def generate(root: Path, run: Runner = _run) -> int:
    api = root / "packages/api-client"
    dump = [
        "uv",
        "run",
        "--directory",
        str(root / "services/core-api"),
        "--no-sync",
        "python",
        "-m",
        "core_api.openapi_export",
        str(api / "openapi.json"),
    ]
    code = run(dump)
    if code:
        return code
    cli = resolve_bin(api, "openapi-typescript", "openapi-typescript", root)
    return run(["node", str(cli), *generate_args(root)], cwd=api)


def typecheck(root: Path, run: Runner = _run) -> int:
    web = root / "apps/web"
    lock = [sys.executable, str(root / "scripts/with_lock.py"), "web", "--", "node"]
    steps = [
        (resolve_bin(web, "next", "next", root), ["typegen"]),
        (resolve_bin(web, "typescript", "tsc", root), ["--noEmit"]),
    ]
    for script, args in steps:
        code = run([*lock, str(script), *args], cwd=web)
        if code:
            return code
    return 0


def main(argv: list[str], root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(
        prog="gen_api_client.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--typecheck", action="store_true", help="also typecheck apps/web")
    args = parser.parse_args(argv)
    try:
        code = generate(root)
        if code == 0 and args.typecheck:
            code = typecheck(root)
    except GenError as err:
        print(f"gen_api_client: {err}", file=sys.stderr)
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
