"""Token use of Claude Code sessions and their subagents, read from the local transcripts.

    python scripts/agent_usage.py                       # by role and model, all Essity sessions
    python scripts/agent_usage.py --since 2026-10-28    # only sessions started on or after that day
    python scripts/agent_usage.py --by session          # one line per main session
    python scripts/agent_usage.py --json                # the role summary as JSON
    python scripts/agent_usage.py --session latest --append docs/ops/sessions.csv
                                                        # one row per session (W1)

Claude Code writes one JSONL per session under ~/.claude/projects/<project>/, and one per
subagent under <session>/subagents/ with a .meta.json naming its type and model. Token counts are
measured; dollars are estimated from the list prices in PRICES (change them if they move), so read
them as a share of quota on a subscription.
"""

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# USD per million tokens: (input, output). Cache reads cost 0.1x input, cache writes 1.25x.
PRICES = {
    "opus": (5.0, 25.0),
    "fable": (5.0, 25.0),
    "sonnet": (3.0, 15.0),
    "haiku": (1.0, 5.0),
}
CACHE_READ, CACHE_WRITE = 0.1, 1.25
PROJECTS = Path.home() / ".claude" / "projects"


def _when(text: str) -> datetime:
    return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))


def family(model: str) -> str:
    return next((name for name in PRICES if name in model), "other")


@dataclass
class Usage:
    input: int = 0
    cache_write: int = 0
    cache_read: int = 0
    output: int = 0
    turns: int = 0
    max_context: int = 0
    first: str = ""
    models: Counter = field(default_factory=Counter)


def _assistant_turns(path: Path):
    """Yield (timestamp, model, usage) once per assistant message; streaming repeats messages."""
    seen: set[str] = set()
    try:
        lines = path.open(encoding="utf-8")
    except OSError:
        return
    with lines:
        for line in lines:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            message = record.get("message")
            if (
                record.get("type") != "assistant"
                or not isinstance(message, dict)
                or not message.get("usage")
            ):
                continue
            if message.get("id") in seen:
                continue
            seen.add(message.get("id"))
            yield (
                record.get("timestamp", ""),
                message.get("model", ""),
                message["usage"],
            )


def _context(usage: dict) -> int:
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
    )


def scan(path: Path, until: str = "") -> Usage:
    """Totals of a transcript; `until` (ISO time) drops the turns after it."""
    u = Usage()
    for ts, model, usage in _assistant_turns(path):
        if until and ts and _when(ts) > _when(until):
            continue
        u.first = u.first or ts
        u.input += usage.get("input_tokens", 0)
        u.cache_write += usage.get("cache_creation_input_tokens", 0)
        u.cache_read += usage.get("cache_read_input_tokens", 0)
        u.output += usage.get("output_tokens", 0)
        u.max_context = max(u.max_context, _context(usage))
        u.turns += 1
        u.models[family(model)] += 1
    return u


def last_context_tokens(path: Path, tail_bytes: int | None = None) -> int:
    """Context size of the latest assistant turn: what the next turn will carry at least.

    With `tail_bytes`, only the end of the file is read: a long session's transcript runs to tens
    of MB, and a hook calling this must stay fast. 0 when the tail holds no assistant turn.
    """
    last = 0
    if tail_bytes is None:
        for _, _, usage in _assistant_turns(path):
            last = _context(usage)
        return last
    try:
        with path.open("rb") as f:
            f.seek(max(0, f.seek(0, 2) - tail_bytes))
            tail = f.read().decode("utf-8", errors="ignore")
    except OSError:
        return 0
    for line in reversed(tail.splitlines()):
        try:
            record = json.loads(line)
        except ValueError:
            continue  # includes the line cut in half by the seek
        message = record.get("message")
        if record.get("type") == "assistant" and isinstance(message, dict) and message.get("usage"):
            return _context(message["usage"])
    return 0


def estimate_cost(u: Usage) -> float:
    """List-price estimate; a session that switched model is split by its share of turns."""
    total = sum(u.models.values()) or 1
    cost = 0.0
    for model, n in u.models.items():
        price_in, price_out = PRICES.get(model, (0.0, 0.0))
        tokens_in = u.input + u.cache_write * CACHE_WRITE + u.cache_read * CACHE_READ
        cost += n / total * (tokens_in * price_in + u.output * price_out) / 1e6
    return cost


@dataclass
class Row:
    kind: str  # main | sub
    session: str
    role: str
    name: str
    meta_model: str
    usage: Usage


