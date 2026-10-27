"""Tests for hooks/context_budget.py. Run: python -m unittest discover -s scripts -p "test_*.py"."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "hooks"))

from agent_usage import last_context_tokens
from context_budget import reminder
from test_agent_usage import turn, write_jsonl


class Reminder(unittest.TestCase):
    def test_nothing_below_the_threshold(self) -> None:
        self.assertEqual(reminder(150_000, 200_000, last_band=0), (None, 0))

    def test_reminds_once_per_50k_band_above_the_threshold(self) -> None:
        text, band = reminder(210_000, 200_000, last_band=0)
        self.assertIn("210k", text or "")
        self.assertEqual(band, 1)
        # Same band again: quiet, so the reminder does not repeat on every call.
        self.assertEqual(reminder(240_000, 200_000, last_band=1), (None, 1))
        text, band = reminder(255_000, 200_000, last_band=1)
        self.assertIsNotNone(text)
        self.assertEqual(band, 2)

    def test_a_cleared_session_starts_counting_again(self) -> None:
        # After /clear the context drops; a later climb must remind again.
        self.assertEqual(reminder(90_000, 200_000, last_band=3), (None, 0))


class Tail(unittest.TestCase):
    def test_reads_the_latest_turn_from_the_tail_of_a_large_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.jsonl"
            filler = {"type": "user", "message": {"content": "x" * 5000}}
            rows = [turn("m1", "claude-opus-5-5", "t1", 0, 0, 900_000, 1)]
            rows += [filler] * 50
            rows += [turn("m2", "claude-opus-5-5", "t2", 0, 0, 230_000, 1)]
            write_jsonl(path, rows)
            self.assertEqual(last_context_tokens(path, tail_bytes=64 * 1024), 230_000)
            # The tail holds no assistant turn at all: report 0, not a stale value.
            write_jsonl(path, rows[:1] + [filler] * 50)
            self.assertEqual(last_context_tokens(path, tail_bytes=64 * 1024), 0)


class Hook(unittest.TestCase):
    def run_hook(self, call: dict, state_dir: Path) -> str:
        import io
        from contextlib import redirect_stdout

        from context_budget import main

        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(call, state_dir, threshold=200_000), 0)
        return out.getvalue()

    def test_main_session_over_budget_gets_additional_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "s.jsonl"
            write_jsonl(transcript, [turn("m", "claude-opus-5-5", "t", 0, 0, 260_000, 1)])
            call = {"session_id": "s1", "transcript_path": str(transcript)}
            out = json.loads(self.run_hook(call, Path(tmp) / "state"))
            self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
            self.assertIn("260k", out["hookSpecificOutput"]["additionalContext"])
            # Second call in the same band stays quiet.
            self.assertEqual(self.run_hook(call, Path(tmp) / "state"), "")

    def test_calls_inside_a_subagent_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "s.jsonl"
            write_jsonl(transcript, [turn("m", "claude-opus-5-5", "t", 0, 0, 900_000, 1)])
            call = {"session_id": "s1", "transcript_path": str(transcript), "agent_id": "a1"}
            self.assertEqual(self.run_hook(call, Path(tmp) / "state"), "")


if __name__ == "__main__":
    unittest.main()
