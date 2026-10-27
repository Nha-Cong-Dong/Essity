"""Open and close the fixed lanes L1..L5 of the parallel workflow.

    python scripts/lane.py up L1 t2.23-skip-unit          # new branch from origin/main, or continue it
    python scripts/lane.py up L3 t3.1-grade-evals --base origin/main
    python scripts/lane.py env L3 [--shell powershell]   # the lane's test database and Redis db
    python scripts/lane.py down L3                        # removes the folder; the branch stays
    python scripts/lane.py status

A lane is a git worktree at `.claude/worktrees/L<n>` with its own test database
`core_test_l<n>` and Redis db <n>. Fixed numbers mean nothing to hand out or give back; agents
outside a lane get Redis dbs 6..14 from `agent_env.py`. L1 is the integration lane: the only
one allowed to write migrations or regenerate the api-client (`scripts/hooks/serial_guard.py`).
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

from agent_env import DATABASE_URL, REDIS_URL, ensure_database
from wt_remove import unlink_links

LANES = range(1, 6)


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
        ensure_database(f"core_test_l{lane}")
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


def status(repo: Path) -> list[str]:
    rows = []
    for lane in LANES:
        path = lane_path(repo, lane)
        if path.exists():
            branch = _git(path, "branch", "--show-current").stdout.strip()
            head = _git(path, "log", "-1", "--format=%h %s").stdout.strip()[:70]
            dirty = len(_git(path, "status", "--short").stdout.splitlines())
            rows.append(f"L{lane}  {branch}  {head}  ({dirty} file(s) not committed)")
        else:
            rows.append(f"L{lane}  free")
    return rows


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
    p_env = sub.add_parser("env")
    p_env.add_argument("lane")
    p_env.add_argument("--shell", choices=["bash", "powershell"], default="bash")
    p_down = sub.add_parser("down")
    p_down.add_argument("lane")
    p_down.add_argument("--force", action="store_true", help="discard uncommitted files")
    sub.add_parser("status")
    args = parser.parse_args(argv)
    repo = main_repo()
    try:
        if args.action == "up":
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
            print("\n".join(status(repo)))
    except (ValueError, RuntimeError) as error:
        print(f"lane: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
