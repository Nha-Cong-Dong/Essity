"""Run the whole core-api test suite as several batches, each under the `core` lock.

One `pytest` over services/core-api/tests takes longer than a tool call may last (600 s), so a
lane lead ran folders by hand, skipped one (tests/stats) and CI went red (retro 02/11). This
script splits the suite by top-level folder, packs small folders together to about BUDGET seconds
per batch, and runs every batch in the lane's test environment.

    python scripts/core_batches.py --list
    python scripts/core_batches.py --lane L2 --keep-going
    python scripts/core_batches.py --lane L2 --only stats

A folder is its own pytest invocation; folders only share one when none of their test files
have the same basename (the tests dirs are not packages, so equal basenames clash). Durations:
a batch of a single folder writes its wall time to the cache file, and later plans use it;
without a cache entry a folder is guessed at SEC_PER_FILE seconds per test file.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CORE = REPO / "services" / "core-api"
BUDGET = 480.0
SEC_PER_FILE = 12.0
ROOT = "(root)"


@dataclass
class Unit:
    name: str
    paths: list[str]  # relative to services/core-api
    seconds: float


@dataclass
class Batch:
    units: list[Unit] = field(default_factory=list)

    @property
    def name(self) -> str:
        return "+".join(u.name for u in self.units)

    @property
    def seconds(self) -> float:
        return sum(u.seconds for u in self.units)

    @property
    def paths(self) -> list[str]:
        return [p for u in self.units for p in u.paths]


def _basenames(unit: Unit) -> set[str]:
    names: set[str] = set()
    for path in unit.paths:
        target = CORE / path
        files = target.rglob("test_*.py") if target.is_dir() else [target]
        names.update(f.name for f in files)
    return names


def discover(
    tests_dir: Path, sec_per_file: float, cache: dict[str, float]
) -> list[Unit]:
    units = []
    for folder in sorted(p for p in tests_dir.iterdir() if p.is_dir()):
        count = len(list(folder.rglob("test_*.py")))
        if count:
            guess = cache.get(folder.name, count * sec_per_file)
            units.append(Unit(folder.name, [f"tests/{folder.name}"], guess))
    top = sorted(tests_dir.glob("test_*.py"))
    if top:
        seconds = cache.get(ROOT, len(top) * sec_per_file)
        units.append(Unit(ROOT, [f"tests/{f.name}" for f in top], seconds))
    return units


def pack(units: list[Unit], budget: float) -> list[Batch]:
    """First-fit decreasing; a batch also refuses a unit whose test basenames clash."""
    batches: list[tuple[Batch, set[str]]] = []
    for unit in sorted(units, key=lambda u: (-u.seconds, u.name)):
        names = _basenames(unit)
        for batch, used in batches:
            if batch.seconds + unit.seconds <= budget and not (used & names):
                batch.units.append(unit)
                used |= names
                break
        else:
            batches.append((Batch([unit]), set(names)))
    return [b for b, _ in batches]


def command(batch: Batch) -> list[str]:
    lock = str(Path(__file__).resolve().parent / "with_lock.py")
    return [
        sys.executable,
        lock,
        "core",
        "--",
        "uv",
        "run",
        "pytest",
        "-q",
        *batch.paths,
    ]


def run_batches(
    batches: list[Batch], env: dict[str, str], keep_going: bool, cache: Path
) -> int:
    child_env = {**os.environ, **env}
    durations = _load(cache)
    failed = 0
    started = time.monotonic()
    for index, batch in enumerate(batches, 1):
        begin = time.monotonic()
        code = subprocess.run(
            command(batch), cwd=CORE, env=child_env, check=False
        ).returncode
        took = time.monotonic() - begin
        status = "ok" if code == 0 else "FAILED"
        print(f"[{index}/{len(batches)}] {batch.name}: {status} ({took:.0f}s)")
        if len(batch.units) == 1 and code == 0:
            durations[batch.units[0].name] = round(took, 1)
            _save(cache, durations)
        if code != 0:
            failed += 1
            if not keep_going:
                print("stopped at the first failure (use --keep-going to run the rest)")
                break
    total = time.monotonic() - started
    print(f"total: {len(batches)} batches planned, {failed} failed, {total:.0f}s")
    return 1 if failed else 0


def _load(cache: Path) -> dict[str, float]:
    try:
        return {str(k): float(v) for k, v in json.loads(cache.read_text()).items()}
    except (OSError, ValueError, AttributeError):
        return {}


def _save(cache: Path, durations: dict[str, float]) -> None:
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(durations, indent=1, sort_keys=True))
    except OSError:
        pass


def infer_lane(path: Path) -> int | None:
    match = re.fullmatch(r"L(\d+)", path.name)
    return int(match.group(1)) if match else None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument(
        "--lane", help="L<n>; default: from the worktree directory name"
    )
    parser.add_argument("--only", help="run just this folder (or '(root)')")
    parser.add_argument(
        "--list", action="store_true", help="print the batches and exit"
    )
    parser.add_argument(
        "--batch", type=int, help="run only batch N as --list numbers them"
    )
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--budget", type=float, default=BUDGET)
    parser.add_argument(
        "--cache", type=Path, default=REPO / ".work" / "core-batch-durations.json"
    )
    args = parser.parse_args(argv)

    units = discover(CORE / "tests", SEC_PER_FILE, _load(args.cache))
    if args.only:
        units = [u for u in units if u.name == args.only]
        if not units:
            print(f"no such folder: {args.only}", file=sys.stderr)
            return 2
    batches = pack(units, args.budget)
    if args.list:
        for i, b in enumerate(batches, 1):
            print(f"{i}: ~{b.seconds:.0f}s  {b.name}")
            print(f"   python scripts/core_batches.py --lane L<n> --batch {i}")
        return 0
    if args.batch is not None:
        if not 1 <= args.batch <= len(batches):
            print(f"no batch {args.batch} (have 1..{len(batches)})", file=sys.stderr)
            return 2
        batches = [batches[args.batch - 1]]

    lane = int(args.lane.lstrip("Ll")) if args.lane else infer_lane(REPO)
    if lane is None:
        print("need --lane L<n> (not inside a lane worktree)", file=sys.stderr)
        return 2
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import lane as lane_module

    return run_batches(batches, lane_module.lane_env(lane), args.keep_going, args.cache)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
