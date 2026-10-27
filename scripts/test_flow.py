"""Tests for flow.py. Run: python -m unittest discover -s scripts -p "test_*.py"."""

import csv
import json
import subprocess
import tempfile
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from unittest import mock

import flow

FULL = "a" * 40
SHORT = FULL[:7]


def evidence(step: str, verdict: str, sha: str = FULL, **extra: object) -> str:
    fields = {
        "step": step,
        "verdict": verdict,
        "sha": sha,
        "round": 1,
        "open_orange": 0,
        **extra,
    }
    return "\n".join(f"{key}: {value}" for key, value in fields.items()) + "\nsummary: ok\n"


class Reader(unittest.TestCase):
    def test_scalars_inline_collections_and_comments(self) -> None:
        got = flow.parse_yaml(
            'task: T3.1  # comment\nn: 3\nq: "a, b: c"\nt: {cmd: "x y", passed: 56}\n'
            'd: ["one, two", three]\nnone: []\n'
        )
        self.assertEqual(got["task"], "T3.1")
        self.assertEqual(got["n"], 3)
        self.assertEqual(got["q"], "a, b: c")
        self.assertEqual(got["t"], {"cmd": "x y", "passed": 56})
        self.assertEqual(got["d"], ["one, two", "three"])
        self.assertEqual(got["none"], [])

    def test_block_lists_and_nested_mappings(self) -> None:
        got = flow.parse_yaml(
            "mutations:\n  killed: 4\n  survived: 0\nfindings:\n  - id: O1\n    level: x\n"
            "  - id: O2\nplain:\n  - a\n  - b\nafter: 1\n"
        )
        self.assertEqual(got["mutations"], {"killed": 4, "survived": 0})
        self.assertEqual(got["findings"], [{"id": "O1", "level": "x"}, {"id": "O2"}])
        self.assertEqual(got["plain"], ["a", "b"])
        self.assertEqual(got["after"], 1)

    def test_empty_text_and_quoted_list(self) -> None:
        self.assertEqual(flow.parse_yaml(""), {})
        got = flow.parse_yaml('status: done\ndecisions: ["a -> b (Coder)", "c (x)"]\n')
        self.assertEqual(got["decisions"], ["a -> b (Coder)", "c (x)"])


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.work = self.tmp / ".work"
        self.dir = self.work / "T9"
        self.dir.mkdir(parents=True)
        self.repo = self.tmp

    def card(self, risk: str = "red") -> None:
        (self.dir / "card.yaml").write_text(
            f"task: T9\nlane: L2\nbranch: t9-x\nrisk: {risk}\nworktree: {self.tmp / 'nope'}\n"
        )

    def put(self, name: str, text: str) -> None:
        (self.dir / name).write_text(text)

    def all_red(self, sha: str = FULL) -> None:
        self.card("red")
        self.put("lane-report.yaml", f"status: done\nhead_sha: {sha}\n")
        self.put("plan-review.yaml", evidence("plan", "pass", sha))
        self.put("review-task-1.yaml", evidence("task", "pass", sha))
        self.put("tester.yaml", evidence("tester", "pass", sha))
        self.put("review.yaml", evidence("final", "merge", sha))
        self.put("pm.yaml", evidence("pm", "pass", sha))


class Gate(Fixture):
    def run_gate(self, head: str = FULL) -> list[str]:
        return flow.gate(self.work, "T9", head, self.repo)

    def test_missing_card_and_missing_files_are_reported_not_raised(self) -> None:
        self.assertIn("card.yaml", self.run_gate()[0])
        self.card("red")
        problems = self.run_gate()
        for name in (
            "lane-report",
            "plan-review",
            "review-task",
            "tester",
            "review",
            "pm",
        ):
            self.assertTrue(any(p.startswith(name) for p in problems), name)

    def test_all_evidence_at_head_passes(self) -> None:
        self.all_red()
        self.assertEqual(self.run_gate(), [])

    def test_yellow_needs_only_review_pm_and_lane_report(self) -> None:
        self.card("yellow")
        self.put("lane-report.yaml", "status: done\n")
        self.put("review.yaml", evidence("final", "merge"))
        self.put("pm.yaml", evidence("pm", "pass"))
        self.assertEqual(self.run_gate(), [])

    def test_bad_verdict_open_orange_and_unfinished_lane_block(self) -> None:
        self.all_red()
        self.put("review.yaml", evidence("final", "no"))
        self.put("pm.yaml", evidence("pm", "pass", open_orange=2))
        self.put("lane-report.yaml", "status: in_progress\n")
        problems = "\n".join(self.run_gate())
        self.assertIn("review: review.yaml: verdict='no'", problems)
        self.assertIn("2 🟠", problems)
        self.assertIn("lane-report", problems)

    def test_open_orange_missing_or_not_a_number_blocks(self) -> None:
        self.all_red()
        self.put("review.yaml", f"step: final\nverdict: merge\nsha: {FULL}\n")
        self.put("pm.yaml", evidence("pm", "pass", open_orange="none"))
        problems = self.run_gate()
        self.assertTrue(any("review.yaml: open_orange thiếu/không hợp lệ" in p for p in problems))
        self.assertTrue(any("pm.yaml: open_orange thiếu/không hợp lệ" in p for p in problems))

    def test_pass_verdict_is_not_a_merge_verdict(self) -> None:
        self.all_red()
        self.put("review.yaml", evidence("final", "pass"))
        self.assertTrue(any("verdict='pass'" in p for p in self.run_gate()))

    def test_review_and_pm_sha_must_equal_head_short_sha_ok(self) -> None:
        self.all_red(sha=SHORT)
        self.assertEqual(self.run_gate(), [])
        self.put("pm.yaml", evidence("pm", "pass", "b" * 40))
        self.assertTrue(any("pm.yaml: sha" in p for p in self.run_gate()))

    def test_tester_and_review_task_may_be_ancestors(self) -> None:
        self.all_red()
        old = "c" * 40
        self.put("tester.yaml", evidence("tester", "pass", old))
        self.put("review-task-1.yaml", evidence("task", "pass", old))
        with mock.patch.object(flow, "is_ancestor", return_value=True):
            self.assertEqual(self.run_gate(), [])
        with mock.patch.object(flow, "is_ancestor", return_value=False):
            problems = self.run_gate()
        self.assertTrue(any("tester.yaml" in p for p in problems))
        self.assertTrue(any("review-task-1.yaml" in p for p in problems))

    def test_cli_exit_code(self) -> None:
        self.all_red()
        args = ["--work", str(self.work), "gate", "T9", "--head", FULL]
        self.assertEqual(flow.main(args), 0)
        (self.dir / "pm.yaml").unlink()
        self.assertEqual(flow.main(args), 1)


