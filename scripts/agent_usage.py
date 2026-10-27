"""Token use of Claude Code sessions and their subagents, read from the local transcripts.

    python scripts/agent_usage.py                       # by role and model, all Essity sessions
    python scripts/agent_usage.py --since 2026-10-28    # only sessions started on or after that day
    python scripts/agent_usage.py --by session          # one line per main session
    python scripts/agent_usage.py --json                # the role summary as JSON

Claude Code writes one JSONL per session under ~/.claude/projects/<project>/, and one per
subagent under <session>/subagents/ with a .meta.json naming its type and model. Token counts are
measured; dollars are estimated from the list prices in PRICES (change them if they move), so read
them as a share of quota on a subscription.
"""

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# USD per million tokens: (input, output). Cache reads cost 0.1x input, cache writes 1.25x.
PRICES = {"opus": (5.0, 25.0), "fable": (5.0, 25.0), "sonnet": (3.0, 15.0), "haiku": (1.0, 5.0)}
CACHE_READ, CACHE_WRITE = 0.1, 1.25
PROJECTS = Path.home() / ".claude" / "projects"


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
            yield record.get("timestamp", ""), message.get("model", ""), message["usage"]


def _context(usage: dict) -> int:
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
    )


def scan(path: Path) -> Usage:
    u = Usage()
    for ts, model, usage in _assistant_turns(path):
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
                try:
                    meta = json.loads(sub.with_suffix(".meta.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    meta = {}
                role = meta.get("customAgentType") or meta.get("agentType") or "general"
                rows.append(
                    Row(
                        "sub",
                        transcript.stem,
                        role,
                        meta.get("name") or sub.stem,
                        meta.get("model") or "",
                        scan(sub),
                    )
                )
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


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="agent_usage.py")
    parser.add_argument(
        "--since", default="", help="YYYY-MM-DD: sessions started on or after this day"
    )
    parser.add_argument("--project", default="D--Essity*", help="glob under ~/.claude/projects")
    parser.add_argument("--by", choices=["role", "session"], default="role")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
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
