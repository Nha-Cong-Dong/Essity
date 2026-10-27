"""Open and close the fixed lanes L1..L5 of the parallel workflow.

    python scripts/lane.py up L1 t2.23-skip-unit          # new branch from origin/main, or continue
    python scripts/lane.py up L3 t3.1-grade-evals --base origin/main
    python scripts/lane.py env L3 [--shell powershell]   # the lane's test databases and Redis db
    python scripts/lane.py down L3                        # removes the folder; the branch stays
    python scripts/lane.py status [--stale]               # --stale: ages, STALE, ORPHAN
    python scripts/lane.py preflight                      # Docker, containers, free RAM, encoding

A lane is a git worktree at `.claude/worktrees/L<n>` with its own test databases
`core_test_l<n>` and `ai_test_l<n>` and Redis db <n>. Fixed numbers mean nothing to hand out or
give back; agents outside a lane get Redis dbs 6..14 from `agent_env.py`. L1 is the integration
lane: the only one allowed to write migrations or regenerate the api-client
(`scripts/hooks/serial_guard.py`).
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import flow
from agent_env import DATABASE_URL, REDIS_URL, ensure_database
from wt_remove import unlink_links

LANES = range(1, 6)
DOCKER_BIN = Path("E:/Docker/Docker/resources/bin")
DOCKER_APP = Path("E:/Docker/Docker/Docker Desktop.exe")
CONTAINERS = ("essity-postgres-1", "essity-redis-1")
DOCKER_WAIT_SECONDS = 180
RAM_WARN_GB, RAM_STOP_GB = 3.0, 1.5
STALE_MINUTES = 45


def parse_lane(text: str) -> int:
    found = re.fullmatch(r"[Ll]([1-5])", text)
    if not found:
        raise ValueError(f"lane must be L1..L5, not {text!r}")
    return int(found.group(1))


def lane_path(repo: Path, lane: int) -> Path:
    return repo / ".claude" / "worktrees" / f"L{lane}"


def lane_env(lane: int) -> dict[str, str]:
    return {
        "CORE_TEST_DATABASE_URL": DATABASE_URL.format(name=f"core_test_l{lane}"),
        "AI_TEST_DATABASE_URL": DATABASE_URL.format(name=f"ai_test_l{lane}"),
        "CORE_TEST_REDIS_URL": REDIS_URL.format(db=lane),
    }


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=False, capture_output=True, text=True
    )


def up(
    repo: Path, lane: int, branch: str, base: str = "origin/main", create_db: bool = True
) -> Path:
    path = lane_path(repo, lane)
    if path.exists():
        current = _git(path, "branch", "--show-current").stdout.strip()
        raise RuntimeError(
            f"L{lane} is in use (branch {current or '?'}); run `lane.py down L{lane}`"
        )
    exists = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0
    args = (
        ["worktree", "add", str(path), branch]
        if exists
        else ["worktree", "add", "-b", branch, str(path), base]
    )
    result = _git(repo, *args)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    if create_db:
        # the superuser creates them (`core` has no CREATEDB), see agent_env.ensure_database
        ensure_database(f"core_test_l{lane}")
        ensure_database(f"ai_test_l{lane}")
    return path


def down(repo: Path, lane: int, force: bool = False) -> None:
    path = lane_path(repo, lane)
    if not path.exists():
        return
    dirty = _git(path, "status", "--short").stdout.splitlines()
    if dirty and not force:
        # Removing the folder throws away what was never committed; the branch keeps the rest.
        raise RuntimeError(
            f"L{lane} has {len(dirty)} uncommitted file(s): commit and push first, "
            f"or run `lane.py down L{lane} --force` to discard them"
        )
    unlink_links(path)  # pnpm junctions point into the main repo (R45)
    result = _git(repo, "worktree", "remove", "--force", str(path))
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    _git(repo, "worktree", "prune")


def _age(minutes: float | None) -> str:
    if minutes is None:
        return "?"
    return f"{minutes:.0f}m" if minutes < 120 else f"{minutes / 60:.0f}h"


def _commit_age(path: Path, now: float) -> float | None:
    stamp = _git(path, "log", "-1", "--format=%ct").stdout.strip()
    return (now - int(stamp)) / 60 if stamp.isdigit() else None


def _lane_report(repo: Path, branch: str, now: float) -> tuple[str, float | None]:
    """(status, minutes since the file changed) of the lane-report of the task on `branch`."""
    for card in sorted((repo / ".work").glob("*/card.yaml")):
        doc = flow.load(card)
        report = card.parent / "lane-report.yaml"
        if doc and doc.get("branch") == branch and report.exists():
            found = flow.load(report) or {}
            return str(found.get("status") or "?"), (now - report.stat().st_mtime) / 60
    return "-", None


def status(repo: Path, stale: bool = False, now: float | None = None) -> list[str]:
    now = time.time() if now is None else now
    rows = []
    for lane in LANES:
        path = lane_path(repo, lane)
        if not path.exists():
            rows.append(f"L{lane}  free")
            continue
        branch = _git(path, "branch", "--show-current").stdout.strip()
        head = _git(path, "log", "-1", "--format=%h %s").stdout.strip()[:70]
        dirty = len(_git(path, "status", "--short").stdout.splitlines())
        row = f"L{lane}  {branch}  {head}  ({dirty} file(s) not committed)"
        if stale:
            state, report_age = _lane_report(repo, branch, now)
            commit_age = _commit_age(path, now)
            row += f"  commit {_age(commit_age)} ago  report {state} {_age(report_age)}"
            old = all(a is not None and a > STALE_MINUTES for a in (commit_age, report_age))
            if state == "in_progress" and old:
                row += "  STALE"
        rows.append(row)
    if stale:
        rows += orphans(repo, now)
    return rows


def orphans(repo: Path, now: float) -> list[str]:
    """Worktrees under .claude/worktrees/ that are not a fixed lane. Read only."""
    listing = _git(repo, "worktree", "list", "--porcelain").stdout
    root = (repo / ".claude" / "worktrees").resolve()
    rows = []
    for block in listing.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            fields[key] = value
        if "worktree" not in fields:
            continue
        path = Path(fields["worktree"]).resolve()
        if path.parent != root or re.fullmatch(r"L[1-5]", path.name):
            continue
        branch = fields.get("branch", "").removeprefix("refs/heads/") or "?"
        dirty = len(_git(path, "status", "--short").stdout.splitlines())
        has_pr = branch != "?" and flow.open_pr(branch, repo) is not None
        rows.append(
            f"ORPHAN  {path.name}  {branch}  commit {_age(_commit_age(path, now))} ago  "
            f"({dirty} file(s) not committed)  PR {'open' if has_pr else 'none'}"
        )
    return rows


def find_docker() -> str | None:
    if shutil.which("docker"):
        return "docker"
    if DOCKER_BIN.exists():
        os.environ["PATH"] = f"{DOCKER_BIN}{os.pathsep}{os.environ.get('PATH', '')}"
        return shutil.which("docker")
    return None


def _docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], check=False, capture_output=True, text=True)


def docker_running() -> bool:
    return _docker("info").returncode == 0


def start_docker(
    wait: int = DOCKER_WAIT_SECONDS, sleep: Callable[[float], None] = time.sleep
) -> bool:
    if not DOCKER_APP.exists():
        return False
    subprocess.Popen([str(DOCKER_APP)])
    for _ in range(wait // 5):
        if docker_running():
            return True
        sleep(5)
    return docker_running()


def container_healthy(name: str) -> bool:
    out = _docker("inspect", "-f", "{{.State.Health.Status}}", name)
    return out.returncode == 0 and out.stdout.strip() == "healthy"


def free_ram_gb() -> float | None:
    try:
        import psutil  # type: ignore[import-not-found,unused-ignore]

        return float(psutil.virtual_memory().available) / 2**30
    except ImportError:
        pass
    command = "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
    )
    return int(out.stdout.strip()) / 2**20 if out.stdout.strip().isdigit() else None  # KiB -> GiB


def preflight(sleep: Callable[[float], None] = time.sleep) -> tuple[list[str], bool]:
    """(messages, ok). ok is False only when Docker is unusable or RAM is below the hard floor."""
    notes, ok = [], True
    if find_docker() is None:
        return [f"preflight: `docker` not found (PATH, {DOCKER_BIN})"], False
    if not docker_running():
        notes.append("preflight: Docker is not running, starting Docker Desktop...")
        if not start_docker(sleep=sleep):
            return [*notes, f"preflight: Docker did not come up in {DOCKER_WAIT_SECONDS} s"], False
    for name in CONTAINERS:
        if not container_healthy(name):
            notes.append(f"preflight: {name} is not healthy: run `just up`")
    ram = free_ram_gb()
    if ram is not None and ram < RAM_STOP_GB:
        notes.append(f"preflight: only {ram:.1f} GB RAM free (< {RAM_STOP_GB}): stop")
        ok = False
    elif ram is not None and ram < RAM_WARN_GB:
        notes.append(f"preflight: warning, {ram:.1f} GB RAM free (< {RAM_WARN_GB})")
    if os.environ.get("PYTHONIOENCODING", "").lower().replace("-", "") != "utf8":
        notes.append("preflight: warning, PYTHONIOENCODING is not utf-8 (Vietnamese text breaks)")
    return notes or ["preflight: ok"], ok


def main_repo() -> Path:
    common = _git(Path.cwd(), "rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(common.stdout.strip()).parent


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="lane.py")
    sub = parser.add_subparsers(dest="action", required=True)
    p_up = sub.add_parser("up")
    p_up.add_argument("lane")
    p_up.add_argument("branch")
    p_up.add_argument("--base", default="origin/main")
    p_up.add_argument("--no-db", action="store_true")
    p_up.add_argument("--no-preflight", action="store_true")
    p_env = sub.add_parser("env")
    p_env.add_argument("lane")
    p_env.add_argument("--shell", choices=["bash", "powershell"], default="bash")
    p_down = sub.add_parser("down")
    p_down.add_argument("lane")
    p_down.add_argument("--force", action="store_true", help="discard uncommitted files")
    p_status = sub.add_parser("status")
    p_status.add_argument("--stale", action="store_true", help="ages, STALE and ORPHAN worktrees")
    sub.add_parser("preflight")
    args = parser.parse_args(argv)
    repo = main_repo()
    try:
        if args.action == "preflight":
            notes, ok = preflight()
            print("\n".join(notes))
            return 0 if ok else 1
        if args.action == "up":
            if not args.no_preflight and not args.no_db:
                notes, ok = preflight()
                print("\n".join(notes))
                if not ok:
                    return 1
            print(up(repo, parse_lane(args.lane), args.branch, args.base, not args.no_db))
        elif args.action == "env":
            for key, value in lane_env(parse_lane(args.lane)).items():
                print(
                    f"$env:{key} = '{value}'"
                    if args.shell == "powershell"
                    else f"export {key}={value}"
                )
        elif args.action == "down":
            down(repo, parse_lane(args.lane), args.force)
        else:
            print("\n".join(status(repo, args.stale)))
    except (ValueError, RuntimeError) as error:
        print(f"lane: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