class AncestorGit(unittest.TestCase):
    def test_is_ancestor_with_real_git(self) -> None:
        repo = Path(tempfile.mkdtemp())

        def git(*args: str) -> str:
            return subprocess.run(
                ["git", "-C", str(repo), *args],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

        git("init", "-q", "-b", "main")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "t")
        (repo / "a").write_text("1")
        git("add", "a")
        git("commit", "-q", "-m", "1")
        first = git("rev-parse", "HEAD")
        (repo / "a").write_text("2")
        git("commit", "-qam", "2")
        second = git("rev-parse", "HEAD")
        self.assertTrue(flow.is_ancestor(repo, first, second))
        self.assertFalse(flow.is_ancestor(repo, second, first))
        self.assertTrue(flow.is_ancestor(repo, second, second))


class Check(Fixture):
    def run_check(self, pr: dict[str, Any] | None) -> list[str]:
        with (
            mock.patch.object(flow, "open_pr", return_value=pr),
            mock.patch.object(flow, "is_ancestor", return_value=True),
        ):
            return flow.check(self.work, "T9", self.repo)

    def test_without_card_it_says_so_and_does_not_crash(self) -> None:
        out = self.run_check(None)
        self.assertTrue(out[0].startswith("✗ card"))
        self.assertIn("next: card", out[-1])

    def test_next_step_follows_the_order_for_red(self) -> None:
        self.card("red")
        self.assertIn("next: plan-review (security-reviewer)", self.run_check(None))
        self.put("plan-review.yaml", evidence("plan", "pass"))
        self.assertTrue(any(line.startswith("next: code") for line in self.run_check(None)))
        self.put("lane-report.yaml", f"status: done\nhead_sha: {FULL}\n")
        self.assertTrue(any(line.startswith("next: review-task") for line in self.run_check(None)))

    def test_yellow_marks_red_steps_not_required(self) -> None:
        self.card("yellow")
        out = self.run_check(None)
        self.assertIn("— plan-review", out)
        self.assertIn("— tester", out)
        self.assertIn("next: code (lane lead L2)", out)

    def test_mergeable_when_everything_green_at_pr_head(self) -> None:
        self.all_red()
        pr = {
            "number": 7,
            "headRefOid": FULL,
            "mergeable": "MERGEABLE",
            "statusCheckRollup": [{"conclusion": "SUCCESS", "status": "COMPLETED"}],
        }
        out = self.run_check(pr)
        self.assertIn("✓ mergeable", out)
        self.assertEqual(out[-1], "next: merge (orchestrator)")

    def test_review_for_an_older_head_is_not_accepted(self) -> None:
        self.all_red()
        pr = {"number": 7, "headRefOid": "d" * 40, "statusCheckRollup": []}
        out = self.run_check(pr)
        self.assertTrue(any(line.startswith("✗ review") and "HEAD" in line for line in out))
        self.assertIn("✗ ci  (chưa có CI)", out)

    def test_ci_red_and_pending(self) -> None:
        red = {"statusCheckRollup": [{"conclusion": "FAILURE", "status": "COMPLETED"}]}
        wait = {"statusCheckRollup": [{"conclusion": "", "status": "IN_PROGRESS"}]}
        self.assertEqual(flow.ci_state(red), ("fail", "CI đỏ"))
        self.assertEqual(flow.ci_state(wait), ("missing", "CI đang chạy"))


