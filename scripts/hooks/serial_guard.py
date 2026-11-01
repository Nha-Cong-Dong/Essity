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
import shlex
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


# Programs that only read or print: their arguments may name a protected command or path.
READERS = {
    "echo", "printf", "cat", "grep", "egrep", "fgrep", "rg", "head", "tail", "ls", "less",
    "wc", "diff", "find", "stat", "test", "pwd", "git", "sort", "uniq", "tr", "cut", "jq",
}  # fmt: skip
_REDIRECT = re.compile(r"^\d*>>?(.*)$")
_ASSIGN = re.compile(r"^[A-Za-z_]\w*=")
_SEPARATORS = set(";&|\n")


def _drop_heredocs(command: str) -> str:
    """Remove heredoc bodies: they are data, not commands."""
    out: list[str] = []
    end: str | None = None
    for line in command.split("\n"):
        if end is not None:
            if line.strip() == end:
                end = None
            continue
        out.append(line)
        found = re.search(r"<<-?\s*(['\"]?)(\w+)\1", line)
        if found:
            end = found.group(2)
    return "\n".join(out)


def _tokens(command: str) -> list[list[str]]:
    """Simple commands of a shell line (quotes honoured; `;` `&&` `||` `|` newline split)."""
    text = re.sub(
        r"\\(?=[\w.])", "/", _drop_heredocs(command)
    )  # Windows paths survive shlex
    lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError:
        words = text.split()
    segments: list[list[str]] = [[]]
    for word in words:
        if word and set(word) <= _SEPARATORS:
            segments.append([])
        else:
            segments[-1].append(word)
    return [seg for seg in segments if seg]


def _resolve(word: str, base: Path) -> Path:
    msys = re.match(r"^/([A-Za-z])(/.*|$)", word)
    path = Path(f"{msys.group(1)}:{msys.group(2) or '/'}") if msys else Path(word)
    return (path if path.is_absolute() else base / path).resolve()


def _is_protected_path(path: Path) -> bool:
    posix = path.as_posix()
    return "/.work/" not in posix and any(p.search(posix) for p in SERIAL_PATHS)


def _lane_dir(words: list[str], base: Path) -> Path:
    """An absolute path inside a lane worktree named by the command wins over the cwd."""
    for word in words:
        if "worktrees" in word:
            parts = _resolve(word, base).parts
            if "worktrees" in parts and parts.index("worktrees") + 1 < len(parts):
                return Path(*parts[: parts.index("worktrees") + 2])
    return base


def _bash_targets(command: str, cwd: Path) -> list[Path]:
    targets: list[Path] = []
    here = cwd.resolve()
    for words in _tokens(command):
        while words and _ASSIGN.match(words[0]):
            words = words[1:]
        if not words:
            continue
        program, base = Path(words[0]).name, here
        if program == "cd" and len(words) > 1:
            here = _resolve(words[1], here)
            continue
        if program == "git" and "-C" in words[:-1]:
            base = _resolve(words[words.index("-C") + 1], here)
        base = _lane_dir(words, base)
        if program not in READERS and any(
            p.search(f"{base.as_posix()} {' '.join(words)}") for p in SERIAL_COMMANDS
        ):
            targets.append(base)
        for index, word in enumerate(words):
            found = _REDIRECT.match(word)
            if not found:
                continue
            target = found.group(1) or (
                words[index + 1] if index + 1 < len(words) else ""
            )
            if target and not target.startswith("&"):
                path = _resolve(target, base)
                if _is_protected_path(path):
                    targets.append(path)
    return targets


def serial_targets(tool: str, tool_input: dict[str, object], cwd: Path) -> list[Path]:
    """Where the call acts on serial resources; empty when it cannot touch one."""
    if tool == "Bash":
        return _bash_targets(str(tool_input.get("command", "")), cwd)
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        file_path = Path(str(tool_input.get("file_path", "")))
        if not file_path.is_absolute():
            file_path = cwd / file_path
        if _is_protected_path(file_path):
            return [file_path.resolve()]
    return []


def serial_target(tool: str, tool_input: dict[str, object], cwd: Path) -> Path | None:
    targets = serial_targets(tool, tool_input, cwd)
    return targets[0] if targets else None


def blocked_reason(
    tool: str, tool_input: dict[str, object], cwd: Path, repo: Path
) -> str | None:
    """Why the call must be blocked, or None to let it through."""
    owner = owner_path(repo)
    for where in serial_targets(tool, tool_input, cwd):
        if _inside(where, owner) and not _in_other_worktree(where, owner, repo):
            continue
        return (
            f"Blocked by serial_guard: migrations and the generated api-client belong to the "
            f"lane holding the serial lock ({owner}; default L1). Hand this task to L1, or ask "
            f"the orchestrator to move the lock in .work/serial-owner."
        )
    return None


def _repo_of(cwd: Path) -> Path:
    common = subprocess.run(
        [
            "git",
            "-C",
            str(cwd),
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return Path(common).parent if common else cwd


def main() -> int:
    call = json.load(sys.stdin)
    cwd = Path(call.get("cwd") or ".")
    tool, tool_input = call.get("tool_name", ""), call.get("tool_input") or {}
    if not serial_targets(tool, tool_input, cwd):
        return 0  # most calls: skip the git lookup below
    reason = blocked_reason(tool, tool_input, cwd, _repo_of(cwd))
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
