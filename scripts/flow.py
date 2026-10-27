"""Evidence gate and metrics for the agent flow (`.work/<task>/*.yaml`).

    python scripts/flow.py check T3.1                       # where is the task, what is next
    python scripts/flow.py gate T3.1 --head <sha>           # exit 1 when anything blocks the merge
    python scripts/flow.py record T3.1 --pr 29              # after the merge: a row in metrics.csv
    python scripts/flow.py retro [--last 5]                 # medians: last N tasks vs the N before

Each agent writes one YAML file of its own (keys: step, verdict, sha, by, at, round, open_orange,
tokens, summary). The files are flat enough for the small reader below, so the script needs
nothing beyond the standard library, `git` and `gh`.
"""

import argparse
import csv
import io
import json
import re
import statistics
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Targets for `retro` (docs/agent.md): hours by risk, one round per gate, one failed CI run.
HOURS_TARGET = {"red": 8.0, "yellow": 3.0, "none": 3.0}
ROUNDS_TARGET = 3.0
CI_FAILED_TARGET = 1.0
WORSE_BY = 0.20

CSV_FIELDS = [
    "task", "risk", "pr", "lane", "started_at", "merged_at", "hours", "review_rounds",
    "tester_rounds", "pm_rounds", "ci_failed_runs", "subagent_tokens", "orange_found", "notes",
]  # fmt: skip

# name, glob in .work/<task>/, who writes it, accepted verdicts, only for risk red
EVIDENCE = [
    ("plan-review", "plan-review.yaml", "security-reviewer", {"pass"}, True),
    ("review-task", "review-task-*.yaml", "security-reviewer", {"pass"}, True),
    ("tester", "tester.yaml", "feature-tester", {"pass"}, True),
    ("review", "review.yaml", "security-reviewer", {"merge"}, False),
    ("pm", "pm.yaml", "project-manager", {"pass"}, False),
]
CI_GOOD = {"SUCCESS", "SKIPPED", "NEUTRAL"}


# -- the small YAML reader ---------------------------------------------------------------------


def _split_top(text: str) -> list[str]:
    parts, depth, quote, current = [], 0, "", ""
    for char in text:
        if quote:
            quote = "" if char == quote else quote
        elif char in "\"'":
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(current)
            current = ""
            continue
        current += char
    if current.strip():
        parts.append(current)
    return parts


def _scalar(text: str) -> Any:
    text = text.strip()
    if text[:1] == "[" and text[-1:] == "]":
        return [_scalar(part) for part in _split_top(text[1:-1])]
    if text[:1] == "{" and text[-1:] == "}":
        found: dict[str, Any] = {}
        for part in _split_top(text[1:-1]):
            key, _, value = part.partition(":")
            found[key.strip()] = _scalar(value)
        return found
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text in ("null", "~", ""):
        return None
    if text in ("true", "false"):
        return text == "true"
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def _strip_comment(line: str) -> str:
    quote = ""
    for index, char in enumerate(line):
        if quote:
            quote = "" if char == quote else quote
        elif char in "\"'":
            quote = char
        elif char == "#" and (index == 0 or line[index - 1] == " "):
            return line[:index]
    return line


def _block(lines: list[tuple[int, str]], start: int, indent: int) -> tuple[Any, int]:
    """Read the block at `indent` from `start`: a mapping, or a list when it starts with `- `."""
    if lines[start][1].startswith("- "):
        items: list[Any] = []
        index = start
        while index < len(lines) and lines[index][0] == indent and lines[index][1].startswith("- "):
            rest = lines[index][1][2:]
            index += 1
            if re.match(r"[\w-]+:( |$)", rest) and not rest.startswith(("{", "[", '"')):
                # `- key: value` opens a mapping whose other keys are indented under the dash
                sub = [(indent + 2, rest)]
                while index < len(lines) and lines[index][0] > indent:
                    sub.append(lines[index])
                    index += 1
                items.append(_block(sub, 0, indent + 2)[0])
            else:
                items.append(_scalar(rest))
        return items, index
    result: dict[str, Any] = {}
    index = start
    while index < len(lines) and lines[index][0] == indent:
        key, _, value = lines[index][1].partition(":")
        index += 1
        if value.strip() == "" and index < len(lines) and lines[index][0] >= indent:
            nested = lines[index][0]
            if nested > indent or lines[index][1].startswith("- "):
                result[key.strip()], index = _block(lines, index, nested)
                continue
        result[key.strip()] = _scalar(value)
    return result, index