class Metrics(Fixture):
    def test_build_row_and_upsert_without_duplicates(self) -> None:
        self.all_red()
        self.put("tester.yaml", evidence("tester", "pass", round=2, tokens=1000))
        self.put("review.yaml", evidence("final", "merge", tokens=500, orange_total=3))
        self.put("lane-report.yaml", "status: done\ntokens: 250\n")

        def fake_run(args: list[str], cwd: Path | None = None) -> str:
            if args[0] == "git":
                return "2026-10-27T08:00:00+00:00\n2026-10-27T09:00:00+00:00\n"
            if args[:3] == ["gh", "pr", "view"]:
                return json.dumps({"mergedAt": "2026-10-27T11:30:00Z"})
            return json.dumps([{"conclusion": "failure"}, {"conclusion": "success"}])

        with mock.patch.object(flow, "_run", fake_run):
            row = flow.build_row(self.work, "T9", 29, self.repo)
        self.assertEqual(row["hours"], "3.5")
        self.assertEqual(row["tester_rounds"], 2)
        self.assertEqual(row["ci_failed_runs"], 1)
        self.assertEqual(row["subagent_tokens"], 1750)
        self.assertEqual(row["orange_found"], 3)
        self.assertIn("subagent_usd", row)
        out = self.tmp / "m" / "metrics.csv"
        flow.record(out, row)
        flow.record(out, {**row, "pr": 30})
        with out.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["pr"], "30")
        self.assertEqual(list(rows[0]), flow.CSV_FIELDS)


class RealTokens(Fixture):
    def run_build(self, projects: Path) -> dict[str, Any]:
        with mock.patch.object(flow, "_run", lambda args, cwd=None: ""):
            return flow.build_row(self.work, "T9", 1, self.repo, projects_dir=projects)

    def setUp(self) -> None:
        super().setUp()
        self.all_red()

    def test_transcripts_replace_the_evidence_tokens_key(self) -> None:
        from test_agent_usage import sub_transcript

        self.put("tester.yaml", evidence("tester", "pass", tokens=999))
        root = self.tmp / "proj"
        sub_transcript(root, "a", "task T9", out=1000)
        sub_transcript(root, "b", "task T90", out=5000)
        row = self.run_build(root)
        self.assertEqual(row["subagent_tokens"], 2000)
        self.assertGreater(float(row["subagent_usd"]), 0)

    def test_no_transcript_falls_back_to_evidence_tokens(self) -> None:
        self.put("tester.yaml", evidence("tester", "pass", tokens=999))
        row = self.run_build(self.tmp / "empty")
        self.assertEqual(row["subagent_tokens"], 999)
        self.assertEqual(row["subagent_usd"], "")

    def test_retro_reads_old_rows_without_the_usd_column(self) -> None:
        path = self.tmp / "old.csv"
        old = [f for f in flow.CSV_FIELDS if f != "subagent_usd"]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=old)
            writer.writeheader()
            for i in range(5):
                writer.writerow(
                    {
                        "task": f"T{i}",
                        "risk": "yellow",
                        "merged_at": f"2026-10-{i + 10}",
                    }
                )
        self.assertTrue(flow.retro(path))
        out = self.tmp / "mixed.csv"
        out.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        flow.record(out, {"task": "T9", "subagent_usd": "1.5"})  # rewrites with the new header
        with out.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]["subagent_usd"], "")
        self.assertEqual(rows[-1]["subagent_usd"], "1.5")


class Retro(unittest.TestCase):
    def write(self, rows: Sequence[Mapping[str, object]]) -> Path:
        path = Path(tempfile.mkdtemp()) / "metrics.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=flow.CSV_FIELDS)
            writer.writeheader()
            for index, row in enumerate(rows):
                base = {
                    "task": f"T{index}",
                    "risk": "yellow",
                    "merged_at": f"2026-10-{10 + index:02d}",
                }
                writer.writerow({**base, **row})
        return path

    def test_not_enough_data(self) -> None:
        path = self.write([{"hours": 1}] * 4)
        self.assertIn("chưa đủ dữ liệu", flow.retro(path)[0])
        self.assertIn("chưa đủ dữ liệu", flow.retro(Path("missing.csv"))[0])

    def test_flags_worse_than_twenty_percent_and_furthest_target(self) -> None:
        old = [{"hours": 2, "subagent_tokens": 1000, "ci_failed_runs": 0}] * 5
        new = [{"hours": 6, "subagent_tokens": 1100, "ci_failed_runs": 0}] * 5
        lines = flow.retro(self.write(old + new))
        hours = next(line for line in lines if line.strip().startswith("hours"))
        tokens = next(line for line in lines if line.strip().startswith("subagent_tokens"))
        self.assertIn("XẤU ĐI +200%", hours)
        self.assertNotIn("XẤU ĐI", tokens)  # +10 %
        self.assertTrue(any("xa mục tiêu nhất: hours (x2.0" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