def _sub_row(sub: Path, session: str) -> Row:
    try:
        meta = json.loads(sub.with_suffix(".meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    role = meta.get("customAgentType") or meta.get("agentType") or "general"
    return Row(
        "sub",
        session,
        role,
        meta.get("name") or sub.stem,
        meta.get("model") or "",
        scan(sub),
    )


def first_prompt(path: Path) -> str:
    """Text of the first user message: the brief a subagent was started with."""
    try:
        lines = path.open(encoding="utf-8")
    except OSError:
        return ""
    with lines:
        for line in lines:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            message = record.get("message")
            if record.get("type") != "user" or not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, list):
                return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
            return content if isinstance(content, str) else ""
    return ""


def task_subagents(task: str, projects: Path = PROJECTS, pattern: str = "D--Essity*") -> list[Row]:
    """Subagents whose first prompt names `task` as a whole code (T3.1 is not T3.10).

    The main session is not counted: it serves many tasks. Later messages sent to the same agent
    are in its own transcript, so they are counted with it.
    """
    code = re.compile(rf"(?<![\w.-]){re.escape(task)}(?![\w-]|\.\d)")
    rows: list[Row] = []
    for sub in sorted(projects.glob(f"{pattern}/*/subagents/*.jsonl")):
        if code.search(first_prompt(sub)):
            rows.append(_sub_row(sub, sub.parent.parent.name))
    return rows


def collect(projects: Path = PROJECTS, pattern: str = "D--Essity*", since: str = "") -> list[Row]:
    """Main sessions and their subagents; `since` (YYYY-MM-DD) keeps sessions started that day or later."""
    rows: list[Row] = []
    for project in sorted(projects.glob(pattern)):
        for transcript in sorted(project.glob("*.jsonl")):
            main = scan(transcript)
            if since and (not main.first or main.first[:10] < since):
                continue
            rows.append(Row("main", transcript.stem, "main", "main", "", main))
            for sub in sorted((project / transcript.stem / "subagents").glob("*.jsonl")):
                rows.append(_sub_row(sub, transcript.stem))
    return rows


def summarize(rows: list[Row]) -> dict:
    groups: dict[tuple[str, str], Counter] = {}
    for row in rows:
        u = row.usage
        total = sum(u.models.values())
        for model, n in u.models.items():
            share = n / total
            g = groups.setdefault((row.role, model), Counter())
            g["agents"] += share
            g["turns"] += n
            g["input"] += u.input * share
            g["cache_write"] += u.cache_write * share
            g["cache_read"] += u.cache_read * share
            g["output"] += u.output * share
            g["cost"] += estimate_cost(u) * share
    grand = sum(g["cost"] for g in groups.values()) or 1
    out = [
        {
            "role": role,
            "model": model,
            **{k: round(v, 2) for k, v in g.items()},
            "share": g["cost"] / grand,
        }
        for (role, model), g in sorted(groups.items(), key=lambda kv: -kv[1]["cost"])
    ]
    return {
        "sessions": sum(r.kind == "main" for r in rows),
        "subagents": sum(r.kind == "sub" for r in rows),
        "cost": round(sum(g["cost"] for g in groups.values()), 2),
        "groups": out,
    }


SESSION_FIELDS = [
    "date", "session", "main_tokens", "sub_tokens_opus", "sub_tokens_sonnet", "sub_tokens_haiku",
    "sub_tokens_other", "total_tokens", "usd", "merges", "tokens_per_merge", "relay_turns",
]  # fmt: skip
RELAY_TEXT = "Another Claude session sent a message"


def tokens(u: Usage) -> int:
    return u.input + u.cache_write + u.cache_read + u.output


def resolve_session(projects: Path, pattern: str, wanted: str) -> str:
    """Full id of the main session: `latest` is the transcript written last, else an id prefix."""
    transcripts = [t for project in projects.glob(pattern) for t in project.glob("*.jsonl")]
    if wanted == "latest":
        if not transcripts:
            raise ValueError(f"no session under {projects}/{pattern}")
        return max(transcripts, key=lambda t: t.stat().st_mtime).stem
    found = sorted({t.stem for t in transcripts if t.stem.startswith(wanted)})
    if len(found) != 1:
        raise ValueError(f"session {wanted!r} matches {len(found)} transcripts")
    return found[0]


def _is_relay(record: dict) -> bool:
    """A main-session turn started by a subagent's hand-back, a teammate's idle note, or a
    background task finishing, not by the user."""
    if record.get("type") == "queue-operation":
        return record.get("operation") == "enqueue" and "<task-notification>" in str(
            record.get("content", "")
        )
    if record.get("type") != "user":
        return False
    origin = record.get("origin")
    if isinstance(origin, dict) and origin.get("kind") == "peer":
        return True
    content = (record.get("message") or {}).get("content")
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return False
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return isinstance(content, str) and content.startswith(RELAY_TEXT)


def _span_and_relays(path: Path, until: str = "") -> tuple[str, str, int]:
    """(first timestamp, last timestamp, relay turns) of a main transcript, up to `until`."""
    first, last, relays = "", "", 0
    with path.open(encoding="utf-8") as lines:
        for line in lines:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            stamp = record.get("timestamp") or ""
            if until and stamp and _when(stamp) > _when(until):
                continue
            if stamp:
                first = min(first, stamp) if first else stamp
                last = max(last, stamp)
            relays += _is_relay(record)
    return first, last, relays


def merges_between(metrics: Path, first: str, last: str) -> int:
    """Rows of metrics.csv merged while the session ran."""
    if not (metrics.exists() and first and last):
        return 0
    start, end = _when(first), _when(last)
    with metrics.open(newline="", encoding="utf-8") as handle:
        stamps = [row.get("merged_at") or "" for row in csv.DictReader(handle)]
    return sum(1 for s in stamps if s and start <= _when(s) <= end)


def session_stats(
    projects: Path, pattern: str, session: str, metrics: Path, until: str = ""
) -> dict:
    transcript = next(
        p / f"{session}.jsonl" for p in projects.glob(pattern) if (p / f"{session}.jsonl").exists()
    )
    main = scan(transcript, until)
    first, last, relays = _span_and_relays(transcript, until)
    by_model: dict[str, float] = {}
    cost = estimate_cost(main)
    for sub in sorted((transcript.parent / session / "subagents").glob("*.jsonl")):
        u = scan(sub, until)
        cost += estimate_cost(u)
        total = sum(u.models.values()) or 1
        for model, n in u.models.items():
            by_model[model] = by_model.get(model, 0.0) + tokens(u) * n / total
    sub_tokens = {m: round(by_model.get(m, 0.0)) for m in ("opus", "sonnet", "haiku")}
    sub_tokens["other"] = round(sum(v for m, v in by_model.items() if m not in sub_tokens))
    total_tokens = tokens(main) + sum(sub_tokens.values())
    merges = merges_between(metrics, first, last)
    return {
        "date": first[:10], "session": session, "main_tokens": tokens(main),
        **{f"sub_tokens_{m}": v for m, v in sub_tokens.items()},
        "total_tokens": total_tokens, "usd": f"{cost:.2f}", "merges": merges,
        "tokens_per_merge": total_tokens // merges if merges else "", "relay_turns": relays,
    }  # fmt: skip


def append_session(out: Path, row: dict) -> None:
    """Add the session's row to sessions.csv, replacing an older row of the same session."""
    rows: list[dict[str, str]] = []
    if out.exists():
        with out.open(newline="", encoding="utf-8") as handle:
            rows = [r for r in csv.DictReader(handle) if r["session"] != row["session"]]
    rows.append({key: str(value) for key, value in row.items()})
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SESSION_FIELDS, restval="")
        writer.writeheader()
        writer.writerows(rows)