def parse_yaml(text: str) -> dict[str, Any]:
    """Flat key/value YAML with inline `[..]`/`{..}`, block lists and one level of nesting."""
    lines = []
    for raw in text.splitlines():
        stripped = _strip_comment(raw).rstrip()
        if stripped.strip():
            lines.append((len(stripped) - len(stripped.lstrip()), stripped.strip()))
    if not lines:
        return {}
    found, _ = _block(lines, 0, lines[0][0])
    return found if isinstance(found, dict) else {}


# -- evidence ---------------------------------------------------------------------------------


def main_repo() -> Path:
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        check=False, capture_output=True, text=True,
    )  # fmt: skip
    return Path(common.stdout.strip()).parent


def load(path: Path) -> dict[str, Any] | None:
    try:
        return parse_yaml(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def same_sha(left: Any, right: Any) -> bool:
    a, b = str(left or ""), str(right or "")
    return len(a) >= 7 and len(b) >= 7 and (a.startswith(b) or b.startswith(a))


def is_ancestor(repo: Path, sha: str, head: str) -> bool:
    if same_sha(sha, head):
        return True
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", str(sha), head],
        check=False, capture_output=True, text=True,
    )  # fmt: skip
    return result.returncode == 0


def gather(work: Path, task: str) -> dict[str, Any]:
    folder = work / task
    found: dict[str, Any] = {"card": load(folder / "card.yaml"), "lane-report": None}
    found["lane-report"] = load(folder / "lane-report.yaml")
    for name, pattern, _who, _ok, _red in EVIDENCE:
        files = sorted(folder.glob(pattern)) if folder.exists() else []
        found[name] = [(file.name, load(file)) for file in files]
    return found


def judge(
    name: str, docs: list[tuple[str, dict[str, Any] | None]], head: str | None, repo: Path
) -> tuple[str, str]:
    """('ok'|'missing'|'fail', reason) for one evidence kind against the head sha (if known)."""
    ok_verdicts = next(item[3] for item in EVIDENCE if item[0] == name)
    if not docs:
        return "missing", "thiếu file"
    reasons = []
    passed = 0
    for file, doc in docs:
        if doc is None:
            reasons.append(f"{file}: không đọc được")
            continue
        if doc.get("verdict") not in ok_verdicts:
            reasons.append(f"{file}: verdict={doc.get('verdict')!r}")
            continue
        if int(doc.get("open_orange") or 0) > 0:
            reasons.append(f"{file}: còn {doc.get('open_orange')} 🟠 mở")
            continue
        if head and name in ("review", "pm") and not same_sha(doc.get("sha"), head):
            reasons.append(f"{file}: sha {doc.get('sha')} khác HEAD {head[:7]}")
            continue
        if (
            head
            and name in ("tester", "review-task")
            and not is_ancestor(repo, str(doc.get("sha") or ""), head)
        ):
            reasons.append(f"{file}: sha {doc.get('sha')} không thuộc nhánh tới {head[:7]}")
            continue
        passed += 1
    # review-task: one file per task; every present file must pass, at least one must exist
    if reasons:
        return "fail", "; ".join(reasons)
    return ("ok", "") if passed else ("missing", "thiếu file")


