"""Tests for core_batches.py. Run: python -m unittest discover -s scripts -p "test_*.py"."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import core_batches as cb


def unit(name: str, files: list[str], seconds: float = 100) -> cb.Unit:
    return cb.Unit(name, [f"tests/{name}/{f}" for f in files], seconds)


class Discover(unittest.TestCase):
    def test_folders_and_root_files_become_units(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "a" / "sub").mkdir(parents=True)
        (root / "a" / "test_x.py").write_text("")
        (root / "a" / "sub" / "test_y.py").write_text("")
        (root / "b").mkdir()
        (root / "b" / "helper.py").write_text("")  # no tests: skipped
        (root / "test_top.py").write_text("")
        units = {u.name: u for u in cb.discover(root, 10, {})}
        self.assertEqual(set(units), {"a", "(root)"})
        self.assertEqual(units["a"].paths, ["tests/a"])
        self.assertEqual(units["a"].seconds, 20)
        self.assertEqual(units["(root)"].paths, ["tests/test_top.py"])

    def test_cached_duration_beats_the_file_count_guess(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "a").mkdir()
        (root / "a" / "test_x.py").write_text("")
        (unit_a,) = cb.discover(root, 10, {"a": 333.0})
        self.assertEqual(unit_a.seconds, 333.0)


class Pack(unittest.TestCase):
    def test_small_units_share_a_batch_under_the_budget(self) -> None:
        units = [
            unit("a", ["t1.py"], 100),
            unit("b", ["t2.py"], 200),
            unit("c", ["t3.py"], 300),
        ]
        batches = cb.pack(units, 480)
        self.assertEqual(sorted(len(b.units) for b in batches), [1, 2])
        self.assertTrue(all(b.seconds <= 480 for b in batches))

    def test_an_oversized_unit_gets_its_own_batch(self) -> None:
        batches = cb.pack([unit("big", ["t.py"], 900), unit("s", ["u.py"], 10)], 480)
        self.assertEqual(len(batches), 2)

    def test_duplicate_test_basenames_never_share_a_batch(self) -> None:
        units = [unit("a", ["test_same.py"], 10), unit("b", ["test_same.py"], 10)]
        self.assertEqual(len(cb.pack(units, 480)), 2)

    def test_packing_is_deterministic(self) -> None:
        units = [
            unit(n, [f"t_{n}.py"], s) for n, s in [("a", 50), ("b", 50), ("c", 400)]
        ]
        self.assertEqual(
            [b.name for b in cb.pack(units, 480)],
            [b.name for b in cb.pack(units[::-1], 480)],
        )


class Command(unittest.TestCase):
    def test_runs_pytest_in_core_api_under_the_core_lock(self) -> None:
        batch = cb.Batch([unit("a", ["t.py"])])
        cmd = cb.command(batch)
        self.assertEqual(cmd[2:4], ["core", "--"])
        self.assertIn("pytest", cmd)
        self.assertIn("tests/a/t.py", cmd)


class Run(unittest.TestCase):
    def setUp(self) -> None:
        self.batches = [
            cb.Batch([unit("a", ["t.py"])]),
            cb.Batch([unit("b", ["u.py"])]),
        ]

    def _run(self, codes: list[int], keep_going: bool) -> tuple[int, int]:
        results = [subprocess.CompletedProcess([], c) for c in codes]
        with (
            mock.patch.object(cb.subprocess, "run", side_effect=results) as run,
            mock.patch("builtins.print"),
        ):
            rc = cb.run_batches(
                self.batches, {}, keep_going, Path(tempfile.mkdtemp()) / "c.json"
            )
        return rc, run.call_count

    def test_all_green_returns_zero(self) -> None:
        self.assertEqual(self._run([0, 0], False), (0, 2))

    def test_stops_at_the_first_failure_by_default(self) -> None:
        self.assertEqual(self._run([1, 0], False), (1, 1))

    def test_keep_going_runs_every_batch_and_still_fails(self) -> None:
        self.assertEqual(self._run([1, 0], True), (1, 2))

    def test_lane_env_is_passed_to_the_child(self) -> None:
        with (
            mock.patch.object(cb.subprocess, "run") as run,
            mock.patch("builtins.print"),
        ):
            run.return_value = subprocess.CompletedProcess([], 0)
            cb.run_batches(
                self.batches[:1], {"X": "1"}, False, Path(tempfile.mkdtemp()) / "c"
            )
        self.assertEqual(run.call_args.kwargs["env"]["X"], "1")

    def test_a_single_unit_batch_records_its_wall_time_in_the_cache(self) -> None:
        cache = Path(tempfile.mkdtemp()) / "c.json"
        with (
            mock.patch.object(cb.subprocess, "run") as run,
            mock.patch("builtins.print"),
        ):
            run.return_value = subprocess.CompletedProcess([], 0)
            cb.run_batches(self.batches[:1], {}, False, cache)
        self.assertIn("a", json.loads(cache.read_text()))


class Cli(unittest.TestCase):
    def test_lane_is_inferred_from_the_worktree_name(self) -> None:
        self.assertEqual(cb.infer_lane(Path("D:/Essity/.claude/worktrees/L3")), 3)
        self.assertIsNone(cb.infer_lane(Path("D:/Essity")))


class Main(unittest.TestCase):
    def test_batch_runs_only_the_numbered_batch(self) -> None:
        with mock.patch.object(cb, "run_batches", return_value=0) as run:
            self.assertEqual(cb.main(["--lane", "L2", "--batch", "2"]), 0)
        batches = run.call_args.args[0]
        self.assertEqual(len(batches), 1)
        with mock.patch("builtins.print") as out:
            cb.main(["--list"])
        listed = [c.args[0] for c in out.call_args_list]
        self.assertEqual(batches[0].name, listed[2].split("  ", 1)[1])

    def test_batch_out_of_range_is_an_error(self) -> None:
        self.assertEqual(cb.main(["--lane", "L2", "--batch", "99"]), 2)

    def test_list_prints_the_command_for_each_batch(self) -> None:
        with mock.patch("builtins.print") as out:
            cb.main(["--list"])
        self.assertTrue(any("--batch 1" in c.args[0] for c in out.call_args_list))


if __name__ == "__main__":
    unittest.main()