def main_repo() -> Path:
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        check=False, capture_output=True, text=True,
    )  # fmt: skip
    return Path(common.stdout.strip()).parent


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="agent_usage.py")
    parser.add_argument(
        "--since", default="", help="YYYY-MM-DD: sessions started on or after this day"
    )
    parser.add_argument("--project", default="D--Essity*", help="glob under ~/.claude/projects")
    parser.add_argument("--by", choices=["role", "session"], default="role")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--session", help="<id prefix|latest>: one line for that main session")
    parser.add_argument(
        "--append",
        type=Path,
        help="with --session: write the line to this CSV (relative: main repo)",
    )
    parser.add_argument("--metrics", type=Path, help="metrics.csv (default: docs/ops/metrics.csv)")
    parser.add_argument("--until", default="", help="with --session: ISO time, ignore what follows")
    args = parser.parse_args(argv)
    if args.session:
        repo = main_repo()
        session = resolve_session(PROJECTS, args.project, args.session)
        metrics = args.metrics or repo / "docs" / "ops" / "metrics.csv"
        row = session_stats(PROJECTS, args.project, session, metrics, args.until)
        print(", ".join(f"{k}={row[k]}" for k in SESSION_FIELDS))
        if args.append:
            out = args.append if args.append.is_absolute() else repo / args.append
            append_session(out, row)
            print(f"agent_usage: {session[:8]} -> {out}")
        return 0
    rows = collect(PROJECTS, args.project, args.since)
    if args.by == "session":
        for row in sorted((r for r in rows if r.kind == "main"), key=lambda r: r.usage.first):
            subs = [r for r in rows if r.kind == "sub" and r.session == row.session]
            u = row.usage
            avg = (u.input + u.cache_write + u.cache_read) // max(u.turns, 1)
            print(
                f"{u.first[:16]:17}{row.session[:8]}  turns={u.turns:5}  avg_ctx={avg // 1000:4}k  "
                f"max_ctx={u.max_context // 1000:4}k  main=${estimate_cost(u):7.2f}  "
                f"subagents={len(subs):3}  sub=${sum(estimate_cost(s.usage) for s in subs):7.2f}"
            )
        return 0
    summary = summarize(rows)
    if args.json:
        print(json.dumps(summary, indent=2))
        return 0
    print(
        f"sessions={summary['sessions']} subagents={summary['subagents']} estimated=${summary['cost']:.0f}"
    )
    print(
        f"{'role':22}{'model':8}{'agents':>7}{'turns':>7}{'in M':>7}{'cWrite M':>9}{'cRead M':>9}{'out M':>7}{'$':>8}{'%':>6}"
    )
    for g in summary["groups"]:
        print(
            f"{g['role'][:22]:22}{g['model']:8}{g['agents']:7.0f}{g['turns']:7.0f}{g['input'] / 1e6:7.2f}"
            f"{g['cache_write'] / 1e6:9.2f}{g['cache_read'] / 1e6:9.1f}{g['output'] / 1e6:7.2f}"
            f"{g['cost']:8.0f}{100 * g['share']:6.1f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
