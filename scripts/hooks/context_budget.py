"""PostToolUse hook: tell the orchestrator when its own context has grown past the budget.

Wired in `.claude/settings.json` for Agent and SendMessage, the orchestrator's tools. Every turn
re-reads the whole context from cache, so a 300k-token orchestrator pays for 300k tokens on each
small step: the 15-27/10 baseline (docs/optimization-baseline.md) put that at about 45% of all
spend. Claude Code cannot /clear itself, so the hook only reminds; the orchestrator asks the user
to /clear at the next safe point (.claude/agent.md §6). Calls inside a subagent are ignored: lane
leads have `maxTurns` instead.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_usage import last_context_tokens

THRESHOLD = int(os.environ.get("CONTEXT_BUDGET_TOKENS", "200000"))
BAND = 50_000
TAIL = 2 * 1024 * 1024


def reminder(size: int, threshold: int, last_band: int) -> tuple[str | None, int]:
    """(text to add to the context or None, band to remember). Band 0 is under the threshold."""
    if size < threshold:
        return None, 0
    band = 1 + (size - threshold) // BAND
    if band <= last_band:
        return None, last_band
    text = (
        f"Ngữ cảnh phiên chính đang khoảng {size // 1000}k token, quá ngân sách "
        f"{threshold // 1000}k (.claude/agent.md §6). Mỗi lượt sau đọc lại toàn bộ phần này. "
        "Ở điểm dừng an toàn kế tiếp (PR vừa merge, hoặc mọi luồng đã push và BOARD đã cập nhật), "
        'báo người dùng một dòng: nên /clear rồi gõ "tiếp tục"; phiên mới dựng lại từ BOARD.'
    )
    return text, band


def main(call: dict, state_dir: Path, threshold: int = THRESHOLD) -> int:
    if call.get("agent_id") or not call.get("transcript_path"):
        return 0
    size = last_context_tokens(Path(call["transcript_path"]), tail_bytes=TAIL)
    state = state_dir / f"{call.get('session_id', 'unknown')}.band"
    try:
        last_band = int(state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        last_band = 0
    text, band = reminder(size, threshold, last_band)
    if band != last_band:
        state_dir.mkdir(parents=True, exist_ok=True)
        state.write_text(str(band), encoding="utf-8")
    if text:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}
        print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(json.load(sys.stdin), Path(tempfile.gettempdir()) / "claude-context-budget"))
