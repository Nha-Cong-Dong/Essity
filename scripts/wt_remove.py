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
import shutil
import stat
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


def is_reparse(path: Path | str) -> bool:
    """Symlink, junction or any other Windows reparse point (never follows it)."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return (
        stat.S_ISLNK(info.st_mode)
        or os.path.isjunction(path)
        or bool(getattr(info, "st_file_attributes", 0) & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    )


def sweep_leftover(
    path: Path, repo: Path | None = None, allowed_roots: list[Path] | None = None
) -> str | None:
    """Delete what `git worktree remove` left behind (read-only files, junctions, long paths).

    Returns None when the folder is gone, else the reason it stays (nothing is deleted then).
    Refuses: a folder with a `.git` entry (a live checkout), a path that is itself a link, a link
    anywhere between the root and the path, and a path not strictly inside
    `<repo>/.claude/worktrees` or an allowed root (paths are made absolute, never resolved).
    """
    path = Path(os.path.abspath(path))
    if not os.path.lexists(path):
        return None
    if repo is not None:
        roots = [Path(os.path.abspath(repo)) / ".claude" / "worktrees"]
        roots += [Path(os.path.abspath(r)) for r in allowed_roots or []]
        root = next((r for r in roots if path != r and r in path.parents), None)
        if root is None:
            return "refused: not strictly inside the worktrees root"
        between = [path, *(p for p in path.parents if p != root and root in p.parents)]
        if any(is_reparse(p) for p in between):
            return "refused: path is or sits under a link"
    elif is_reparse(path):
        return "refused: path is a link"
    if (path / ".git").exists():
        return "has a .git entry"
    errors: list[str] = []

    def retry(func, target, exc) -> None:  # type: ignore[no-untyped-def]
        try:
            if not is_reparse(target):
                os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError as error:
            errors.append(str(error))

    try:
        unlink_links(path)
        # the extended-length prefix lifts the 260-character limit of pnpm's nested node_modules
        prefix = (r"\\?" + "\\") if sys.platform == "win32" else ""
        target = prefix + str(path)
        if sys.version_info >= (3, 12):
            shutil.rmtree(target, onexc=retry)
        else:
            shutil.rmtree(target, onerror=lambda f, t, e: retry(f, t, e[1]))
    except OSError as error:
        errors.append(str(error))
    if os.path.lexists(path):
        return errors[0] if errors else "still exists"
    return None


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def check_removable(path: Path, repo: Path, allowed_roots: list[Path]) -> None:
    """Raise ValueError unless `path` is strictly inside .claude/worktrees or an allowed root."""
    if is_reparse(path):
        raise ValueError(f"{path} is a link, not a worktree folder")
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