def lane_done(report: dict[str, Any] | None) -> tuple[str, str]:
    if report is None:
        return "missing", "thiếu lane-report.yaml"
    if report.get("status") != "done":
        return "fail", f"lane-report status={report.get('status')!r}"
    return "ok", ""


def gate(work: Path, task: str, head: str, repo: Path) -> list[str]:
    """Reasons the merge is blocked; empty when every required file passes at `head`."""
    found = gather(work, task)
    card = found["card"]
    if card is None:
        return [f"thiếu {work / task / 'card.yaml'}"]
    red = card.get("risk") == "red"
    problems = []
    state, reason = lane_done(found["lane-report"])
    if state != "ok":
        problems.append(f"lane-report: {reason}")
    for name, _pattern, _who, _ok, only_red in EVIDENCE:
        if only_red and not red:
            continue
        state, reason = judge(name, found[name], head, repo)
        if state != "ok":
            problems.append(f"{name}: {reason}")
    return problems


# -- GitHub (mocked in tests) -------------------------------------------------------------------


def _run(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(args, check=False, capture_output=True, text=True, cwd=cwd)
    return result.stdout if result.returncode == 0 else ""


def open_pr(branch: str, repo: Path) -> dict[str, Any] | None:
    out = _run(
        ["gh", "pr", "list", "--head", branch, "--state", "open",
         "--json", "number,headRefOid,mergeable,statusCheckRollup"],
        repo,
    )  # fmt: skip
    try:
        prs = json.loads(out or "[]")
    except json.JSONDecodeError:
        return None
    return prs[0] if prs else None


def ci_state(pr: dict[str, Any]) -> tuple[str, str]:
    runs = pr.get("statusCheckRollup") or []
    if not runs:
        return "missing", "chưa có CI"
    bad = [r for r in runs if (r.get("conclusion") or r.get("state") or "") not in CI_GOOD]
    if not bad:
        return "ok", ""
    pending = [r for r in bad if r.get("status") in ("IN_PROGRESS", "QUEUED", "PENDING")]
    return ("missing", "CI đang chạy") if len(pending) == len(bad) else ("fail", "CI đỏ")


def check(work: Path, task: str, repo: Path) -> list[str]:
    found = gather(work, task)
    card = found["card"]
    if card is None:
        return [f"✗ card (thiếu {work / task / 'card.yaml'})", "next: card (orchestrator)"]
    red = card.get("risk") == "red"
    branch = str(card.get("branch") or "")
    worktree = Path(str(card.get("worktree") or repo))
    git_dir = worktree if worktree.exists() else repo
    pr = open_pr(branch, repo) if branch else None
    head = str(pr["headRefOid"]) if pr else None
    report = found["lane-report"]
    ref = head or (str(report.get("head_sha")) if report and report.get("head_sha") else None)

    steps: list[tuple[str, str, str, str]] = [("card", "ok", "", "orchestrator")]
    for name, _pattern, who, _ok, only_red in EVIDENCE[:1]:
        steps.append(_evidence_step(name, who, only_red, red, found, head, git_dir))
    state, reason = lane_done(report)
    steps.append(("code", state, reason, f"lane lead {card.get('lane', '')}".strip()))
    for name, _pattern, who, _ok, only_red in EVIDENCE[1:3]:
        steps.append(_evidence_step(name, who, only_red, red, found, ref, git_dir))
    steps.append(("pr", "ok" if pr else "missing", "" if pr else "chưa có PR mở", "orchestrator"))
    for name, _pattern, who, _ok, only_red in EVIDENCE[3:]:
        steps.append(_evidence_step(name, who, only_red, red, found, head, git_dir))
    if pr:
        state, reason = ci_state(pr)
    else:
        state, reason = "missing", "chưa có PR"
    steps.append(("ci", state, reason, "orchestrator"))

    lines, missing = [], []
    for name, state, reason, who in steps:
        mark = {"ok": "✓", "na": "—"}.get(state, "✗")
        lines.append(f"{mark} {name}" + (f"  ({reason})" if reason else ""))
        if state not in ("ok", "na"):
            missing.append((name, who, reason))
    ready = not missing and pr is not None and pr.get("mergeable") != "CONFLICTING"
    lines.append(f"{'✓' if ready else '✗'} mergeable")
    if missing:
        lines.append(f"next: {missing[0][0]} ({missing[0][1]})")
        lines.append("thiếu: " + ", ".join(f"{n} [{r}]" if r else n for n, _w, r in missing))
    else:
        lines.append("next: merge (orchestrator)")
    return lines


def _evidence_step(
    name: str, who: str, only_red: bool, red: bool, found: dict[str, Any],
    head: str | None, git_dir: Path,
) -> tuple[str, str, str, str]:  # fmt: skip
    if only_red and not red:
        return name, "na", "", who
    state, reason = judge(name, found[name], head, git_dir)
    return name, state, reason, who


# -- metrics ------------------------------------------------------------------------------------


def _when(text: str) -> datetime:
    return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))


