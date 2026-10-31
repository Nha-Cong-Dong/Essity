"""Tests for agent_usage.py. Run: python -m unittest discover -s scripts -p "test_*.py"."""

import json
import tempfile
import unittest
from pathlib import Path

from agent_usage import (
    collect,
    estimate_cost,
    last_context_tokens,
    scan,
    summarize,
    task_subagents,
)


def turn(msg_id: str, model: str, ts: str, inp: int, write: int, read: int, out: int) -> dict:
    return {
        "type": "assistant",
        "timestamp": ts,
        "message": {
            "id": msg_id,
            "model": model,
            "usage": {
                "input_tokens": inp,
                "cache_creation_input_tokens": write,
                "cache_read_input_tokens": read,
                "output_tokens": out,
            },
        },
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def sub_transcript(
    root: Path,
    name: str,
    prompt: str | list,
    model: str = "claude-sonnet-5-5",
    out: int = 10,
) -> None:
    """A fake subagent under <root>/D--Essity/<session>/subagents/ with one assistant turn."""
    base = root / "D--Essity" / "sess" / "subagents"
    user = {"type": "user", "message": {"role": "user", "content": prompt}}
    write_jsonl(base / f"agent-{name}.jsonl", [user, turn(name, model, "t", 100, 0, 900, out)])
    meta = {"customAgentType": "lane-lead", "model": model}
    base.joinpath(f"agent-{name}.meta.json").write_text(json.dumps(meta), encoding="utf-8")


class TaskSubagents(unittest.TestCase):
    def codes(self, root: Path, task: str) -> list:
        return sorted(
            r.name.removeprefix("agent-") for r in task_subagents(task, root, "D--Essity*")
        )

    def test_matches_whole_task_code_and_work_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sub_transcript(root, "a", "Luồng L1, task T3.1 (card).")
            sub_transcript(root, "b", r"Xem D:\Essity\.work\T-OPS-NEXT\card.yaml")
            sub_transcript(root, "c", [{"type": "text", "text": "xong T3.1."}])
            sub_transcript(root, "d", "task T3.10 khác")
            sub_transcript(root, "e", "không nhắc mã nào ở tin đầu")
            self.assertEqual(self.codes(root, "T3.1"), ["a", "c"])
            self.assertEqual(self.codes(root, "T-OPS-NEXT"), ["b"])
            self.assertEqual(self.codes(root, "T9"), [])

    def test_only_the_first_prompt_assigns_the_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sub_transcript(root, "x", "việc khác hẳn")
            path = root / "D--Essity" / "sess" / "subagents" / "agent-x.jsonl"
            later = {
                "type": "user",
                "message": {"role": "user", "content": "T3.1 ở tin sau"},
            }
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(later) + "\n")
            self.assertEqual(self.codes(root, "T3.1"), [])

    def test_sums_tokens_and_prices_by_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sub_transcript(root, "s", "T5", "claude-sonnet-5-5", out=1_000_000)
            sub_transcript(root, "o", "T5", "claude-opus-5-5", out=1_000_000)
            rows = task_subagents("T5", root, "D--Essity*")
        self.assertEqual(
            sum(r.usage.input + r.usage.cache_read + r.usage.output for r in rows),
            2_002_000,
        )
        cost = {r.name.removeprefix("agent-"): estimate_cost(r.usage) for r in rows}
        self.assertGreater(cost["o"], cost["s"])


class Scan(unittest.TestCase):
    def test_counts_each_message_once_and_tracks_the_largest_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.jsonl"
            first = turn("m1", "claude-opus-5-5", "2026-10-27T01:00:00Z", 10, 100, 1000, 5)
            # Streaming writes the same message twice; it must count once.
            write_jsonl(
                path,
                [
                    first,
                    first,
                    turn("m2", "claude-opus-5-5", "2026-10-27T01:01:00Z", 20, 0, 3000, 7),
                ],
            )
            u = scan(path)
        self.assertEqual(u.turns, 2)
        self.assertEqual((u.input, u.cache_write, u.cache_read, u.output), (30, 100, 4000, 12))
        self.assertEqual(u.max_context, 3020)
        self.assertEqual(u.models, {"opus": 2})

    def test_ignores_broken_lines_and_turns_without_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.jsonl"
            path.write_text(
                'not json\n{"type": "user", "message": {"content": "hi"}}\n',
                encoding="utf-8",
            )
            self.assertEqual(scan(path).turns, 0)

    def test_last_context_is_the_context_of_the_latest_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.jsonl"
            write_jsonl(
                path,
                [
                    turn("m1", "claude-opus-5-5", "t1", 1, 0, 300_000, 1),
                    turn("m2", "claude-opus-5-5", "t2", 1, 1_000, 120_000, 1),
                ],
            )
            self.assertEqual(last_context_tokens(path), 121_001)
            self.assertEqual(last_context_tokens(Path(tmp) / "missing.jsonl"), 0)


