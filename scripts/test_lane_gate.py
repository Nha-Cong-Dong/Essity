"""Tests for hooks/lane_gate.py and hooks/retro_due.py (W3, W4).
Run: python -m unittest discover -s scripts -p "test_*.py"."""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent / "hooks"))

import lane_gate
import retro_due
from test_lane import MODELS, git


def merges(n: int) -> str:
    return "task,merged_at\n" + "".join(f"T{i},2026-10-30T0{i}:00:00Z\n" for i in range(n))


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp()) / "repo"
        models = self.repo / "services" / "core-api" / "src" / "core_api" / "db" / "models"
        models.mkdir(parents=True)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "t")
        (models / "document.py").write_text(MODELS, encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "models")
        self.ops = self.repo / "docs" / "ops"
        self.ops.mkdir(parents=True)
        (self.ops / "process-changelog.md").write_text("| 29/10 | x | y |\n", encoding="utf-8")
        self.set_merges(2)

    def set_merges(self, n: int) -> None:
        (self.ops / "metrics.csv").write_text(merges(n), encoding="utf-8")

    def card(self, task: str, extra: str = "") -> None:
        folder = self.repo / ".work" / task
        folder.mkdir(parents=True, exist_ok=True)
        text = f"task: {task}\nbase: main\n{extra}"
        (folder / "card.yaml").write_text(text, encoding="utf-8")

    def call(self, prompt: str, kind: str = "lane-lead") -> dict:
        return {"tool_name": "Agent", "tool_input": {"subagent_type": kind, "prompt": prompt}}


class LaneGate(Fixture):
    def test_other_agents_and_tools_pass(self) -> None:
        self.set_merges(9)
        self.assertEqual(
            lane_gate.decide(self.call("T7.4", "security-reviewer"), self.repo), (None, [])
        )
        bash = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
        self.assertEqual(lane_gate.decide(bash, self.repo), (None, []))

    def test_retro_due_blocks_a_lane_lead(self) -> None:
        self.set_merges(5)
        reason, _ = lane_gate.decide(self.call("Luồng L1, task T7.4"), self.repo)
        self.assertIn("RETRO DUE: 5 merge chưa retro", reason or "")
        self.assertIn("flow.py retro", reason or "")

    def test_missing_schema_blocks_and_full_schema_passes(self) -> None:
        self.card("T7.4", "needs_schema: [doc_section.page_start]\n")
        self.card("T7.6", "needs_schema: [doc_section.title]\n")
        reason, _ = lane_gate.decide(self.call("Luồng L3, task T7.4 (card)."), self.repo)
        self.assertIn("doc_section.page_start", reason or "")
        self.assertEqual(lane_gate.decide(self.call("task T7.6"), self.repo), (None, []))

    def test_a_card_without_needs_schema_only_warns(self) -> None:
        self.card("T7.4")
        reason, notes = lane_gate.decide(self.call("task T7.4"), self.repo)
        self.assertIsNone(reason)
        self.assertIn("needs_schema", notes[0])

    def test_task_codes_match_whole(self) -> None:
        # T7.40 is not T7.4
        self.card("T7.4", "needs_schema: [doc_section.page_start]\n")
        self.assertEqual(lane_gate.decide(self.call("task T7.40"), self.repo), (None, []))

    def test_main_exits_2_with_the_reason_on_stderr(self) -> None:
        self.set_merges(6)
        stdin = io.StringIO(json.dumps(self.call("task T1")))
        with (
            mock.patch.object(lane_gate, "main_checkout", lambda _cwd: self.repo),
            mock.patch("sys.stdin", stdin),
            mock.patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            self.assertEqual(lane_gate.main(), 2)
        self.assertIn("RETRO DUE: 6", err.getvalue())


class RetroDueHook(Fixture):
    def test_prints_the_line_only_when_due(self) -> None:
        self.assertEqual(retro_due.message(self.repo), "")
        self.set_merges(7)
        self.assertIn("RETRO DUE: 7 merge chưa retro", retro_due.message(self.repo))

    def test_without_docs_it_is_quiet(self) -> None:
        empty = Path(tempfile.mkdtemp())
        self.assertEqual(retro_due.message(empty), "")


if __name__ == "__main__":
    unittest.main()