def _round(doc: dict[str, Any] | None) -> int:
    return int((doc or {}).get("round") or 0)


def _sum(docs: list[dict[str, Any] | None], key: str) -> int:
    return sum(int(doc.get(key) or 0) for doc in docs if doc)


def build_row(work: Path, task: str, pr: int, repo: Path, notes: str = "") -> dict[str, Any]:
    found = gather(work, task)
    card = found["card"] or {}
    branch = str(card.get("branch") or "")
    base = str(card.get("base") or "origin/main")
    first = _run(["git", "log", f"{base}..{branch}", "--reverse", "--format=%aI"], repo)
    started = first.splitlines()[0] if first.strip() else ""
    view = _run(["gh", "pr", "view", str(pr), "--json", "mergedAt"], repo)
    merged = str(json.loads(view or "{}").get("mergedAt") or "")
    runs = _run(
        ["gh", "run", "list", "--branch", branch, "--json", "conclusion", "--limit", "100"], repo
    )
    failed = sum(1 for run in json.loads(runs or "[]") if run.get("conclusion") == "failure")
    hours = ""
    if started and merged:
        hours = f"{(_when(merged) - _when(started)).total_seconds() / 3600:.1f}"
    docs = [doc for name, *_ in EVIDENCE for _file, doc in found[name]] + [found["lane-report"]]

    def first_doc(name: str) -> dict[str, Any] | None:
        return found[name][0][1] if found[name] else None

    return {
        "task": task, "risk": card.get("risk", ""), "pr": pr, "lane": card.get("lane", ""),
        "started_at": started, "merged_at": merged, "hours": hours,
        "review_rounds": _round(first_doc("review")), "tester_rounds": _round(first_doc("tester")),
        "pm_rounds": _round(first_doc("pm")), "ci_failed_runs": failed,
        "subagent_tokens": _sum(docs, "tokens"), "orange_found": _sum(docs, "orange_total"),
        "notes": notes,
    }  # fmt: skip


def record(out: Path, row: dict[str, Any]) -> None:
    rows: list[dict[str, str]] = []
    if out.exists():
        with out.open(newline="", encoding="utf-8") as handle:
            rows = [r for r in csv.DictReader(handle) if r["task"] != row["task"]]
    rows.append({key: str(value) for key, value in row.items()})
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _num(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key) or 0)
    except ValueError:
        return 0.0


def _metrics(row: dict[str, str]) -> dict[str, float]:
    rounds = sum(_num(row, k) for k in ("review_rounds", "tester_rounds", "pm_rounds"))
    return {
        "hours": _num(row, "hours"),
        "subagent_tokens": _num(row, "subagent_tokens"),
        "rounds": rounds,
        "ci_failed_runs": _num(row, "ci_failed_runs"),
    }