class Cost(unittest.TestCase):
    def test_cache_reads_cost_a_tenth_of_input_and_sonnet_is_cheaper_than_opus(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            opus, sonnet = Path(tmp) / "o.jsonl", Path(tmp) / "s.jsonl"
            write_jsonl(opus, [turn("a", "claude-opus-5-5", "t", 0, 0, 1_000_000, 0)])
            write_jsonl(sonnet, [turn("b", "claude-sonnet-5-5", "t", 0, 0, 1_000_000, 0)])
            self.assertAlmostEqual(estimate_cost(scan(opus)), 0.5)
            self.assertAlmostEqual(estimate_cost(scan(sonnet)), 0.3)


class Collect(unittest.TestCase):
    def make_project(self, root: Path) -> None:
        proj = root / "D--Essity"
        write_jsonl(
            proj / "s1.jsonl",
            [turn("m1", "claude-opus-5-5", "2026-10-26T10:00:00Z", 0, 0, 1000, 1)],
        )
        sub = proj / "s1" / "subagents" / "agent-rev-1.jsonl"
        write_jsonl(sub, [turn("m2", "claude-sonnet-5-5", "2026-10-26T10:05:00Z", 0, 0, 500, 1)])
        sub.with_suffix(".meta.json").write_text(
            json.dumps(
                {
                    "customAgentType": "security-reviewer",
                    "name": "rev-t2.1",
                    "model": "sonnet",
                }
            ),
            encoding="utf-8",
        )
        write_jsonl(
            proj / "s0.jsonl",
            [turn("m0", "claude-opus-5-5", "2026-10-20T10:00:00Z", 0, 0, 9, 1)],
        )

    def test_rows_carry_role_and_name_and_since_filters_by_session_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.make_project(Path(tmp))
            rows = collect(Path(tmp), "D--Essity*", since="2026-10-25")
        self.assertEqual(
            sorted((r.kind, r.role) for r in rows),
            [("main", "main"), ("sub", "security-reviewer")],
        )
        sub = next(r for r in rows if r.kind == "sub")
        self.assertEqual((sub.name, sub.meta_model), ("rev-t2.1", "sonnet"))

    def test_summary_groups_by_role_and_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.make_project(Path(tmp))
            summary = summarize(collect(Path(tmp), "D--Essity*"))
        self.assertEqual(summary["sessions"], 2)
        self.assertEqual(summary["subagents"], 1)
        by_key = {(g["role"], g["model"]): g for g in summary["groups"]}
        self.assertEqual(by_key[("main", "opus")]["turns"], 2)
        self.assertEqual(by_key[("security-reviewer", "sonnet")]["cache_read"], 500)
        self.assertAlmostEqual(sum(g["share"] for g in summary["groups"]), 1.0)


class Session(unittest.TestCase):
    """W1: one row per main session in docs/ops/sessions.csv."""

    def make(self, root: Path) -> Path:
        proj = root / "D--Essity"
        peer = {
            "type": "user",
            "timestamp": "2026-10-31T01:00:00Z",
            "message": {"content": "Another Claude session sent a message:\n<teammate-message>"},
        }
        handback = {
            "type": "user",
            "timestamp": "2026-10-31T01:10:00Z",
            "origin": {"kind": "peer", "handback": True},
            "message": {"content": [{"type": "text", "text": "report"}]},
        }
        notification = {
            "type": "queue-operation",
            "operation": "enqueue",
            "timestamp": "2026-10-31T01:20:00Z",
            "content": "<task-notification>\n<status>completed</status>",
        }
        human = {
            "type": "user",
            "timestamp": "2026-10-31T00:00:00Z",
            "origin": {"kind": "human"},
            "message": {"content": "tiếp tục"},
        }
        tool = {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "content": "Another Claude session"}]},
        }
        write_jsonl(
            proj / "s1.jsonl",
            [
                human,
                turn("m1", "claude-opus-5-5", "2026-10-31T00:00:05Z", 1, 2, 3, 4),
                peer,
                tool,
                handback,
                notification,
                turn("m2", "claude-opus-5-5", "2026-10-31T02:00:00Z", 10, 0, 0, 0),
            ],
        )
        sub = proj / "s1" / "subagents" / "agent-a.jsonl"
        write_jsonl(sub, [turn("m3", "claude-sonnet-5-5", "2026-10-31T00:30:00Z", 0, 0, 90, 10)])
        sub.with_suffix(".meta.json").write_text("{}", encoding="utf-8")
        write_jsonl(
            proj / "s0.jsonl", [turn("m0", "claude-opus-5-5", "2026-10-30T10:00:00Z", 0, 0, 9, 1)]
        )
        metrics = root / "metrics.csv"
        metrics.write_text(
            "task,merged_at\nA,2026-10-30T23:59:00Z\nB,2026-10-31T01:30:00Z\nC,2026-10-31T03:00:00Z\n",
            encoding="utf-8",
        )
        return metrics

    def test_stats_split_main_and_subagent_tokens_and_count_merges_and_relays(self) -> None:
        from agent_usage import session_stats

        with tempfile.TemporaryDirectory() as tmp:
            metrics = self.make(Path(tmp))
            got = session_stats(Path(tmp), "D--Essity*", "s1", metrics)
        self.assertEqual(got["date"], "2026-10-31")
        self.assertEqual(got["session"], "s1")
        self.assertEqual(got["main_tokens"], 20)
        self.assertEqual(got["sub_tokens_sonnet"], 100)
        self.assertEqual(got["sub_tokens_opus"], 0)
        self.assertEqual(got["total_tokens"], 120)
        self.assertEqual(got["merges"], 1)  # only B is inside 00:00..02:00
        self.assertEqual(got["tokens_per_merge"], 120)
        self.assertEqual(got["relay_turns"], 3)  # peer text, handback, task-notification
        self.assertRegex(got["usd"], r"^\d+\.\d\d$")

    def test_until_cuts_the_session_at_a_time(self) -> None:
        from agent_usage import session_stats

        with tempfile.TemporaryDirectory() as tmp:
            metrics = self.make(Path(tmp))
            got = session_stats(
                Path(tmp), "D--Essity*", "s1", metrics, until="2026-10-31T01:15:00Z"
            )
        self.assertEqual(got["main_tokens"], 10)  # m2 at 02:00 is cut
        self.assertEqual(got["sub_tokens_sonnet"], 100)
        self.assertEqual(got["relay_turns"], 2)
        self.assertEqual(got["merges"], 0)  # B merged at 01:30, after the cut

    def test_a_short_session_id_prefix_and_latest_are_resolved(self) -> None:
        import os

        from agent_usage import resolve_session

        with tempfile.TemporaryDirectory() as tmp:
            self.make(Path(tmp))
            proj = Path(tmp) / "D--Essity"
            os.utime(proj / "s0.jsonl", (1, 1))
            self.assertEqual(resolve_session(Path(tmp), "D--Essity*", "latest"), "s1")
            self.assertEqual(resolve_session(Path(tmp), "D--Essity*", "s0"), "s0")
            with self.assertRaises(ValueError):
                resolve_session(Path(tmp), "D--Essity*", "zz")

    def test_no_merge_leaves_tokens_per_merge_blank(self) -> None:
        from agent_usage import session_stats

        with tempfile.TemporaryDirectory() as tmp:
            self.make(Path(tmp))
            got = session_stats(Path(tmp), "D--Essity*", "s1", Path(tmp) / "missing.csv")
        self.assertEqual((got["merges"], got["tokens_per_merge"]), (0, ""))

    def test_append_writes_the_header_once_and_replaces_the_same_session(self) -> None:
        import csv

        from agent_usage import SESSION_FIELDS, append_session, session_stats

        with tempfile.TemporaryDirectory() as tmp:
            metrics = self.make(Path(tmp))
            out = Path(tmp) / "ops" / "sessions.csv"
            row = session_stats(Path(tmp), "D--Essity*", "s1", metrics)
            append_session(out, row)
            append_session(out, {**row, "relay_turns": 0})
            append_session(out, {**row, "session": "s0"})
            with out.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(list(rows[0]), SESSION_FIELDS)
        self.assertEqual(
            [(r["session"], r["relay_turns"]) for r in rows], [("s1", "0"), ("s0", "3")]
        )


if __name__ == "__main__":
    unittest.main()
