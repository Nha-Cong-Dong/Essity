"""Remove a git worktree without following pnpm's junctions into the main repo (R45).

    python scripts/wt_remove.py .claude/worktrees/agent-1234
    python scripts/wt_remove.py E:/DevCache/wt-mut --allow-root E:/DevCache

`git worktree remove --force` and `rm -rf` follow the junctions pnpm leaves in node_modules
(`node_modules` -> the main repo's, workspace links -> `packages/*`) and delete the main repo's
files: on 24/10 that took `packages/api-client`. This script unlinks every junction and symlink
first, then lets git remove the rest, and refuses any path that is not a worktree folder.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _is_link(entry: os.DirEntry[str]) -> bool:
    return entry.is_symlink() or entry.is_junction()


def unlink_links(root: Path) -> list[Path]:
    """Remove every junction and symlink under `root` without entering them; return what went."""
    removed: list[Path] = []
    stack = [root]
    while stack:
        with os.scandir(stack.pop()) as entries:
            for entry in entries:
                path = Path(entry.path)
                if _is_link(entry):
                    if entry.is_junction() or (sys.platform == "win32" and entry.is_dir()):
                        os.rmdir(path)  # removes the link, not the folder it points at
                    else:
                        os.unlink(path)
                    removed.append(path)
                elif entry.is_dir(follow_symlinks=False):
                    stack.append(path)
    return removed


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def check_removable(path: Path, repo: Path, allowed_roots: list[Path]) -> None:
    """Raise ValueError unless `path` is strictly inside .claude/worktrees or an allowed root."""
    path, repo = path.resolve(), repo.resolve()
    worktrees = repo / ".claude" / "worktrees"
    roots = [worktrees, *(root.resolve() for root in allowed_roots)]
    if any(path != root and _inside(path, root) for root in roots):
        return
    if _inside(path, repo):
        raise ValueError(f"{path} is inside the main repo, not a worktree folder")
    raise ValueError(f"{path} is not under {worktrees} or an --allow-root")


def main_repo() -> Path:
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return Path(common).parent


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wt_remove.py")
    parser.add_argument("worktree", type=Path)
    parser.add_argument("--allow-root", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    repo = main_repo()
    try:
        check_removable(args.worktree, repo, args.allow_root)
    except ValueError as error:
        print(f"wt_remove: refused: {error}", file=sys.stderr)
        return 2
    removed = unlink_links(args.worktree)
    print(f"wt_remove: unlinked {len(removed)} junctions/symlinks")
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "remove", "--force", str(args.worktree)], check=True
    )
    subprocess.run(["git", "-C", str(repo), "worktree", "prune"], check=True)
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--short"], check=False, capture_output=True, text=True
    )
    print("wt_remove: main repo status:\n" + (status.stdout or "(clean)"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