def _target(metric: str, row: dict[str, str]) -> float | None:
    if metric == "hours":
        return HOURS_TARGET.get(row.get("risk", ""), HOURS_TARGET["none"])
    return {"rounds": ROUNDS_TARGET, "ci_failed_runs": CI_FAILED_TARGET}.get(metric)


def _median(rows: list[dict[str, str]], metric: str) -> float | None:
    return statistics.median(_metrics(r)[metric] for r in rows) if rows else None


def _table(title: str, rows: list[dict[str, str]], last: int) -> tuple[list[str], str | None]:
    recent, before = rows[-last:], rows[-2 * last : -last]
    lines = [f"{title} ({len(recent)} gần nhất vs {len(before)} trước đó)"]
    lines.append(f"  {'chỉ số':<17}{'trước':>10}{'gần nhất':>10}  ghi chú")
    far: tuple[float, str] | None = None
    for metric in ("hours", "subagent_tokens", "rounds", "ci_failed_runs"):
        now, was = _median(recent, metric), _median(before, metric)
        note = ""
        if now is not None and was and now > was * (1 + WORSE_BY):
            note = f"XẤU ĐI +{(now / was - 1) * 100:.0f}%"
        ratios = [_metrics(r)[metric] / t for r in recent if (t := _target(metric, r))]
        if ratios:
            ratio = statistics.median(ratios)
            if far is None or ratio > far[0]:
                far = (ratio, metric)
        was_text = "-" if was is None else f"{was:g}"
        now_text = "-" if now is None else f"{now:g}"
        lines.append(f"  {metric:<17}{was_text:>10}{now_text:>10}  {note}".rstrip())
    mark = None
    if far and far[0] > 1:
        mark = f"xa mục tiêu nhất: {far[1]} (x{far[0]:.1f} so với mục tiêu)"
        lines.append(f"  {mark}")
    return lines, mark


def retro(csv_path: Path, last: int = 5) -> list[str]:
    rows: list[dict[str, str]] = []
    if csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    rows.sort(key=lambda r: r.get("merged_at", ""))
    if len(rows) < last:
        return [f"chưa đủ dữ liệu ({len(rows)}/{last} task trong {csv_path})"]
    out, _ = _table("tất cả", rows, last)
    for risk in ("red", "yellow", "none"):
        part = [r for r in rows if r.get("risk") == risk]
        if len(part) >= 2:
            lines, _ = _table(f"risk {risk}", part, min(last, max(1, len(part) // 2)))
            out += lines
    return out


# -- CLI ----------------------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="flow.py")
    parser.add_argument("--work", type=Path, help="the .work folder (default: <main repo>/.work)")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("check").add_argument("task")
    p_gate = sub.add_parser("gate")
    p_gate.add_argument("task")
    p_gate.add_argument("--head", required=True)
    p_rec = sub.add_parser("record")
    p_rec.add_argument("task")
    p_rec.add_argument("--pr", type=int, required=True)
    p_rec.add_argument("--notes", default="")
    p_rec.add_argument("--out", type=Path)
    p_retro = sub.add_parser("retro")
    p_retro.add_argument("--last", type=int, default=5)
    p_retro.add_argument("--csv", type=Path)
    args = parser.parse_args(argv)
    repo = main_repo()
    work = args.work or repo / ".work"
    metrics = repo / "docs" / "ops" / "metrics.csv"
    if args.action == "check":
        print("\n".join(check(work, args.task, repo)))
    elif args.action == "gate":
        problems = gate(work, args.task, args.head, repo)
        for problem in problems:
            print(f"✗ {problem}")
        print("gate: " + ("CHẶN" if problems else "đạt"))
        return 1 if problems else 0
    elif args.action == "record":
        out = args.out or metrics
        row = build_row(work, args.task, args.pr, repo, args.notes)
        record(out, row)
        print(f"flow: {args.task} -> {out}")
    else:
        print("\n".join(retro(args.csv or metrics, args.last)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
