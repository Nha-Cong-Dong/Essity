"""Git pre-commit / pre-push guard: a lane worktree may only commit on its card's branch.

Overnight 01/11 a lane lead committed onto another open PR's branch twice. `lane.py up`
installs `pre-commit` and `pre-push` in the shared hooks dir; both call this script with the
repository root. A worktree `.claude/worktrees/L<n>` is checked against every
`.work/*/card.yaml` (main checkout and the worktree itself) whose `lane:` is `L<n>`: the current
branch must be the `branch:` of one of them. No card for the lane, a detached HEAD (rebase) or a
checkout that is not a lane worktree pass.
"""

import re
import subprocess
import sys
from pathlib import Path

HOOK_NAMES = ("pre-commit", "pre-push")


def _flat(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        found = re.match(r"^([A-Za-z_]+):\s*(.*?)\s*$", line)
        if found:
            out[found.group(1)] = found.group(2).strip("\"'")
    return out


def card_branches(repo: Path, top: Path, lane: str) -> set[str]:
    branches: set[str] = set()
    for root in {repo, top}:
        for card_file in (root / ".work").glob("*/card.yaml"):
            card = _flat(card_file)
            if card.get("lane") == lane and card.get("branch"):
                branches.add(card["branch"])
    return branches


def refusal(repo: Path, top: Path, branch: str) -> str | None:
    """Why the commit/push must stop, or None."""
    if not branch or not re.fullmatch(r"L\d+", top.name):
        return None
    if top.parent != repo / ".claude" / "worktrees":
        return None
    expected = card_branches(repo, top, top.name)
    if not expected or branch in expected:
        return None
    return (
        f"branch_guard: {top.name} is on branch '{branch}' but its card says "
        f"{', '.join(sorted(expected))}. Do not commit onto another PR's branch; run "
        f"`python scripts/lane.py up {top.name} <branch>` (after `lane.py down {top.name}`)."
    )


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return result.stdout.strip()


def main(argv: list[str]) -> int:
    repo = Path(argv[1]).resolve()
    top = Path(_git("rev-parse", "--show-toplevel")).resolve()
    reason = refusal(repo.resolve(), top, _git("branch", "--show-current"))
    if reason:
        print(reason, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
