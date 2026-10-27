"""Tests for agent_usage.py. Run: python -m unittest discover -s scripts -p "test_*.py"."""

import json
import tempfile
import unittest
from pathlib import Path

from agent_usage import collect, estimate_cost, last_context_tokens, scan, summarize


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
                'not json\n{"type": "user", "message": {"content": "hi"}}\n', encoding="utf-8"
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
    def test_cache_reads_cost_a_tenth_of_input_and_sonnet_is_cheaper_than_opus(self) -> None:
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
                {"customAgentType": "security-reviewer", "name": "rev-t2.1", "model": "sonnet"}
            ),
            encoding="utf-8",
        )
        write_jsonl(
            proj / "s0.jsonl", [turn("m0", "claude-opus-5-5", "2026-10-20T10:00:00Z", 0, 0, 9, 1)]
        )

    def test_rows_carry_role_and_name_and_since_filters_by_session_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.make_project(Path(tmp))
            rows = collect(Path(tmp), "D--Essity*", since="2026-10-25")
        self.assertEqual(
            sorted((r.kind, r.role) for r in rows), [("main", "main"), ("sub", "security-reviewer")]
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


if __name__ == "__main__":
    unittest.main()
