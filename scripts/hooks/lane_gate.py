"""PreToolUse hook: refuse to start a lane lead while a retro is due or its task lacks schema.

Wired in `.claude/settings.json` for Agent. Claude Code passes the tool call as JSON on stdin;
exit code 2 blocks the call and shows stderr to the model. Only `subagent_type: lane-lead` is
checked:
- RETRO DUE (W3): five or more merges since the last `flow.py retro` (`flow.unretroed`).
- schema (W4): for each task whose `.work/<task>/card.yaml` is named in the prompt, every
  `needs_schema` column must exist in the card's base (`lane.schema_check`). A card without
  `needs_schema` only warns.
"""

import io
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import flow
import lane
from config_drift import main_checkout


def _tasks(prompt: str, repo: Path) -> list[str]:
    """Card folders named in the prompt as whole codes (T7.4 is not T7.40)."""
    found = []
    for card in sorted((repo / ".work").glob("*/card.yaml")):
        code = card.parent.name
        if re.search(rf"(?<![\w.-]){re.escape(code)}(?![\w-]|\.\d)", prompt):
            found.append(code)
    return found


def decide(call: dict, repo: Path) -> tuple[str | None, list[str]]:
    """(reason to block or None, warnings) for one tool call."""
    tool_input = call.get("tool_input") or {}
    if (
        call.get("tool_name") not in ("Agent", "Task")
        or tool_input.get("subagent_type") != "lane-lead"
    ):
        return None, []
    due = flow.retro_due_line(flow.unretroed(*flow.ops_paths(repo)))
    if due:
        return f"{due}: chạy `python scripts/flow.py retro` trước, rồi mới giao lane lead.", []
    notes: list[str] = []
    for task in _tasks(str(tool_input.get("prompt") or ""), repo):
        missing, more = lane.schema_check(repo, task)
        notes += more
        if missing:
            return (
                f"preflight {task}: thiếu cột trên base: {', '.join(missing)}. "
                "Merge migration trước (L1) hoặc sửa needs_schema trong card.",
                notes,
            )
    return None, notes


def main() -> int:
    call = json.load(sys.stdin)
    repo = main_checkout(Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()))
    reason, notes = decide(call, repo)
    if reason:
        if isinstance(sys.stderr, io.TextIOWrapper):
            sys.stderr.reconfigure(encoding="utf-8")
        print(reason, file=sys.stderr)
        return 2
    if notes:
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding="utf-8")
        context = {"hookEventName": "PreToolUse", "additionalContext": "\n".join(notes)}
        print(json.dumps({"hookSpecificOutput": context}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
