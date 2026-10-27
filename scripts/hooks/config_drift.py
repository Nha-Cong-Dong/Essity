"""SessionStart hook: warn when the live agent config differs from its reviewed copy.

Wired in `.claude/settings.json`. The check itself lives in the private docs repository
(`docs/_tools/config_drift.py`, next to the `docs/_backup/` copy it compares against); this file
only finds the main checkout and hands over. Without `docs/` (CI, other clones) it prints nothing.
"""

import os
import subprocess
import sys
from pathlib import Path


def main_checkout(cwd: Path) -> Path:
    """Lane worktrees live in `<checkout>/.claude/worktrees/<name>`; config and docs/ are in <checkout>."""
    path = cwd.resolve()
    parts = path.parts
    for i in range(len(parts) - 1):
        if parts[i] == ".claude" and parts[i + 1] == "worktrees":
            return Path(*parts[:i])
    return path


def run(root: Path) -> str:
    tool = root / "docs" / "_tools" / "config_drift.py"
    if not tool.is_file():
        return ""
    result = subprocess.run(
        [sys.executable, str(tool), "--root", str(root), "--hook"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    return result.stdout


def main() -> int:
    root = main_checkout(Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()))
    try:
        out = run(root)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0  # a warning hook must never block a session
    if out:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
