"""SessionStart hook: say when five or more merges have gone without a retro (W3, 31/10).

Wired in `.claude/settings.json`. From 29/10 to 31/10, 31 merges went by and the measure → retro →
fix loop of `.claude/agent.md` §10 never ran: it lived only in memory. This prints the same
`RETRO DUE` line as `flow.py record`; `hooks/lane_gate.py` then refuses new lane leads until
`python scripts/flow.py retro` has run. Without `docs/` (CI, other clones) it prints nothing.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import flow
from config_drift import main_checkout


def message(repo: Path) -> str:
    line = flow.retro_due_line(flow.unretroed(*flow.ops_paths(repo)))
    if not line:
        return ""
    return f"{line}: chạy `python scripts/flow.py retro` trước khi giao lane lead (agent.md §10)."


def main() -> int:
    root = main_checkout(Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()))
    try:
        out = message(root)
    except (OSError, ValueError):
        return 0  # a reminder must never block a session
    if out:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
