"""PreToolUse hook: only the lane holding the serial lock may write migrations or the api-client.

Wired in `.claude/settings.json` for Bash, Edit and Write. Claude Code passes the tool call as
JSON on stdin; exit code 2 blocks the call and shows stderr to the model.

Serial resources have one chain each: Alembic has one head per service, and
`packages/api-client` is generated from one OpenAPI. Two lanes touching them at once is how
PR D and PR E both wrote migration 0011 (26/10). The owner is the integration lane L1
(`.claude/worktrees/L1`) unless the orchestrator names another checkout in `.work/serial-owner`.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

SERIAL_COMMANDS = [
    re.compile(r"\balembic\b.*\brevision\b"),
    re.compile(r"gen_api_client"),
    re.compile(r"\bjust\s+gen-api\b"),
    re.compile(r"openapi-typescript"),
    re.compile(r"api-client\b.*\bgenerate\b"),
]
SERIAL_PATHS = [
    re.compile(r"(^|/)services/[^/]+/migrations/versions/"),
    re.compile(r"(^|/)packages/api-client/src/"),
    re.compile(r"(^|/)packages/api-client/openapi\.json$"),
]


def owner_path(repo: Path) -> Path:
    marker = repo / ".work" / "serial-owner"
    if marker.exists():
        return Path(marker.read_text(encoding="utf-8").strip()).resolve()
    return (repo / ".claude" / "worktrees" / "L1").resolve()


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _in_other_worktree(where: Path, owner: Path, repo: Path) -> bool:
    """Lane worktrees live inside the main checkout: owning the main checkout is not owning them."""
    worktrees = (repo / ".claude" / "worktrees").resolve()
    if not _inside(where, worktrees) or where == worktrees:
        return False
    lane = worktrees / where.relative_to(worktrees).parts[0]
    return not _inside(owner, lane)


def serial_target(tool: str, tool_input: dict[str, object], cwd: Path) -> Path | None:
    """Where the call acts on a serial resource, or None when it cannot touch one."""
    if tool == "Bash":
        command = str(tool_input.get("command", ""))
        if not any(pattern.search(command) for pattern in SERIAL_COMMANDS):
            return None
        return cwd.resolve()
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        file_path = Path(str(tool_input.get("file_path", "")))
        if not file_path.is_absolute():
            file_path = cwd / file_path
        if not any(p.search(file_path.as_posix()) for p in SERIAL_PATHS):
            return None
        return file_path.resolve()
    return None


def blocked_reason(tool: str, tool_input: dict[str, object], cwd: Path, repo: Path) -> str | None:
    """Why the call must be blocked, or None to let it through."""
    where = serial_target(tool, tool_input, cwd)
    if where is None:
        return None
    owner = owner_path(repo)
    if _inside(where, owner) and not _in_other_worktree(where, owner, repo):
        return None
    return (
        f"Blocked by serial_guard: migrations and the generated api-client belong to the lane "
        f"holding the serial lock ({owner}; default L1). Hand this task to L1, or ask the "
        f"orchestrator to move the lock in .work/serial-owner."
    )


def _repo_of(cwd: Path) -> Path:
    common = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return Path(common).parent if common else cwd


def main() -> int:
    call = json.load(sys.stdin)
    cwd = Path(call.get("cwd") or ".")
    tool, tool_input = call.get("tool_name", ""), call.get("tool_input") or {}
    if serial_target(tool, tool_input, cwd) is None:
        return 0  # most calls: skip the git lookup below
    reason = blocked_reason(tool, tool_input, cwd, _repo_of(cwd))
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
